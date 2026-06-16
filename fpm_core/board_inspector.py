r"""Board component inspector — live template-matching AOI tool.

- Source: a folder of images (replayed as a live feed) or a webcam. An industrial
  camera can be plugged in via camera_source.IndustrialCameraSource.
- Detection: loads a component template library (component_detector.ComponentLibrary),
  runs fpm on each frame, overlays labelled boxes and a per-component pass/fail count.
- Teach: pause, drag a rectangle over a component, name it -> saved to the library and
  used immediately.

Run:  python board_inspector.py
"""
import os
import threading
import time
import traceback

import numpy as np
from PIL import Image, ImageTk

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from fpm_env import HERE
from camera_source import FolderSource, WebcamSource
from component_detector import ComponentLibrary, to_gray

DEFAULT_TEMPLATE_DIR = os.path.join(HERE, "templates")

COLOR_OK = "#1fbf4f"
COLOR_BAD = "#ff5050"
BOX_COLOR = "#00e000"


class BoardInspector(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Board Component Inspector — fpm")
        self.geometry("1280x820")
        self.minsize(1000, 660)

        self.source = None
        self.lib = ComponentLibrary(DEFAULT_TEMPLATE_DIR)
        self._worker = None
        self._running = False
        self._detect_on = tk.BooleanVar(value=True)
        self._teaching = False

        self._frame_rgb = None       # latest full-res RGB frame (numpy)
        self._detections = []        # latest detections
        self._photo = None
        self._scale = 1.0
        self._ox = self._oy = 0
        self._fps = 0.0

        # teach rubber-band
        self._rb_start = None
        self._rb_id = None

        self._build_ui()
        self._try_load_library(DEFAULT_TEMPLATE_DIR, silent=True)

    # ---------------- UI ----------------
    def _build_ui(self):
        root = ttk.Frame(self, padding=6)
        root.pack(fill="both", expand=True)

        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 6))

        ttk.Label(left, text="Source", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Folder (replay)…", command=self.use_folder).pack(fill="x", pady=2)
        ttk.Button(left, text="Webcam", command=self.use_webcam).pack(fill="x", pady=2)
        row = ttk.Frame(left); row.pack(fill="x", pady=2)
        self.start_btn = ttk.Button(row, text="▶ Start", command=self.start)
        self.start_btn.pack(side="left", expand=True, fill="x")
        self.stop_btn = ttk.Button(row, text="⏹ Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", expand=True, fill="x")
        ttk.Checkbutton(left, text="Detect", variable=self._detect_on).pack(anchor="w")
        self.src_lbl = ttk.Label(left, text="source: (none)", foreground="#666",
                                 wraplength=240)
        self.src_lbl.pack(anchor="w")

        ttk.Separator(left).pack(fill="x", pady=6)
        ttk.Label(left, text="Template library",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Load folder…", command=self.load_library).pack(fill="x", pady=2)
        self.lib_lbl = ttk.Label(left, text=DEFAULT_TEMPLATE_DIR, foreground="#666",
                                 wraplength=240)
        self.lib_lbl.pack(anchor="w")
        self.teach_btn = ttk.Button(left, text="✎ Teach region (drag on image)",
                                    command=self.toggle_teach)
        self.teach_btn.pack(fill="x", pady=2)
        ttk.Button(left, text="Delete selected", command=self.delete_selected).pack(fill="x", pady=2)

        ttk.Label(left, text="Components (found / expected)").pack(anchor="w", pady=(6, 0))
        self.tree = ttk.Treeview(left, columns=("found", "exp"), height=16, selectmode="browse")
        self.tree.heading("#0", text="name")
        self.tree.heading("found", text="found")
        self.tree.heading("exp", text="exp")
        self.tree.column("#0", width=120)
        self.tree.column("found", width=50, anchor="center")
        self.tree.column("exp", width=45, anchor="center")
        self.tree.pack(fill="both", expand=True)

        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(right, bg="#101010", highlightthickness=0, cursor="tcross")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)

        self.status = ttk.Label(self, text="Ready.", relief="sunken", anchor="w")
        self.status.pack(side="bottom", fill="x")
        self._refresh_tree()

    # ---------------- Source selection ----------------
    def use_folder(self):
        d = filedialog.askdirectory(title="Pick image folder", initialdir=HERE)
        if not d:
            return
        self._set_source(FolderSource(d, fps=5.0))

    def use_webcam(self):
        try:
            self._set_source(WebcamSource(0))
        except Exception as e:
            messagebox.showerror("Webcam", str(e))

    def _set_source(self, src):
        self.stop()
        self.source = src
        self.src_lbl.config(text=f"source: {src.name}")
        self.status.config(text=f"Source set: {src.name}. Press Start.")

    def start(self):
        if self.source is None:
            messagebox.showinfo("No source", "Pick a folder or webcam first.")
            return
        if self._running:
            return
        try:
            self.source.open()
        except Exception as e:
            messagebox.showerror("Open source", str(e))
            return
        self._running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()

    def stop(self):
        self._running = False
        if self.source is not None:
            try:
                self.source.close()
            except Exception:
                pass
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    # ---------------- Capture + detect loop (worker thread) ----------------
    def _loop(self):
        while self._running:
            try:
                ok, frame = self.source.read()
            except Exception:
                self.after(0, lambda tb=traceback.format_exc(): self._fatal(tb))
                return
            if not ok:
                self.after(0, self.stop)
                return
            t0 = time.time()
            dets = []
            if self._detect_on.get() and not self._teaching and self.lib.components:
                try:
                    dets = self.lib.detect(to_gray(frame))
                except Exception:
                    dets = []
            dt = time.time() - t0
            self._fps = (1.0 / dt) if dt > 0 else 0.0
            if not self._teaching:
                self._frame_rgb = frame
                self._detections = dets
                self.after(0, self._render)

    def _fatal(self, tb):
        self.stop()
        messagebox.showerror("Source error", tb)

    # ---------------- Rendering ----------------
    def _render(self):
        frame = self._frame_rgb
        if frame is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:  # canvas not laid out yet
            return
        h, w = frame.shape[:2]
        self._scale = min(cw / w, ch / h)
        dw, dh = max(1, int(w * self._scale)), max(1, int(h * self._scale))
        self._ox, self._oy = (cw - dw) // 2, (ch - dh) // 2

        disp = Image.fromarray(frame).resize((dw, dh), Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(self._ox, self._oy, anchor="nw", image=self._photo)

        counts = {}
        for d in self._detections:
            counts[d["name"]] = counts.get(d["name"], 0) + 1
            pts = []
            for (x, y) in d["corners"]:
                pts += [self._ox + x * self._scale, self._oy + y * self._scale]
            self.canvas.create_polygon(pts, outline=BOX_COLOR, fill="", width=2)
            lx = self._ox + d["corners"][0][0] * self._scale
            ly = self._oy + d["corners"][0][1] * self._scale - 12
            self.canvas.create_text(lx, ly, anchor="w", fill=BOX_COLOR,
                                    text=f"{d['name']} {d['score']:.2f}",
                                    font=("Segoe UI", 9, "bold"))
        self._update_counts(counts)
        self.status.config(text=f"{self.source.name}  |  {w}x{h}  |  "
                                f"{len(self._detections)} detections  |  ~{self._fps:.1f} fps")

    def _update_counts(self, counts):
        expected = self.lib.expected_counts()
        for name in self.lib.components:
            found = counts.get(name, 0)
            exp = expected.get(name, 1)
            tag = "ok" if found >= exp else "bad"
            if self.tree.exists(name):
                self.tree.item(name, values=(found, exp), tags=(tag,))
        self.tree.tag_configure("ok", foreground=COLOR_OK)
        self.tree.tag_configure("bad", foreground=COLOR_BAD)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        expected = self.lib.expected_counts()
        for name in self.lib.components:
            self.tree.insert("", "end", iid=name, text=name,
                             values=(0, expected.get(name, 1)))

    # ---------------- Library ----------------
    def load_library(self):
        d = filedialog.askdirectory(title="Pick template library folder", initialdir=HERE)
        if d:
            self._try_load_library(d)

    def _try_load_library(self, folder, silent=False):
        try:
            self.lib = ComponentLibrary(folder).load()
        except Exception as e:
            if not silent:
                messagebox.showerror("Library", str(e))
            return
        self.lib_lbl.config(text=folder)
        self._refresh_tree()
        if not silent:
            self.status.config(text=f"Loaded {len(self.lib.components)} component(s).")

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = sel[0]
        if messagebox.askyesno("Delete", f"Delete component '{name}'?"):
            self.lib.remove(name)
            self._refresh_tree()

    # ---------------- Teach (rubber-band crop) ----------------
    def toggle_teach(self):
        self._teaching = not self._teaching
        self.teach_btn.config(text="✎ Teaching… (drag)" if self._teaching
                              else "✎ Teach region (drag on image)")
        self.status.config(text="Teach mode: drag a rectangle over a component."
                           if self._teaching else "Teach mode off.")

    def _on_down(self, ev):
        if not self._teaching:
            return
        self._rb_start = (ev.x, ev.y)
        if self._rb_id:
            self.canvas.delete(self._rb_id)
        self._rb_id = self.canvas.create_rectangle(ev.x, ev.y, ev.x, ev.y,
                                                   outline="#ffcc00", width=2)

    def _on_drag(self, ev):
        if not self._teaching or self._rb_start is None:
            return
        x0, y0 = self._rb_start
        self.canvas.coords(self._rb_id, x0, y0, ev.x, ev.y)

    def _on_up(self, ev):
        if not self._teaching or self._rb_start is None:
            return
        x0, y0 = self._rb_start
        x1, y1 = ev.x, ev.y
        self._rb_start = None
        if self._frame_rgb is None:
            return
        # canvas -> image coords
        ix0 = int((min(x0, x1) - self._ox) / self._scale)
        iy0 = int((min(y0, y1) - self._oy) / self._scale)
        ix1 = int((max(x0, x1) - self._ox) / self._scale)
        iy1 = int((max(y0, y1) - self._oy) / self._scale)
        h, w = self._frame_rgb.shape[:2]
        ix0, iy0 = max(0, ix0), max(0, iy0)
        ix1, iy1 = min(w, ix1), min(h, iy1)
        if ix1 - ix0 < 6 or iy1 - iy0 < 6:
            self.status.config(text="Region too small.")
            return
        patch = self._frame_rgb[iy0:iy1, ix0:ix1]
        name = simpledialog.askstring("Teach component", "Component name:",
                                      parent=self)
        if not name:
            return
        try:
            self.lib.add(name, patch)
        except Exception as e:
            messagebox.showerror("Teach", str(e))
            return
        self._refresh_tree()
        self.status.config(text=f"Added '{name}' ({ix1-ix0}x{iy1-iy0}). "
                           f"Turn off Teach to resume detection.")


if __name__ == "__main__":
    BoardInspector().mainloop()
