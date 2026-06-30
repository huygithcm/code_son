#coding=utf-8
"""Chup loat anh tu camera MindVision de tao dataset train YOLO detect board.

Dung tkinter (giong detect_gui.py) vi OpenCV trong venv la ban headless (khong
co cv2.imshow). Cua so co LIVE VIEW + cac nut/ phim tat.

Dieu khien:
    nut "Luu (Space)" hoac phim SPACE / s : luu frame hien tai
    nut "Auto" hoac phim a                : bat/tat tu dong luu moi N frame
    q / ESC / dong cua so                 : thoat

Anh luu vao yolo_board/dataset/images/ dat ten board_XXXX.jpg (anh GOC full-res).

Meo lay data DA DANG (quan trong hon so luong):
  - di chuyen board: goc, giua, mep khung hinh; xoay nhieu goc
  - doi anh sang: sang/toi, co bong, phan quang; doi khoang cach to<->nho
  - board co/khong linh kien, board loi (neu can)
Muc tieu ~100-150 anh da dang la du cho 1 class 'board'.

Chay:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\capture_dataset.py
    ... --auto-every 15
    ... --out yolo_board\\dataset\\images
"""
import os
import sys
import glob
import argparse

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)                       # de import camera_mv

from camera_mv import Camera, mvsdk            # noqa: E402

DEFAULT_OUT = os.path.join(HERE, "dataset", "images")
DISP_W = 1000
LOOP_MS = 30


def next_index(out_dir):
    """Tiep tuc danh so sau cac anh board_XXXX.jpg da co (khong ghi de)."""
    mx = -1
    for p in glob.glob(os.path.join(out_dir, "board_*.jpg")):
        stem = os.path.splitext(os.path.basename(p))[0]
        try:
            mx = max(mx, int(stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return mx + 1


class CaptureApp:
    def __init__(self, root, out_dir, auto_every):
        self.root = root
        self.out_dir = out_dir
        self.auto_every = auto_every
        self.idx = next_index(out_dir)
        self.saved = 0
        self.frame_i = 0
        self.auto = False
        self.last_frame = None          # bgr full-res hien tai
        self.tkimg = None

        self.cam = Camera()
        root.title("Capture dataset (YOLO board)")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        bar = tk.Frame(root); bar.pack(fill="x")
        tk.Button(bar, text="Luu (Space)", command=self.save_frame,
                  bg="#2e7d32", fg="white", font=("Segoe UI", 11, "bold")).pack(side="left", padx=4, pady=4)
        self.btn_auto = tk.Button(bar, text="Auto: off", width=10, command=self.toggle_auto)
        self.btn_auto.pack(side="left", padx=4)
        self.status = tk.Label(bar, text=""); self.status.pack(side="left", padx=8)

        self.canvas = tk.Canvas(root, bg="gray20")
        self.canvas.pack(fill="both", expand=True)

        for k in ("<space>", "s", "S"):
            root.bind(k, lambda e: self.save_frame())
        for k in ("a", "A"):
            root.bind(k, lambda e: self.toggle_auto())
        for k in ("q", "Q", "<Escape>"):
            root.bind(k, lambda e: self.on_close())

        try:
            name = self.cam.open()
            self.set_status(f"Camera: {name}")
        except Exception as e:
            self.set_status("Camera loi: " + str(e))
        self._tick()

    def set_status(self, msg=None):
        base = msg if msg is not None else getattr(self, "_base", "")
        if msg is not None:
            self._base = msg
        self.status.config(
            text=f"{getattr(self, '_base', '')}  |  saved={self.saved}  "
                 f"next=board_{self.idx:04d}  AUTO={'ON' if self.auto else 'off'}")

    def toggle_auto(self):
        self.auto = not self.auto
        self.btn_auto.config(text=f"Auto: {'ON' if self.auto else 'off'}",
                             relief="sunken" if self.auto else "raised")
        self.set_status()

    def save_frame(self):
        if self.last_frame is None:
            return
        fn = os.path.join(self.out_dir, f"board_{self.idx:04d}.jpg")
        cv2.imwrite(fn, self.last_frame)
        print("da luu", fn)
        self.idx += 1
        self.saved += 1
        self.set_status()

    def _tick(self):
        if self.cam.h is None:
            return
        try:
            _, rgb = self.cam.grab()
            self.last_frame = np.ascontiguousarray(rgb[:, :, ::-1])   # bgr full-res
            self.frame_i += 1
            if self.auto and self.frame_i % self.auto_every == 0:
                self.save_frame()
            self._render(rgb)
        except mvsdk.CameraException as e:
            self.set_status("Grab loi: " + e.message)
        self.root.after(LOOP_MS, self._tick)

    def _render(self, rgb):
        h, w = rgb.shape[:2]
        s = min(DISP_W / w, 1.0)
        disp = cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        disp = np.ascontiguousarray(disp)
        self.tkimg = ImageTk.PhotoImage(Image.fromarray(disp))
        self.canvas.config(width=disp.shape[1], height=disp.shape[0])
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tkimg)

    def on_close(self):
        try:
            self.cam.close()
        finally:
            print(f"\nXong. Da luu {self.saved} anh vao {self.out_dir}")
            self.root.destroy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT, help="thu muc luu anh")
    ap.add_argument("--auto-every", type=int, default=15,
                    help="auto-capture: luu moi N frame khi bat che do auto")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    print(f"Luu vao: {args.out}")
    print("SPACE/s=luu  a=auto on/off  q/ESC=thoat")

    root = tk.Tk()
    CaptureApp(root, args.out, args.auto_every)
    root.mainloop()


if __name__ == "__main__":
    main()
