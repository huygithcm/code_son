#coding=utf-8
"""Detect LIEN TUC tren day chuyen dang chay (board di chuyen qua khung hinh).

Luong:
  - Stream lien tuc tu camera MindVision.
  - Moi frame: tu tach board (OpenCV) -> neu CO board trong khung thi chay template
    matching (fpm) tren vung board, ve overlay + bang found/expected.
  - May trang thai dem MOI board 1 lan: khi board xuat hien -> theo doi, chon frame
    "day du nhat" (nhieu linh kien nhat); khi board roi khoi khung -> CHOT ket qua
    PASS/FAIL cho board do, tang bo dem, luu anh neu FAIL, ghi log CSV.

Chay:
    fpm_core\\.venv\\Scripts\\python.exe stream_detect.py
"""
import os
import sys
import csv
import time
import datetime as dt

import numpy as np
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "fpm_core"))

from camera_mv import Camera, mvsdk              # noqa: E402
from component_detector import ComponentLibrary  # noqa: E402
from segment_board import board_bbox             # noqa: E402

DEFAULT_LIB = os.path.join(HERE, "fpm_core", "templates_board")
FAIL_DIR = os.path.join(HERE, "stream_out", "fail")
LOG_CSV = os.path.join(HERE, "stream_out", "log.csv")
MAX_VIEW = (1000, 760)

PRESENT_AREA = 0.010      # board chiem > 1% khung -> coi nhu CO board
ABSENT_FRAMES = 6         # so frame vang lien tiep de chot board da roi khoi khung
DETECT_EVERY = 1          # detect moi N frame (tang de nhe CPU)


