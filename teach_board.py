#coding=utf-8
"""Tu tao 'data' kiem tra linh kien tu LIVE camera (hoac anh tinh): keo chuot chon
vung -> dat ten, nguong (score), so luong, va co cho phep xoay 180 do hay khong ->
luu template (gray PNG) + components.json (format ComponentLibrary / board_inspector).

Chay (venv co san fpm cua fpm_core):
    fpm_core\\.venv\\Scripts\\python.exe teach_board.py

Thao tac:
    - Live / Freeze : bat/tat xem truc tiep tu camera. Freeze de dung hinh va ve khung.
    - Open image... : nap 1 anh tinh thay cho camera.
    - Keo chuot tren anh (khi dang Freeze / dang xem anh tinh) -> ve khung linh kien.
      Tha chuot -> hộp thoai: Ten / Score nguong / So luong / [x] Cho phep xoay 180 do.
    - Library folder...      : doi thu muc luu.
    - Chon trong list + Delete: xoa linh kien.
"""
import os
import sys
import json
import argparse

import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMAGE = os.path.join(HERE, "mindvision_python", "snap_000.jpg")
DEFAULT_LIB = os.path.join(HERE, "fpm_core", "templates_board")
CONFIG_NAME = "components.json"
MAX_VIEW = (1100, 820)

# angle = tolerance_angle (do). 180 = cho phep linh kien xoay 180 do.
ANGLE_180 = 180
ANGLE_NONE = 10          # mac dinh khi khong cho xoay (van cho lech nho)


