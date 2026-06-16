r"""Auto test on the M12 character set (template-matching OCR).

For each character template (0-9, A-Z) in "Test Images/M12", run fpm against the scene
M12_D_Test.jpg, keep detections above a score threshold, then:
  - draw every detection (box + label) onto an annotated image
  - print a per-character summary and the detected string (left-to-right, top-to-bottom)

Run:  python test_m12.py            (uses defaults)
      python test_m12.py --score 0.65 --scene M12_D_Test.jpg --show
"""
import argparse
import os
import string

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from fpm_env import setup_fpm_dll_dirs, HERE

setup_fpm_dll_dirs()
import fpm  # noqa: E402

M12_DIR = os.path.join(HERE, "Test Images", "M12")
CHARS = list(string.digits + string.ascii_uppercase)  # 0-9, A-Z


def load_gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="M12_D_Test.jpg", help="Scene file in M12 dir.")
    ap.add_argument("--score", type=float, default=0.6, help="Score threshold.")
    ap.add_argument("--max-per-char", type=int, default=20)
    ap.add_argument("--angle", type=float, default=0.0, help="Tolerance angle (deg).")
    ap.add_argument("--out", default="m12_result.png")
    ap.add_argument("--show", action="store_true", help="Open the annotated image.")
    args = ap.parse_args()

    scene_path = os.path.join(M12_DIR, args.scene)
    if not os.path.isfile(scene_path):
        raise SystemExit(f"Scene not found: {scene_path}")
    scene_gray = load_gray(scene_path)
    print(f"Scene: {args.scene}  {scene_gray.shape[1]}x{scene_gray.shape[0]}")
    print(f"Templates: {len(CHARS)}  | score>={args.score}  angle_tol={args.angle}\n")

    params = fpm.MatchParams()
    params.score = args.score
    params.max_pos = args.max_per_char
    params.tolerance_angle = args.angle
    params.max_overlap = 0.3

    detections = []  # (char, score, cx, cy, corners)
    found_chars, missing = 0, []
    for ch in CHARS:
        tpath = os.path.join(M12_DIR, f"{ch}.jpg")
        if not os.path.isfile(tpath):
            missing.append(ch)
            continue
        tmpl = load_gray(tpath)
        res = fpm.match(scene_gray, tmpl, params)
        if res:
            found_chars += 1
            best = max(r["score"] for r in res)
            print(f"  '{ch}': {len(res):2d} hit(s)  best={best:.3f}")
            for r in res:
                detections.append((ch, r["score"], r["center"][0], r["center"][1],
                                   r["corners"]))
        else:
            print(f"  '{ch}': no match")

    print(f"\nChars with >=1 hit: {found_chars}/{len(CHARS)} | "
          f"total detections: {len(detections)}")
    if missing:
        print(f"Missing template files: {missing}")

    # Reading order: top-to-bottom by rows, then left-to-right within a row.
    detections.sort(key=lambda d: (round(d[3] / 30), d[2]))
    reading = "".join(d[0] for d in detections)
    print(f"\nDetected sequence (reading order): {reading}")

    annotate(scene_path, detections, os.path.join(HERE, args.out), args.show)


def annotate(scene_path, detections, out_path, show):
    img = Image.open(scene_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    for ch, score, cx, cy, corners in detections:
        pts = [tuple(p) for p in corners] + [tuple(corners[0])]
        draw.line(pts, fill=(0, 220, 0), width=1)
        draw.text((corners[0][0], corners[0][1] - 16), ch, fill=(255, 60, 60), font=font)
    img.save(out_path)
    print(f"Annotated image -> {out_path}")
    if show:
        os.startfile(out_path)  # noqa: S606 (Windows preview)


if __name__ == "__main__":
    main()