class StreamApp:
    def __init__(self, root, lib_dir):
        self.root = root
        self.lib_dir = lib_dir
        self.cam = Camera()
        self.lib = None
        self.tkimg = None
        self.running = False
        self.use_auto_roi = tk.BooleanVar(value=True)

        # may trang thai / bo dem
        self.state = "IDLE"           # IDLE | PRESENT
        self.absent = 0
        self.best_board = None        # dict ket qua "day du nhat" cua board hien tai
        self.n_pass = 0
        self.n_fail = 0
        self.frame_i = 0
        self._disp_scale = 1.0

        root.title("Stream detect - day chuyen")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        bar = tk.Frame(root); bar.pack(fill="x")
        self.btn = tk.Button(bar, text="Start", width=8, command=self.toggle,
                             bg="#2e7d32", fg="white", font=("Segoe UI", 11, "bold"))
        self.btn.pack(side="left", padx=4, pady=4)
        tk.Checkbutton(bar, text="Auto board ROI", variable=self.use_auto_roi).pack(side="left", padx=6)
        tk.Button(bar, text="Reset counters", command=self.reset_counters).pack(side="left", padx=4)
        tk.Button(bar, text="Reload library", command=self.reload_lib).pack(side="left", padx=4)
        self.status = tk.Label(bar, text=""); self.status.pack(side="left", padx=8)

        body = tk.Frame(root); body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="gray20"); self.canvas.pack(side="left", fill="both", expand=True)

        right = tk.Frame(body); right.pack(side="right", fill="y")
        self.banner = tk.Label(right, text="--", font=("Segoe UI", 20, "bold"), width=10)
        self.banner.pack(pady=4)
        self.counter = tk.Label(right, text="PASS 0 / FAIL 0", font=("Segoe UI", 13))
        self.counter.pack(pady=2)
        self.tree = ttk.Treeview(right, columns=("found", "exp", "st"), show="tree headings", height=18)
        self.tree.heading("#0", text="Component"); self.tree.column("#0", width=120)
        for c, t, w in (("found", "found", 55), ("exp", "exp", 45), ("st", "status", 65)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="y", expand=True)
        self.tree.tag_configure("PASS", background="#c8e6c9")
        self.tree.tag_configure("FAIL", background="#ffcdd2")

        os.makedirs(FAIL_DIR, exist_ok=True)
        self._init_log()
        self._init_camera()
        self.reload_lib()

    # ---------- setup ----------
    def _init_log(self):
        if not os.path.isfile(LOG_CSV):
            with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["time", "verdict", "detail"])

    def _init_camera(self):
        try:
            name = self.cam.open()
            self.status.config(text="Camera: " + name)
        except Exception as e:
            self.status.config(text="Camera loi: " + str(e))
            messagebox.showerror("Camera", str(e))

    def reload_lib(self):
        try:
            self.lib = ComponentLibrary(self.lib_dir).load()
            base = self.status.cget("text").split("  |")[0]
            self.status.config(text=f"{base}  |  Lib: {len(self.lib.components)} linh kien")
        except Exception as e:
            messagebox.showerror("Library", str(e))

    def reset_counters(self):
        self.n_pass = self.n_fail = 0
        self.counter.config(text="PASS 0 / FAIL 0")

    # ---------- stream ----------
    def toggle(self):
        if self.cam.h is None:
            return
        if self.running:
            self.running = False
            self.btn.config(text="Start", bg="#2e7d32")
        else:
            if not self.lib or not self.lib.components:
                messagebox.showwarning("Library", "Thu vien rong. Teach truoc."); return
            self.running = True
            self.btn.config(text="Stop", bg="#c62828")
            self._tick()

    def _tick(self):
        if not self.running or self.cam.h is None:
            return
        try:
            gray, rgb = self.cam.grab()
        except Exception:
            self.root.after(10, self._tick); return

        self.frame_i += 1
        H, W = gray.shape
        bb = board_bbox(np.ascontiguousarray(rgb[:, :, ::-1]), margin=15) if self.use_auto_roi.get() else None
        present = False
        if bb is not None:
            present = (bb[2] * bb[3]) > PRESENT_AREA * (W * H)
        elif not self.use_auto_roi.get():
            present = True   # khong dung auto-roi: luon detect toan khung

        vis = Image.fromarray(rgb).convert("RGB")
        d = ImageDraw.Draw(vis)

        if present and (self.frame_i % DETECT_EVERY == 0):
            res = self._detect(gray, bb)
            res["rgb"] = rgb
            self._draw(d, res, bb)
            self._update_table(res)
            # giu frame "day du nhat" (tong found lon nhat)
            if self.best_board is None or res["total_found"] > self.best_board["total_found"]:
                self.best_board = res
            self.state = "PRESENT"
            self.absent = 0
        else:
            if self.state == "PRESENT":
                self.absent += 1
                if self.absent >= ABSENT_FRAMES:
                    self._commit()        # board da roi khoi khung -> chot ket qua
        if bb is not None:
            x, y, w, h = bb
            d.rectangle((x, y, x + w, y + h), outline=(0, 229, 255), width=3)

        self._show(vis)
        self.root.after(1, self._tick)

    def _detect(self, gray, bb):
        if bb is not None:
            x, y, w, h = bb
            sub = gray[y:y + h, x:x + w]; ox, oy = x, y
        else:
            sub = gray; ox, oy = 0, 0
        dets = self.lib.detect(sub)
        expected = self.lib.expected_counts()
        counts = {n: 0 for n in self.lib.components}
        items = []
        for r in dets:
            counts[r["name"]] += 1
            items.append((r["name"], r["score"],
                          [(p[0] + ox, p[1] + oy) for p in r["corners"]],
                          (r["center"][0] + ox, r["center"][1] + oy)))
        ok_all = all(counts[n] >= expected[n] for n in self.lib.components)
        return {"counts": counts, "expected": expected, "items": items,
                "ok": ok_all, "total_found": sum(counts.values())}

    def _draw(self, d, res, bb):
        for name, score, corners, center in res["items"]:
            d.line([corners[0], corners[1], corners[2], corners[3], corners[0]],
                   fill=(255, 0, 0), width=4)
            d.text((center[0] + 6, center[1] - 6), f"{name} {score:.2f}", fill=(255, 255, 0))

    def _update_table(self, res):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for name in sorted(self.lib.components):
            f, e = res["counts"][name], res["expected"][name]
            ok = f >= e
            self.tree.insert("", "end", text=name, values=(f, e, "PASS" if ok else "FAIL"),
                             tags=(("PASS" if ok else "FAIL"),))
        self.banner.config(text="PASS" if res["ok"] else "FAIL",
                           fg="white", bg=("#2e7d32" if res["ok"] else "#c62828"))

    def _commit(self):
        """Chot ket qua cho board vua roi khoi khung."""
        res = self.best_board
        self.state = "IDLE"; self.absent = 0; self.best_board = None
        if res is None:
            return
        verdict = "PASS" if res["ok"] else "FAIL"
        if res["ok"]:
            self.n_pass += 1
        else:
            self.n_fail += 1
        self.counter.config(text=f"PASS {self.n_pass} / FAIL {self.n_fail}")
        detail = ",".join(f'{n}:{res["counts"][n]}/{res["expected"][n]}'
                          for n in sorted(self.lib.components))
        ts = dt.datetime.now()
        with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([ts.isoformat(timespec="seconds"), verdict, detail])
        if not res["ok"] and res.get("rgb") is not None:
            # luu anh board FAIL (kem khung) de truy vet
            vis = Image.fromarray(res["rgb"]).convert("RGB")
            dd = ImageDraw.Draw(vis)
            self._draw(dd, res, None)
            fn = os.path.join(FAIL_DIR, ts.strftime("fail_%Y%m%d_%H%M%S_%f.jpg"))
            vis.save(fn)

    def _show(self, pil_img):
        w, h = pil_img.size
        s = min(MAX_VIEW[0] / w, MAX_VIEW[1] / h, 1.0)
        self._disp_scale = s
        disp = pil_img.resize((int(w * s), int(h * s)))
        self.tkimg = ImageTk.PhotoImage(disp)
        self.canvas.config(width=disp.width, height=disp.height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tkimg)

    def on_close(self):
        self.running = False
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
    app = StreamApp(root, args.lib)
    if args.selftest:
        root.update()
        print("selftest OK; lib:", len(app.lib.components) if app.lib else 0)
        root.destroy(); return
    root.mainloop()


if __name__ == "__main__":
    main()
