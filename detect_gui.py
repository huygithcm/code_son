#coding=utf-8
"""Giao dien kiem tra linh kien: co LIVE VIEW va nut "Chup & Detect". Moi lan Detect
se chup 1 frame, chay template matching (fpm) tren thu vien templates_board, ve ket qua
+ bang found/expected (PASS/FAIL). Nguong score / goc xoay 180 do lay tu components.json
(dat trong teach_board.py).

Chay (venv co san fpm cua fpm_core):
    fpm_core\\.venv\\Scripts\\python.exe detect_gui.py
"""
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "fpm_core"))

from camera_mv import Camera, mvsdk          # noqa: E402
from component_detector import ComponentLibrary  # noqa: E402 (tu import fpm)
from segment_board import board_bbox, normalize_board  # noqa: E402 (auto tach board)
from hsv_tuner import HSVTuner                # noqa: E402

DEFAULT_LIB = os.path.join(HERE, "fpm_core", "templates_board")
DISP_W = 900           # be rong hien thi (resize bang cv2 cho nhanh, it RAM)
DETECT_EVERY = 3       # che do lien tuc: detect moi N frame
LOOP_MS = 20           # nhip vong lap (~50fps toi da) -> khong chiem het CPU


class DetectApp:
    def __init__(self, root, lib_dir):
        self.root = root
        self.lib_dir = lib_dir
        self.cam = Camera()
        self.lib = None
        self.tkimg = None
        self.live = False
        self.roi = None            # (x0,y0,x1,y1) toa do full-res; None = toan anh
        self._disp_scale = 1.0
        self._drag = None
        self._roi_tmp = None
        self.frame_i = 0
        self._fps = 0.0

        root.title("Kiem tra linh kien - MindVision + fpm")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        bar = tk.Frame(root); bar.pack(fill="x")
        self.btn = tk.Button(bar, text="Chup & Detect", command=self.detect,
                             bg="#2e7d32", fg="white", font=("Segoe UI", 11, "bold"))
        self.btn.pack(side="left", padx=4, pady=4)
        self.btn_live = tk.Button(bar, text="Live", width=8, command=self.toggle_live)
        self.btn_live.pack(side="left", padx=4)
        self.cont = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Detect lien tuc", variable=self.cont).pack(side="left", padx=4)
        self.normalize = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="Chuan hoa board", variable=self.normalize).pack(side="left", padx=4)
        tk.Button(bar, text="Auto board ROI", command=self.auto_roi).pack(side="left", padx=4)
        tk.Button(bar, text="HSV tuner", command=self.open_hsv).pack(side="left", padx=4)
        tk.Button(bar, text="Clear ROI", command=self.clear_roi).pack(side="left", padx=4)
        self.gray_fps = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Gray (FPS cao)", variable=self.gray_fps,
                       command=self.toggle_gray).pack(side="left", padx=4)
        tk.Button(bar, text="Reload library", command=self.reload_lib).pack(side="left", padx=4)
        tk.Button(bar, text="Library folder...", command=self.choose_lib).pack(side="left", padx=4)
        self.status = tk.Label(bar, text=""); self.status.pack(side="left", padx=8)

        body = tk.Frame(root); body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="gray20", cursor="cross")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_up)

        right = tk.Frame(body); right.pack(side="right", fill="y")
        self.tree = ttk.Treeview(right, columns=("score", "thr", "found", "exp", "st"),
                                 show="tree headings", height=18)
        self.tree.heading("#0", text="Component"); self.tree.column("#0", width=110)
        for c, t, w in (("score", "best", 55), ("thr", "nguong", 60),
                        ("found", "found", 55), ("exp", "exp", 45), ("st", "status", 60)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="y", expand=True)
        self.tree.tag_configure("PASS", background="#c8e6c9")
        self.tree.tag_configure("FAIL", background="#ffcdd2")
        self.tree.bind("<<TreeviewSelect>>", self._on_pick)
        self.total = tk.Label(right, text="", font=("Segoe UI", 11, "bold")); self.total.pack(pady=2)

        # --- chinh nguong/so luong cho TUNG linh kien ---
        tune = tk.LabelFrame(right, text="Chinh nguong tung linh kien", padx=6, pady=6)
        tune.pack(fill="x", pady=4)
        self.sel_name = tk.StringVar(value="")
        self.sel_score = tk.DoubleVar(value=0.70)
        self.sel_exp = tk.IntVar(value=1)
        self.sel_rot = tk.BooleanVar(value=False)
        self.cbo = ttk.Combobox(tune, textvariable=self.sel_name, state="readonly", width=18)
        self.cbo.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        self.cbo.bind("<<ComboboxSelected>>", lambda e: self._load_sel())
        tk.Label(tune, text="Score nguong:").grid(row=1, column=0, sticky="e")
        tk.Spinbox(tune, from_=0.1, to=1.0, increment=0.05, textvariable=self.sel_score,
                   width=7, format="%.2f").grid(row=1, column=1, sticky="w")
        tk.Label(tune, text="So luong:").grid(row=2, column=0, sticky="e")
        tk.Spinbox(tune, from_=1, to=50, textvariable=self.sel_exp, width=7).grid(
            row=2, column=1, sticky="w")
        tk.Checkbutton(tune, text="Xoay 180 do", variable=self.sel_rot).grid(
            row=3, column=0, columnspan=2, sticky="w")
        tk.Button(tune, text="Luu nguong", command=self.save_threshold).grid(
            row=4, column=0, columnspan=2, pady=(4, 0), sticky="we")

        self._init_camera()
        self.reload_lib()

    # ---------- chinh nguong tung linh kien ----------
    def _on_pick(self, _=None):
        sel = self.tree.selection()
        if sel:
            name = self.tree.item(sel[0], "text")
            self.sel_name.set(name); self._load_sel()

    def _load_sel(self):
        name = self.sel_name.get()
        if not self.lib or name not in self.lib.components:
            return
        cfg = self.lib.components[name].cfg
        self.sel_score.set(round(float(cfg.get("score", 0.7)), 2))
        self.sel_exp.set(int(cfg.get("expected", 1)))
        self.sel_rot.set(float(cfg.get("angle", 0)) >= 180)

    def save_threshold(self):
        name = self.sel_name.get()
        if not self.lib or name not in self.lib.components:
            messagebox.showwarning("Chinh nguong", "Chon linh kien truoc."); return
        comp = self.lib.components[name]
        comp.cfg["score"] = round(float(self.sel_score.get()), 3)
        comp.cfg["expected"] = int(self.sel_exp.get())
        new_angle = 180 if self.sel_rot.get() else 10
        relearn = (float(comp.cfg.get("angle", 0)) != new_angle)
        comp.cfg["angle"] = new_angle
        self.lib.save_config()
        if relearn:
            comp._learn()          # angle doi -> learn lai template
        self.status.config(text=f"Da luu nguong {name}: score={comp.cfg['score']} "
                                f"exp={comp.cfg['expected']} angle={new_angle}")

    def _init_camera(self):
        try:
            name = self.cam.open()
            self.status.config(text="Camera: " + name)
            self.start_live()
        except Exception as e:
            self.status.config(text="Camera loi: " + str(e))
            messagebox.showerror("Camera", str(e))

    # ---------- live ----------
    def toggle_live(self):
        if self.cam.h is None:
            return
        self.stop_live() if self.live else self.start_live()

    def start_live(self):
        self.live = True
        self.btn_live.config(text="Stop", relief="sunken")
        self._tick()

    def stop_live(self):
        self.live = False
        self.btn_live.config(text="Live", relief="raised")

    def _tick(self):
        if not self.live or self.cam.h is None:
            return
        try:
            t0 = time.time()
            gray, rgb = self.cam.grab()
            items = None
            disp = rgb
            if self.cont.get() and self.lib and self.lib.components:
                self.frame_i += 1
                if self.frame_i % DETECT_EVERY == 0:
                    det_gray, ox, oy, disp = self._prep(gray, rgb)
                    dets, disp = self._detect_image(det_gray, disp)
                    items = self._run_detect(dets, ox, oy)
            elif self.normalize.get():
                r = normalize_board(np.ascontiguousarray(rgb[:, :, ::-1]))
                if r is not None:
                    disp = np.ascontiguousarray(r[1][:, :, ::-1])
            self._render(disp, items)
            dt = time.time() - t0
            self._fps = 0.9 * getattr(self, "_fps", 0.0) + 0.1 * (1.0 / dt if dt > 0 else 0)
            base = self.status.cget("text").split("  |FPS")[0]
            self.status.config(text=f"{base}  |FPS {self._fps:.1f}")
        except Exception:
            pass
        self.root.after(LOOP_MS, self._tick)

    def _render(self, rgb, items=None):
        """Resize bang cv2 (nhanh, it RAM) roi ve ket qua tren anh NHO."""
        h, w = rgb.shape[:2]
        s = min(DISP_W / w, 1.0)
        self._disp_scale = s
        disp = cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        disp = np.ascontiguousarray(disp)
        if items:
            for name, score, corners, center in items:
                pts = np.array([[int(px * s), int(py * s)] for px, py in corners], np.int32)
                cv2.polylines(disp, [pts], True, (255, 0, 0), 2)
                cv2.putText(disp, f"{name} {score:.2f}",
                            (int(center[0] * s) + 4, int(center[1] * s) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        self.tkimg = ImageTk.PhotoImage(Image.fromarray(disp))
        self.canvas.config(width=disp.shape[1], height=disp.shape[0])
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tkimg)
        if self.roi:
            x0, y0, x1, y1 = [int(v * s) for v in self.roi]
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#00e5ff", width=2, dash=(6, 4))

    # ---------- ROI ----------
    def on_down(self, e):
        if self.live:
            self.stop_live()
        self._drag = (e.x, e.y)
        if self._roi_tmp:
            self.canvas.delete(self._roi_tmp)
        self._roi_tmp = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                     outline="#00e5ff", width=2)

    def on_move(self, e):
        if self._drag and self._roi_tmp:
            self.canvas.coords(self._roi_tmp, self._drag[0], self._drag[1], e.x, e.y)

    def on_up(self, e):
        if not self._drag:
            return
        x0, y0 = self._drag; x1, y1 = e.x, e.y
        self._drag = None
        bx0, bx1 = sorted((x0, x1)); by0, by1 = sorted((y0, y1))
        if bx1 - bx0 < 8 or by1 - by0 < 8:
            return
        s = self._disp_scale or 1.0
        self.roi = (int(bx0 / s), int(by0 / s), int(bx1 / s), int(by1 / s))
        self.status.config(text=f"ROI = {self.roi}")

    def clear_roi(self):
        self.roi = None
        self._roi_tmp = None
        self.status.config(text="ROI: toan anh")

    def toggle_gray(self):
        """Chuyen camera sang MONO8 (FPS cao hon) hoac ve mau."""
        if self.cam.h is None:
            return
        was_live = self.live
        self.stop_live()
        try:
            self.cam.reopen(force_mono=self.gray_fps.get())
        except Exception as e:
            messagebox.showerror("Camera", str(e)); return
        self.status.config(text=("Mode: GRAY/MONO (FPS cao)" if self.gray_fps.get()
                                 else "Mode: mau"))
        if was_live:
            self.start_live()

    def open_hsv(self):
        """Mo HSV tuner tren 1 frame mau de chinh nguong tach board."""
        if self.cam.h is None:
            return
        if self.cam.mono:
            messagebox.showinfo("HSV tuner", "Dang o che do GRAY/MONO -> khong co mau. "
                                "Tat 'Gray (FPS cao)' de chinh HSV."); return
        self.stop_live()
        try:
            _, rgb = self.cam.grab()
        except mvsdk.CameraException as e:
            messagebox.showerror("Grab", e.message); return
        HSVTuner(self.root, np.ascontiguousarray(rgb[:, :, ::-1]))

    def auto_roi(self):
        """Tu dong tach board (OpenCV) -> dat ROI quanh board."""
        if self.cam.h is None:
            return
        self.stop_live()
        try:
            _, rgb = self.cam.grab()
        except mvsdk.CameraException as e:
            messagebox.showerror("Grab", e.message); return
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        bb = board_bbox(bgr, margin=45)   # margin rong de khong cat linh kien o mep board
        if bb is None:
            messagebox.showwarning("Auto ROI", "Khong tach duoc board."); return
        x, y, w, h = bb
        self.roi = (x, y, x + w, y + h)
        self.status.config(text=f"Auto board ROI = {self.roi}")
        self._render(rgb)

    # ---------- library ----------
    def choose_lib(self):
        p = filedialog.askdirectory(initialdir=self.lib_dir)
        if p:
            self.lib_dir = p; self.reload_lib()

    def reload_lib(self):
        try:
            self.lib = ComponentLibrary(self.lib_dir).load()
            n = len(self.lib.components)
            base = self.status.cget("text").split("  |")[0]
            self.status.config(text=f"{base}  |  Lib: {n} linh kien")
            names = sorted(self.lib.components)
            self.cbo["values"] = names
            if names:
                if self.sel_name.get() not in names:
                    self.sel_name.set(names[0])
                self._load_sel()
            if n == 0:
                messagebox.showwarning("Library", "Thu vien rong. Dung teach_board.py de tao truoc.")
        except Exception as e:
            messagebox.showerror("Library", str(e))

    # ---------- detect ----------
    def _prep(self, gray, rgb):
        """Chuan bi anh de detect + anh de hien thi.
        - Chuan hoa board: nan board ve canonical -> det tren canonical, hien canonical.
        - Khong: cat theo ROI (neu co), hien anh goc."""
        if self.normalize.get():
            r = normalize_board(np.ascontiguousarray(rgb[:, :, ::-1]))
            if r is not None:
                gray_c, bgr_c = r
                return gray_c, 0, 0, np.ascontiguousarray(bgr_c[:, :, ::-1])
            # khong tach duoc board -> fallback toan anh
            return gray, 0, 0, rgb
        if self.roi:
            x0, y0, x1, y1 = self.roi
            x0 = max(0, x0); y0 = max(0, y0)
            x1 = min(gray.shape[1], x1); y1 = min(gray.shape[0], y1)
            return gray[y0:y1, x0:x1], x0, y0, rgb
        return gray, 0, 0, rgb

    def _detect_image(self, det_gray, disp):
        """Detect (tu chon huong khi chuan hoa) -> (dets, disp da xoay neu can)."""
        if self.normalize.get():
            dets, flipped = self.lib.detect_oriented(det_gray)
            if flipped:
                disp = cv2.rotate(disp, cv2.ROTATE_180)
            return dets, disp
        return self.lib.detect(det_gray), disp

    def _run_detect(self, dets, ox=0, oy=0):
        """Cap nhat bang tu ket qua dets, tra ve items (toa do + offset) de ve."""
        expected = self.lib.expected_counts()
        counts = {n: 0 for n in self.lib.components}
        best = {n: 0.0 for n in self.lib.components}
        items = []
        for r in dets:
            counts[r["name"]] += 1
            best[r["name"]] = max(best[r["name"]], r["score"])
            items.append((r["name"], r["score"],
                          [(p[0] + ox, p[1] + oy) for p in r["corners"]],
                          (r["center"][0] + ox, r["center"][1] + oy)))

        for i in self.tree.get_children():
            self.tree.delete(i)
        ok_all = True
        for name in sorted(self.lib.components):
            found, exp = counts[name], expected[name]
            thr = self.lib.components[name].cfg.get("score", 0.7)
            ok = found >= exp; ok_all &= ok
            self.tree.insert("", "end", text=name,
                             values=(f"{best[name]:.2f}", f"{thr:.2f}", found, exp,
                                     "PASS" if ok else "FAIL"),
                             tags=(("PASS" if ok else "FAIL"),))
        self.total.config(text=("TONG: PASS" if ok_all else "TONG: FAIL"),
                          fg=("#2e7d32" if ok_all else "#c62828"))
        return items

    def detect(self):
        if self.cam.h is None:
            messagebox.showerror("Camera", "Camera chua mo."); return
        if not self.lib or not self.lib.components:
            messagebox.showwarning("Library", "Chua co template. Tao bang teach_board.py."); return
        self.stop_live()
        try:
            gray, rgb = self.cam.grab()
        except mvsdk.CameraException as e:
            messagebox.showerror("Grab", e.message); return
        det_gray, ox, oy, disp = self._prep(gray, rgb)
        dets, disp = self._detect_image(det_gray, disp)
        items = self._run_detect(dets, ox, oy)
        self._render(disp, items)

    def on_close(self):
        self.stop_live()
        try:
            self.cam.close()
        finally:
            self.root.destroy()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=DEFAULT_LIB)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    root = tk.Tk()
    if args.selftest:
        Camera.open = lambda self: "SELFTEST"
        Camera.grab = lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("no grab"))
    app = DetectApp(root, args.lib)
    if args.selftest:
        root.update()
        print("selftest OK; lib components:", len(app.lib.components) if app.lib else 0)
        root.destroy(); return
    root.mainloop()


if __name__ == "__main__":
    main()
