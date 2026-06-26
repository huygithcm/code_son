#coding=utf-8
"""Tu dong tach board (module) ra khoi nen bang OpenCV, va danh gia tren nhieu anh.

Y tuong:
  1. HSV -> lam noi vung board. Board la PCB mau xanh duong -> nguong theo Hue/Sat.
     (du phong: neu mask xanh qua nho, fallback sang tach theo do tuong phan/canh.)
  2. Morphology (close+open) lam sach mask.
  3. Lay contour lon nhat -> minAreaRect (board nghieng) + bounding box.
  4. Xuat: overlay (ve rect), mask, anh board da cat & xoay thang (deskew).
  5. Danh gia: in bbox, goc, dien tich, ti le lap day (fill = area/bbox_area) cho moi
     anh + do on dinh giua cac anh.

Chay:
    fpm_core\\.venv\\Scripts\\python.exe segment_board.py
    fpm_core\\.venv\\Scripts\\python.exe segment_board.py --images mindvision_python/snap_000.jpg ...
"""
import os
import glob
import argparse

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "seg_out")


# Nguong HSV tach board (chinh duoc tu HSV tuner). board PCB xanh duong.
HSV_LO = [90, 60, 40]
HSV_HI = [140, 255, 255]


def set_hsv(lo, hi):
    """Cap nhat nguong HSV tach board (tu HSV tuner)."""
    global HSV_LO, HSV_HI
    HSV_LO = [int(v) for v in lo]
    HSV_HI = [int(v) for v in hi]


