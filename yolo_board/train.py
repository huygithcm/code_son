#coding=utf-8
"""Train YOLO detect board (1 class). Dung Ultralytics.

Cai dat (1 lan):
    fpm_core\\.venv\\Scripts\\python.exe -m pip install ultralytics

Chay:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\train.py
    ... --model yolo11s.pt --epochs 100 --imgsz 960

Board la vat the to, 1 class -> model nho (yolo11n/s) la du. Khong can real-time
nen co the tang --imgsz / dung yolo11m de chinh xac hon.
"""
import os
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo11n.pt",
                    help="yolo11n/s/m/l/x .pt (n=nhe nhat, x=chinh xac nhat)")
    ap.add_argument("--data", default=os.path.join(HERE, "board.yaml"))
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--name", default="board_yolo")
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.name,
        project=os.path.join(HERE, "runs"),
        patience=30,
        # augment manh -> bu cho dataset nho, robust voi anh sang/vi tri
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
        degrees=180, translate=0.1, scale=0.5, fliplr=0.5, flipud=0.5,
        mosaic=1.0,
    )
    best = os.path.join(HERE, "runs", args.name, "weights", "best.pt")
    print("\nXong. Model tot nhat:", best)


if __name__ == "__main__":
    main()
