#coding=utf-8
"""Tien xu ly + CHUAN HOA NGUON SANG truoc khi template matching, de matching giua
'data' (template chup luc teach) va 'anh thuc te' (luc detect) on dinh du anh sang khac.

QUAN TRONG: phep xu ly phai "crop-consistent" -> cho ket qua giong nhau cho mot vung
du vung do nam trong frame lon hay la template cat rieng. Vi vay chi dung TOAN TU CUC BO
(Gaussian/Sobel theo lan can), KHONG dung CLAHE/histogram-equalization (chuan hoa theo
toan anh -> template & frame bi xu ly khac nhau).

Cac mode (FPM_PP_MODE):
  "localnorm" (MAC DINH): chuan hoa anh sang/tuong phan CUC BO (I - mean_local)/std_local
       -> khu gradient anh sang nen (chieu sang khong deu, bong do), on dinh nhat giua
       data va anh thuc. NCC von da bat bien voi sang tuyen tinh, localnorm xu ly them
       phan sang CUC BO/phi tuyen ma NCC khong tu lo duoc.
  "localnorm+gradient": chuan hoa sang cuc bo roi lay bien canh.
  "gradient"  : blur nhe + Sobel magnitude (bien canh).
  "blur"      : chi lam min.
  "none"      : khong xu ly (chi dua vao tinh bat bien sang cua NCC).

Bien moi truong:
  FPM_PP_MODE  : nhu tren (mac dinh "localnorm")
  FPM_PP_SIGMA : ban kinh (sigma) uoc luong anh sang nen cho localnorm (mac dinh 21)
  FPM_PP_BLUR  : kich thuoc Gaussian lam min (so le, mac dinh 3; <3 = tat)
"""
import os
import cv2
import numpy as np

_MODE = os.environ.get("FPM_PP_MODE", "localnorm").lower()
_SIGMA = float(os.environ.get("FPM_PP_SIGMA", "21"))
_BLUR = int(os.environ.get("FPM_PP_BLUR", "3"))


def _smooth(g):
    if _BLUR >= 3 and _BLUR % 2 == 1:
        return cv2.GaussianBlur(g, (_BLUR, _BLUR), 0)
    return g


def _localnorm(g):
    """Chuan hoa anh sang/tuong phan cuc bo: (I - mean_local) / std_local.
    Loai bo gradient anh sang nen (chieu sang khong deu) -> ben voi nguon sang.
    Cuc bo nen crop-consistent (tru vien)."""
    f = g.astype(np.float32)
    mean = cv2.GaussianBlur(f, (0, 0), _SIGMA)
    diff = f - mean
    var = cv2.GaussianBlur(diff * diff, (0, 0), _SIGMA)
    std = np.sqrt(np.maximum(var, 0.0)) + 1.0
    out = diff / std
    out = np.clip(out * 40.0 + 128.0, 0, 255)
    return out.astype(np.uint8)


def _gradient(g):
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    out = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX)
    return out.astype(np.uint8)


def preprocess(gray):
    """gray uint8 (H,W) -> gray uint8 (H,W) da chuan hoa sang + tien xu ly."""
    g = np.ascontiguousarray(gray)
    if g.ndim == 3:
        g = cv2.cvtColor(g, cv2.COLOR_RGB2GRAY)
    g = g.astype(np.uint8, copy=False)

    if _MODE == "none":
        return g

    g = _smooth(g)
    if _MODE == "blur":
        pass
    elif _MODE == "localnorm":
        g = _localnorm(g)
    elif _MODE == "gradient":
        g = _gradient(g)
    else:  # "localnorm+gradient"
        g = _gradient(_localnorm(g))
    return np.ascontiguousarray(g, dtype=np.uint8)