def hsv_mask(bgr, lo=None, hi=None):
    """Chi tra ve mask inRange theo HSV (cho HSV tuner xem truc tiep)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    blur = cv2.GaussianBlur(hsv, (5, 5), 0)
    lo = np.array(HSV_LO if lo is None else lo, np.uint8)
    hi = np.array(HSV_HI if hi is None else hi, np.uint8)
    return cv2.inRange(blur, lo, hi)


def board_mask(bgr):
    """Tra ve mask nhi phan vung board + phuong phap da dung."""
    mask = hsv_mask(bgr)

    # close manh de noi cac mang xanh bi linh kien cat vun thanh ca module
    k_big = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_big, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)

    method = "blue-hsv"
    if cv2.countNonZero(mask) < 0.005 * mask.size:
        # fallback: tach theo canh/Otsu tren anh xam (khi mau khong ro)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=3)
        method = "otsu-fallback"
    return mask, method


def board_hull(mask):
    """Gop tat ca mang lon thanh convex hull -> bao tron ca module (ke ca linh kien)."""
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    biggest = max(cv2.contourArea(c) for c in cnts)
    keep = [c for c in cnts if cv2.contourArea(c) > 0.15 * biggest]
    pts = np.vstack(keep)
    return cv2.convexHull(pts)


def board_bbox(bgr, margin=0, scale=0.5):
    """Tra ve bounding box truc-toa-do (x,y,w,h) cua board, hoac None.
    Dung cho auto-ROI. margin: noi rong bbox (px). scale<1: thu nho de chay nhanh."""
    H, W = bgr.shape[:2]
    if scale and scale < 1.0:
        small = cv2.resize(bgr, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)
        mask, _ = board_mask(small)
        cnt = board_hull(mask)
        if cnt is None:
            return None
        x, y, w, h = [int(v / scale) for v in cv2.boundingRect(cnt)]
    else:
        mask, _ = board_mask(bgr)
        cnt = board_hull(mask)
        if cnt is None:
            return None
        x, y, w, h = cv2.boundingRect(cnt)
    x0 = max(0, x - margin); y0 = max(0, y - margin)
    x1 = min(W, x + w + margin); y1 = min(H, y + h + margin)
    return (x0, y0, x1 - x0, y1 - y0)


def board_rect(bgr, scale=0.5):
    """minAreaRect cua board (toa do full-res), hoac None."""
    H, W = bgr.shape[:2]
    if scale and scale < 1.0:
        small = cv2.resize(bgr, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)
        cnt = board_hull(board_mask(small)[0])
        if cnt is None:
            return None
        (cx, cy), (w, h), a = cv2.minAreaRect((cnt.astype(np.float32) / scale).astype(np.int32))
        return ((cx, cy), (w, h), a)
    cnt = board_hull(board_mask(bgr)[0])
    return cv2.minAreaRect(cnt) if cnt is not None else None


# Kich thuoc board chuan (canonical) - teach va detect deu nan board ve kich thuoc nay
CANON_W = 360
CANON_H = 720


def normalize_board(bgr, cw=CANON_W, ch=CANON_H, scale=0.5):
    """Nan board ve khung chuan (cw x ch, portrait) -> bat bien vi tri/xoay/ti le.
    Tra ve (gray_canon, bgr_canon) hoac None."""
    rect = board_rect(bgr, scale)
    if rect is None:
        return None
    crop = deskew_crop(bgr, rect)        # cat + xoay thang (kich thuoc thay doi)
    if crop is None:
        return None
    canon = cv2.resize(crop, (cw, ch), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(canon, cv2.COLOR_BGR2GRAY)
    return gray, canon


def deskew_crop(bgr, rect):
    """Cat va xoay vung board thang dung tu minAreaRect."""
    (cx, cy), (w, h), ang = rect
    w, h = int(round(w)), int(round(h))
    if w == 0 or h == 0:
        return None
    box = cv2.boxPoints(rect).astype("float32")
    dst = np.array([[0, h - 1], [0, 0], [w - 1, 0], [w - 1, h - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(box, dst)
    crop = cv2.warpPerspective(bgr, M, (w, h))
    if crop.shape[0] < crop.shape[1]:        # cho board luon dung doc
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    return crop


def process(path):
    bgr = cv2.imread(path)
    if bgr is None:
        return None
    H, W = bgr.shape[:2]
    mask, method = board_mask(bgr)
    cnt = board_hull(mask)
    if cnt is None:
        return {"path": path, "ok": False, "method": method}

    area = cv2.contourArea(cnt)
    x, y, bw, bh = cv2.boundingRect(cnt)
    rect = cv2.minAreaRect(cnt)
    (rw, rh) = rect[1]
    rect_area = max(rw * rh, 1)
    fill = area / rect_area

    # overlay
    vis = bgr.copy()
    cv2.drawContours(vis, [cv2.boxPoints(rect).astype(int)], -1, (0, 0, 255), 4)
    cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
    cv2.putText(vis, f"{method} fill={fill:.2f}", (x, max(30, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

    crop = deskew_crop(bgr, rect)

    os.makedirs(OUT_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_overlay.png"), vis)
    cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_mask.png"), mask)
    if crop is not None:
        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_board.png"), crop)

    return {
        "path": path, "ok": True, "method": method,
        "img": (W, H), "bbox": (x, y, bw, bh),
        "angle": round(rect[2], 1), "area": int(area),
        "area_ratio": round(area / (W * H), 4), "fill": round(fill, 3),
        "board_size": None if crop is None else (crop.shape[1], crop.shape[0]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", default=None)
    args = ap.parse_args()

    imgs = args.images or sorted(glob.glob(os.path.join(HERE, "mindvision_python", "snap_*.jpg")))
    if not imgs:
        print("Khong tim thay anh."); return

    print(f"Danh gia tach board tren {len(imgs)} anh -> {os.path.relpath(OUT_DIR, HERE)}/\n")
    rows = []
    for p in imgs:
        r = process(p)
        rows.append(r)
        if not r or not r.get("ok"):
            print(f"  {os.path.basename(p):16} FAIL ({r and r.get('method')})")
            continue
        print(f"  {os.path.basename(p):16} {r['method']:14} bbox={r['bbox']} "
              f"angle={r['angle']:>5} area%={r['area_ratio']*100:4.1f} fill={r['fill']:.2f} "
              f"board={r['board_size']}")

    # do on dinh giua cac anh (bbox center + area)
    ok = [r for r in rows if r and r.get("ok")]
    if len(ok) >= 2:
        cxs = [r["bbox"][0] + r["bbox"][2] / 2 for r in ok]
        cys = [r["bbox"][1] + r["bbox"][3] / 2 for r in ok]
        ars = [r["area_ratio"] for r in ok]
        print("\nDanh gia on dinh (std nho = on dinh):")
        print(f"  center_x: mean={np.mean(cxs):.0f} std={np.std(cxs):.0f}")
        print(f"  center_y: mean={np.mean(cys):.0f} std={np.std(cys):.0f}")
        print(f"  area%   : mean={np.mean(ars)*100:.1f} std={np.std(ars)*100:.2f}")
    print("\nXong. Xem overlay/mask/board trong", os.path.relpath(OUT_DIR, HERE) + "/")


if __name__ == "__main__":
    main()
