#coding=utf-8
"""HSV tuner (Tkinter): chinh nguong HSV de tach board/ROI bang OpenCV, xem mask truc
tiep. Apply -> ghi nguong vao segment_board (set_hsv) cho auto board ROI dung.

Dung trong detect_gui / stream_detect:
    from hsv_tuner import HSVTuner
    HSVTuner(parent, bgr_frame, on_apply=callback)
"""
import numpy as np
import cv2
import tkinter as tk
from PIL import Image, ImageTk

import segment_board

PREVIEW_W = 520


class HSVTuner(tk.Toplevel):
    def __init__(self, parent, bgr, on_apply=None):
        super().__init__(parent)
        self.title("HSV tuner - tach board/ROI")
        self.bgr = bgr
        self.on_apply = on_apply
        h, w = bgr.shape[:2]
        self.s = PREVIEW_W / w
        self.small = cv2.resize(bgr, (PREVIEW_W, int(h * self.s)))

        self.vars = {}
        specs = [("H lo", segment_board.HSV_LO[0], 179), ("H hi", segment_board.HSV_HI[0], 179),
                 ("S lo", segment_board.HSV_LO[1], 255), ("S hi", segment_board.HSV_HI[1], 255),
                 ("V lo", segment_board.HSV_LO[2], 255), ("V hi", segment_board.HSV_HI[2], 255)]

        ctrl = tk.Frame(self, padx=8, pady=8); ctrl.pack(side="left", fill="y")
        for i, (name, val, mx) in enumerate(specs):
            tk.Label(ctrl, text=name, width=5, anchor="e").grid(row=i, column=0)
            v = tk.IntVar(value=int(val))
            self.vars[name] = v
            tk.Scale(ctrl, from_=0, to=mx, orient="horizontal", length=240,
                     variable=v, command=lambda e: self._update()).grid(row=i, column=1)

        self.view_mode = tk.StringVar(value="mask")
        tk.Radiobutton(ctrl, text="Mask", variable=self.view_mode, value="mask",
                       command=self._update).grid(row=6, column=0, columnspan=2, sticky="w")
        tk.Radiobutton(ctrl, text="Anh loc (overlay)", variable=self.view_mode, value="overlay",
                       command=self._update).grid(row=7, column=0, columnspan=2, sticky="w")
        self.info = tk.Label(ctrl, text=""); self.info.grid(row=8, column=0, columnspan=2, pady=4)
        tk.Button(ctrl, text="Apply (luu nguong)", command=self._apply,
                  bg="#2e7d32", fg="white").grid(row=9, column=0, columnspan=2, sticky="we", pady=4)

        self.canvas = tk.Label(self); self.canvas.pack(side="right", padx=6, pady=6)
        self.transient(parent)
        self._update()

    def _lohi(self):
        lo = [self.vars["H lo"].get(), self.vars["S lo"].get(), self.vars["V lo"].get()]
        hi = [self.vars["H hi"].get(), self.vars["S hi"].get(), self.vars["V hi"].get()]
        return lo, hi

    def _update(self, *_):
        lo, hi = self._lohi()
        mask = segment_board.hsv_mask(self.small, lo, hi)
        # uoc luong bbox board tu mask (xem co tach duoc khong)
        cnt = segment_board.board_hull(
            cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)), iterations=2))
        if self.view_mode.get() == "mask":
            disp = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
        else:
            rgb = self.small[:, :, ::-1].copy()
            rgb[mask == 0] = (rgb[mask == 0] * 0.25).astype(np.uint8)
            disp = rgb
        if cnt is not None:
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(disp, (x, y), (x + w, y + h), (0, 229, 255), 2)
            self.info.config(text=f"bbox ~ {int(x/self.s)},{int(y/self.s)} "
                                  f"{int(w/self.s)}x{int(h/self.s)}")
        else:
            self.info.config(text="Chua tach duoc board")
        self.tk_im = ImageTk.PhotoImage(Image.fromarray(np.ascontiguousarray(disp)))
        self.canvas.config(image=self.tk_im)

    def _apply(self):
        lo, hi = self._lohi()
        segment_board.set_hsv(lo, hi)
        if self.on_apply:
            self.on_apply(lo, hi)
        self.destroy()
