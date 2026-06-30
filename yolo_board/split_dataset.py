#coding=utf-8
"""Chia dataset thanh train/val cho YOLO va tao file board.yaml.

Doc tu  dataset/images/ + dataset/labels/  -> tao:
    dataset/train/images, dataset/train/labels
    dataset/val/images,   dataset/val/labels
    yolo_board/board.yaml

Chay:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\split_dataset.py --val 0.2
"""
import os
import sys
import glob
import shutil
import random
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(HERE, "dataset")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--val", type=float, default=0.2, help="ti le anh cho val")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    img_dir = os.path.join(DS, "images")
    lab_dir = os.path.join(DS, "labels")
    imgs = sorted(glob.glob(os.path.join(img_dir, "*.jpg")) +
                  glob.glob(os.path.join(img_dir, "*.png")))
    imgs = [p for p in imgs
            if os.path.exists(os.path.join(lab_dir,
                              os.path.splitext(os.path.basename(p))[0] + ".txt"))]
    if not imgs:
        print("Khong co anh co nhan. Chay auto_label_hsv.py truoc.")
        return

    random.seed(args.seed)
    random.shuffle(imgs)
    n_val = max(1, int(len(imgs) * args.val))
    splits = {"val": imgs[:n_val], "train": imgs[n_val:]}

    for split, files in splits.items():
        di = os.path.join(DS, split, "images")
        dl = os.path.join(DS, split, "labels")
        os.makedirs(di, exist_ok=True)
        os.makedirs(dl, exist_ok=True)
        for p in files:
            stem = os.path.splitext(os.path.basename(p))[0]
            shutil.copy(p, os.path.join(di, os.path.basename(p)))
            shutil.copy(os.path.join(lab_dir, stem + ".txt"),
                        os.path.join(dl, stem + ".txt"))
        print(f"{split}: {len(files)} anh")

    yaml_path = os.path.join(HERE, "board.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {DS}\n")
        f.write("train: train/images\n")
        f.write("val: val/images\n")
        f.write("nc: 1\n")
        f.write("names: ['board']\n")
    print("Da tao", yaml_path)


if __name__ == "__main__":
    main()
