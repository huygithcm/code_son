#coding=utf-8
"""Tu dong tao nhan YOLO cho board bang chinh thuat toan HSV cu (segment_board).

Voi moi anh trong dataset/images/:
  - chay board_rect() (HSV + contour) de lay bounding box board
  - xuat nhan YOLO: dataset/labels/<ten>.txt  ->  "0 xc yc w h" (chuan hoa 0..1)
  - xuat anh preview co ve box: dataset/preview/<ten>.jpg de DUYET NHANH

Y tuong: HSV lam dung ~70-80% anh -> coi nhu nhan xong mien phi. Cac anh HSV
SAI (xem trong preview/) chi can sua tay bang LabelImg/Roboflow -> rat nhanh.

Chay:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\auto_label_hsv.py
    ... --images yolo_board\\dataset\\images
"""
import os
import sys
import glob
import argparse

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from segment_board import board_rect           # noqa: E402  (dung HSV cu)

DEFAULT_IMG = os.path.join(HERE, "dataset", "images")


def rect_to_yolo(rect, W, H):
    """minAreaRect -> YOLO axis-aligned bbox (xc,yc,w,h) chuan hoa 0..1."""
    box = cv2.boxPoints(rect)
    xs, ys = box[:, 0], box[:, 1]
    x0, y0 = max(0, xs.min()), max(0, ys.min())
    x1, y1 = min(W, xs.max()), min(H, ys.max())
    bw, bh = x1 - x0, y1 - y0
    if bw <= 1 or bh <= 1:
        return None
    xc = (x0 + x1) / 2 / W
    yc = (y0 + y1) / 2 / H
    return xc, yc, bw / W, bh / H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default=DEFAULT_IMG)
    args = ap.parse_args()

    img_dir = args.images
    lab_dir = os.path.join(os.path.dirname(img_dir), "labels")
    pre_dir = os.path.join(os.path.dirname(img_dir), "preview")
    os.makedirs(lab_dir, exist_ok=True)
    os.makedirs(pre_dir, exist_ok=True)

    imgs = sorted(glob.glob(os.path.join(img_dir, "*.jpg")) +
                  glob.glob(os.path.join(img_dir, "*.png")))
    if not imgs:
        print("Khong tim thay anh trong", img_dir)
        return

    ok, fail = 0, []
    for p in imgs:
        bgr = cv2.imread(p)
        if bgr is None:
            continue
        H, W = bgr.shape[:2]
        stem = os.path.splitext(os.path.basename(p))[0]
        rect = board_rect(bgr)
        yolo = rect_to_yolo(rect, W, H) if rect is not None else None

        vis = bgr.copy()
        if yolo is None:
            fail.append(stem)
            # ghi file label rong -> ban se sua tay sau
            open(os.path.join(lab_dir, stem + ".txt"), "w").close()
            cv2.putText(vis, "HSV FAIL - sua tay", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        else:
            xc, yc, w, h = yolo
            with open(os.path.join(lab_dir, stem + ".txt"), "w") as f:
                f.write(f"0 {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            x0, y0 = int((xc - w / 2) * W), int((yc - h / 2) * H)
            x1, y1 = int((xc + w / 2) * W), int((yc + h / 2) * H)
            cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 3)
            ok += 1
        cv2.imwrite(os.path.join(pre_dir, stem + ".jpg"), vis)

    print(f"Da gan nhan: {ok}/{len(imgs)} anh OK bang HSV.")
    if fail:
        print(f"HSV FAIL ({len(fail)}) -> sua tay (xem preview/): " + ", ".join(fail))
    print(f"\nLabels: {lab_dir}")
    print(f"Preview (duyet bang mat): {pre_dir}")
    print("Buoc tiep: mo preview/, anh nao box sai -> sua label bang LabelImg/Roboflow.")


if __name__ == "__main__":
    main()