class AddDialog(tk.Toplevel):
    """Hop thoai nhap thuoc tinh linh kien sau khi ve khung."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Thuoc tinh linh kien")
        self.result = None
        self.resizable(False, False)
        self.transient(parent)

        self.v_name = tk.StringVar()
        self.v_score = tk.DoubleVar(value=0.70)
        self.v_exp = tk.IntVar(value=1)
        self.v_rot = tk.BooleanVar(value=False)

        f = tk.Frame(self, padx=12, pady=12); f.pack()
        tk.Label(f, text="Ten:").grid(row=0, column=0, sticky="e")
        e_name = tk.Entry(f, textvariable=self.v_name, width=22)
        e_name.grid(row=0, column=1, sticky="w", pady=3)
        tk.Label(f, text="Score nguong (0-1):").grid(row=1, column=0, sticky="e")
        tk.Spinbox(f, from_=0.1, to=1.0, increment=0.05, textvariable=self.v_score,
                   width=8, format="%.2f").grid(row=1, column=1, sticky="w", pady=3)
        tk.Label(f, text="So luong ky vong:").grid(row=2, column=0, sticky="e")
        tk.Spinbox(f, from_=1, to=50, textvariable=self.v_exp, width=8).grid(
            row=2, column=1, sticky="w", pady=3)
        tk.Checkbutton(f, text="Cho phep xoay 180 do", variable=self.v_rot).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=4)

        b = tk.Frame(f); b.grid(row=4, column=0, columnspan=2, pady=(8, 0))
        tk.Button(b, text="Luu", width=8, command=self.ok).pack(side="left", padx=4)
        tk.Button(b, text="Huy", width=8, command=self.cancel).pack(side="left", padx=4)

        e_name.focus_set()
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())
        self.grab_set()

    def ok(self):
        name = self.v_name.get().strip()
        if not name:
            messagebox.showwarning("Thieu ten", "Nhap ten linh kien.", parent=self)
            return
        self.result = {
            "name": name,
            "score": round(float(self.v_score.get()), 3),
            "expected": int(self.v_exp.get()),
            "angle": ANGLE_180 if self.v_rot.get() else ANGLE_NONE,
            "max_pos": max(2, int(self.v_exp.get()) + 1),
            "max_overlap": 0.3,
            "enabled": True,
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class TeachApp:
    def __init__(self, root, image_path, lib_dir, use_camera=True):
        self.root = root
        self.lib_dir = lib_dir
        self.img = None            # PIL RGB dang hien thi (de crop)
        self.tkimg = None
        self.scale = 1.0
        self.start = None
        self.rect_id = None
        self.config = {}
        self.cam = None
        self.live = False

        root.title("Teach board - tao data linh kien (live)")

        bar = tk.Frame(root); bar.pack(fill="x")
        self.btn_live = tk.Button(bar, text="Live", width=8, command=self.toggle_live)
        self.btn_live.pack(side="left", padx=3, pady=3)
        self.normalize = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="Chuan hoa board", variable=self.normalize).pack(side="left", padx=4)
        tk.Button(bar, text="Open image...", command=self.open_image).pack(side="left", padx=3)
        tk.Button(bar, text="Library folder...", command=self.choose_lib).pack(side="left", padx=3)
        tk.Button(bar, text="Delete selected", command=self.delete_selected).pack(side="left", padx=3)
        self.lbl = tk.Label(bar, text=""); self.lbl.pack(side="left", padx=8)

        body = tk.Frame(root); body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="gray20", cursor="cross")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_up)

        right = tk.Frame(body); right.pack(side="right", fill="y")
        tk.Label(right, text="Components").pack()
        self.listbox = tk.Listbox(right, width=30, height=24)
        self.listbox.pack(fill="y", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._load_existing()

        if use_camera:
            try:
                from camera_mv import Camera
                self.cam = Camera()
                name = self.cam.open()
                self.lbl.config(text="Camera: " + name)
                self.start_live()
            except Exception as e:
                self.cam = None
                self.lbl.config(text="Camera loi -> dung anh tinh: " + str(e))
                self.load_image(image_path)
        else:
            self.load_image(image_path)

    # ---------- live ----------
    def toggle_live(self):
        if self.cam is None:
            messagebox.showinfo("Live", "Khong co camera. Dung Open image...")
            return
        if self.live:
            self.stop_live()
        else:
            self.start_live()

    def start_live(self):
        self.live = True
        self.btn_live.config(text="Freeze", relief="sunken")
        self._tick()

    def stop_live(self):
        self.live = False
        self.btn_live.config(text="Live", relief="raised")

    def _tick(self):
        if not self.live or self.cam is None:
            return
        try:
            _, rgb = self.cam.grab()
            self._show_array(rgb)
        except Exception:
            pass
        self.root.after(30, self._tick)

    def _maybe_normalize(self, rgb):
        """Neu bat 'Chuan hoa board': nan board ve khung chuan (canonical)."""
        if not self.normalize.get():
            return rgb
        try:
            import cv2
            from segment_board import normalize_board
            r = normalize_board(np.ascontiguousarray(rgb[:, :, ::-1]))
            if r is not None:
                return cv2.cvtColor(r[1], cv2.COLOR_BGR2RGB)
        except Exception:
            pass
        return rgb

    def _show_array(self, rgb):
        self.img = Image.fromarray(self._maybe_normalize(rgb)).convert("RGB")
        self._render()

    # ---------- data ----------
    def _cfg_path(self):
        return os.path.join(self.lib_dir, CONFIG_NAME)

    def _load_existing(self):
        os.makedirs(self.lib_dir, exist_ok=True)
        p = self._cfg_path()
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        self._refresh_list()

    def _save_config(self):
        with open(self._cfg_path(), "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for n in sorted(self.config):
            c = self.config[n]
            rot = "180" if c.get("angle", 0) >= 180 else "-"
            self.listbox.insert("end", f'{n}  s{c.get("score"):.2f} exp{c.get("expected",1)} rot{rot}')
        self.lbl.config(text=f"{self.lbl.cget('text').split('  |')[0]}  |  Lib: {os.path.basename(self.lib_dir)} ({len(self.config)})")

    # ---------- image ----------
    def _render(self):
        if self.img is None:
            return
        w, h = self.img.size
        self.scale = min(MAX_VIEW[0] / w, MAX_VIEW[1] / h, 1.0)
        disp = self.img.resize((int(w * self.scale), int(h * self.scale)))
        self.tkimg = ImageTk.PhotoImage(disp)
        self.canvas.config(width=disp.width, height=disp.height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tkimg)

    def load_image(self, path):
        if not path or not os.path.isfile(path):
            return
        self.stop_live()
        rgb = np.asarray(Image.open(path).convert("RGB"))
        self.img = Image.fromarray(self._maybe_normalize(rgb)).convert("RGB")
        self._render()

    def open_image(self):
        p = filedialog.askopenfilename(
            initialdir=os.path.join(HERE, "mindvision_python"),
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"), ("All", "*.*")])
        if p:
            self.load_image(p)

    def choose_lib(self):
        p = filedialog.askdirectory(initialdir=self.lib_dir)
        if p:
            self.lib_dir = p
            self.config = {}
            self._load_existing()

    # ---------- ve khung ----------
    def on_down(self, e):
        if self.live:
            self.stop_live()           # tu dong dung hinh khi bat dau ve
        self.start = (e.x, e.y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def on_move(self, e):
        if self.start and self.rect_id:
            self.canvas.coords(self.rect_id, self.start[0], self.start[1], e.x, e.y)

    def on_up(self, e):
        if not self.start or self.img is None:
            return
        x0, y0 = self.start; x1, y1 = e.x, e.y
        self.start = None
        bx0, bx1 = sorted((x0, x1)); by0, by1 = sorted((y0, y1))
        if bx1 - bx0 < 5 or by1 - by0 < 5:
            return
        ix0, iy0 = int(bx0 / self.scale), int(by0 / self.scale)
        ix1, iy1 = int(bx1 / self.scale), int(by1 / self.scale)

        dlg = AddDialog(self.root)
        self.root.wait_window(dlg)
        if not dlg.result:
            if self.rect_id:
                self.canvas.delete(self.rect_id); self.rect_id = None
            return
        r = dlg.result
        name = r.pop("name")
        patch = self.img.crop((ix0, iy0, ix1, iy1)).convert("L")
        os.makedirs(self.lib_dir, exist_ok=True)
        patch.save(os.path.join(self.lib_dir, f"{name}.png"))
        self.config[name] = r
        self._save_config()
        self._refresh_list()
        self.canvas.create_text(bx0 + 2, by0 - 8, anchor="w", text=name, fill="yellow")
        self.rect_id = None

    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = sorted(self.config)[sel[0]]
        if not messagebox.askyesno("Xoa", f"Xoa linh kien '{name}'?"):
            return
        self.config.pop(name, None)
        png = os.path.join(self.lib_dir, f"{name}.png")
        if os.path.isfile(png):
            os.remove(png)
        self._save_config()
        self._refresh_list()

    def on_close(self):
        self.stop_live()
        try:
            if self.cam:
                self.cam.close()
        finally:
            self.root.destroy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--lib", default=DEFAULT_LIB)
    ap.add_argument("--no-camera", action="store_true", help="dung anh tinh, khong mo camera")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    root = tk.Tk()
    app = TeachApp(root, args.image, args.lib,
                   use_camera=(not args.no_camera and not args.selftest))
    if args.selftest:
        root.update()
        print("selftest OK; lib:", app.lib_dir, "components:", len(app.config))
        root.destroy(); return
    root.mainloop()


if __name__ == "__main__":
    main()
