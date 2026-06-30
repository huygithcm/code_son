#coding=utf-8
"""Detect board bang model YOLO da train. Thay the cho HSV (segment_board).

Ham board_bbox_yolo(bgr) tra ve (x, y, w, h) cua board co score cao nhat,
hoac None -> dung lam auto-ROI giong board_bbox() cu trong detect_gui.py.

Chay thu tren camera (live):
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\detect_board.py --live
Hoac tren anh:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\detect_board.py --images path1 path2
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

DEFAULT_W = os.path.join(HERE, "weights", "best.pt")
if not os.path.exists(DEFAULT_W):
    DEFAULT_W = os.path.join(HERE, "runs", "board_yolo", "weights", "best.pt")

_MODEL = None


def load_model(weights=DEFAULT_W):
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        if not os.path.exists(weights):
            raise FileNotFoundError(f"Chua co model: {weights}. Chay train.py truoc.")
        _MODEL = YOLO(weights)
    return _MODEL


def board_bbox_yolo(bgr, conf=0.25, weights=DEFAULT_W):
    """Tra ve (x,y,w,h) board score cao nhat, hoac None. Thay cho board_bbox() HSV."""
    model = load_model(weights)
    res = model.predict(bgr, conf=conf, verbose=False)[0]
    if res.boxes is None or len(res.boxes) == 0:
        return None
    confs = res.boxes.conf.cpu().numpy()
    i = int(confs.argmax())
    x0, y0, x1, y1 = res.boxes.xyxy.cpu().numpy()[i]
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


def _draw(bgr, conf, weights):
    model = load_model(weights)
    res = model.predict(bgr, conf=conf, verbose=False)[0]
    vis = bgr.copy()
    if res.boxes is not None:
        for b, c in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy()):
            x0, y0, x1, y1 = map(int, b)
            cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 3)
            cv2.putText(vis, f"board {c:.2f}", (x0, max(20, y0 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    return vis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=DEFAULT_W)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--images", nargs="*")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    if args.live:
        from camera_mv import Camera, mvsdk
        cam = Camera(); print("Camera:", cam.open())
        cv2.namedWindow("YOLO board", cv2.WINDOW_NORMAL)
        while True:
            try:
                _, rgb = cam.grab()
            except mvsdk.CameraException:
                break
            bgr = np.ascontiguousarray(rgb[:, :, ::-1])
            vis = _draw(bgr, args.conf, args.weights)
            cv2.imshow("YOLO board", vis)
            if (cv2.waitKey(1) & 0xFF) in (ord('q'), 27):
                break
        cam.close(); cv2.destroyAllWindows()
        return

    imgs = args.images or sorted(glob.glob(os.path.join(HERE, "dataset", "images", "*.jpg")))
    out = os.path.join(HERE, "pred_out"); os.makedirs(out, exist_ok=True)
    for p in imgs:
        bgr = cv2.imread(p)
        if bgr is None:
            continue
        vis = _draw(bgr, args.conf, args.weights)
        bb = board_bbox_yolo(bgr, args.conf, args.weights)
        print(f"{os.path.basename(p):20} bbox={bb}")
        cv2.imwrite(os.path.join(out, os.path.basename(p)), vis)
    print("Anh ket qua trong", out)


if __name__ == "__main__":
    main()
