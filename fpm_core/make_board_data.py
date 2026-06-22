#coding=utf-8
"""Tạo 'data' kiểm tra linh kiện trên board từ 1 ảnh đã chụp.

- Cắt từng linh kiện theo toạ độ (box) -> 1 ảnh template/linh kiện (gray PNG).
- Ghi components.json (tham số match + số lượng kỳ vọng) -> thư viện chuẩn của
  component_detector.ComponentLibrary / board_inspector.
- Verify: nạp lại thư viện, chạy detect trên chính ảnh nguồn, vẽ kết quả + in bảng
  found/expected.

Chạy:
    cd fpm_core
    .venv/Scripts/python.exe make_board_data.py
"""
import os
import json

import numpy as np
from PIL import Image, ImageDraw

from component_detector import ComponentLibrary

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Ảnh board đã chụp từ camera MindVision
SRC_IMAGE = os.path.join(ROOT, "mindvision_python", "snapshot.jpg")
# Thư mục thư viện template sẽ tạo ra
LIB_DIR = os.path.join(HERE, "templates_board")

# Toạ độ từng linh kiện trên ảnh nguồn: name -> (x0, y0, x1, y1)
COMPONENTS = {
    "CAP_TOP": (1130, 558, 1222, 645),   # tụ điện trên (trụ bạc)
    "IC_U1":   (1120, 655, 1215, 745),   # IC (chip đen, có chân)
    "IND_L1":  (1075, 795, 1185, 905),   # cuộn cảm (khối tròn đen)
    "CAP_BOT": (1138, 912, 1230, 1002),  # tụ điện dưới (trụ bạc)
}

# Tham số match + số lượng kỳ vọng cho mỗi linh kiện
PARAMS = {
    "CAP_TOP": {"score": 0.70, "angle": 10, "max_pos": 2, "expected": 1},
    "IC_U1":   {"score": 0.70, "angle": 10, "max_pos": 2, "expected": 1},
    "IND_L1":  {"score": 0.70, "angle": 10, "max_pos": 2, "expected": 1},
    "CAP_BOT": {"score": 0.70, "angle": 10, "max_pos": 2, "expected": 1},
}


def build_library():
    im = Image.open(SRC_IMAGE).convert("RGB")
    print("Anh nguon:", SRC_IMAGE, im.size)
    os.makedirs(LIB_DIR, exist_ok=True)

    cfg = {}
    for name, box in COMPONENTS.items():
        patch = im.crop(box).convert("L")
        out = os.path.join(LIB_DIR, f"{name}.png")
        patch.save(out)
        cfg[name] = PARAMS[name]
        print(f"  template {name}: {patch.size} -> {os.path.relpath(out, ROOT)}")

    with open(os.path.join(LIB_DIR, "components.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("Da ghi components.json")


def verify():
    """Nạp thư viện, detect trên ảnh nguồn, vẽ + in bảng found/expected."""
    lib = ComponentLibrary(LIB_DIR).load()
    src_rgb = Image.open(SRC_IMAGE).convert("RGB")
    frame_gray = np.asarray(src_rgb.convert("L"), dtype=np.uint8)

    dets = lib.detect(frame_gray)
    expected = lib.expected_counts()

    # Vẽ kết quả
    vis = src_rgb.copy()
    d = ImageDraw.Draw(vis)
    counts = {n: 0 for n in lib.components}
    for r in dets:
        counts[r["name"]] += 1
        c = r["corners"]
        d.line([c[0], c[1], c[2], c[3], c[0]], fill=(255, 0, 0), width=4)
        cx, cy = r["center"]
        d.text((cx + 6, cy - 6), f'{r["name"]} {r["score"]:.2f}', fill=(255, 255, 0))

    out = os.path.join(HERE, "board_check_result.png")
    vis.save(out)

    print("\n== KET QUA KIEM TRA LINH KIEN ==")
    print(f'{"Component":10} {"found":>6} {"expected":>9}  status')
    ok_all = True
    for name in sorted(lib.components):
        found, exp = counts[name], expected[name]
        ok = found >= exp
        ok_all &= ok
        print(f'{name:10} {found:>6} {exp:>9}  {"PASS" if ok else "FAIL"}')
    print("TONG:", "PASS" if ok_all else "FAIL")
    print("Anh ket qua ->", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    build_library()
    verify()
