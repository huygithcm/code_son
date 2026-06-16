r"""Synthetic test-image generator for fpm (with ground truth).

Builds a Source scene by pasting a Template at known positions/angles, optionally with
rotation, extra instances, brightness change and Gaussian noise. Saves:
    out/src.png, out/tmpl.png, out/ground_truth.json

Why: template matching is best validated against *known* placements — you can then
measure position/angle error instead of eyeballing. With --verify it runs fpm and
reports the error against ground truth.

Examples:
    # Use a region of an existing image as the template:
    python make_test_images.py --image "Test Images/Src1.bmp" --crop 1709 1610 466 135 ^
        --angle 20 --instances 3 --noise 8 --out out

    # No input image -> generate a synthetic textured template:
    python make_test_images.py --angle 30 --instances 2 --verify
"""
import argparse
import json
import os
import random

import numpy as np
from PIL import Image


def synthetic_template(w=120, h=80, seed=0):
    """A textured template with sharp features (good for NCC)."""
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 215, size=(h, w), dtype=np.uint8)
    img = Image.fromarray(base, "L").convert("RGB")
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.rectangle([4, 4, w - 5, h - 5], outline=(255, 255, 0), width=3)
    d.line([6, 6, w - 6, h - 6], fill=(255, 0, 0), width=3)
    d.ellipse([w // 2 - 14, h // 2 - 14, w // 2 + 14, h // 2 + 14],
              outline=(0, 200, 255), width=3)
    return img


def make_scene(tmpl, scene_w, scene_h, placements, noise, brightness, bg, seed):
    rng = np.random.default_rng(seed)
    if bg == "noise":
        arr = rng.integers(60, 180, size=(scene_h, scene_w, 3), dtype=np.uint8)
        scene = Image.fromarray(arr, "RGB")
    else:
        scene = Image.new("RGB", (scene_w, scene_h), (128, 128, 128))

    gt = []
    for (cx, cy, ang) in placements:
        rot = tmpl.rotate(ang, expand=True, resample=Image.BICUBIC)
        rw, rh = rot.size
        # rotate() fills corners black; build a mask so only the template pastes.
        mask = tmpl.convert("L").point(lambda _: 255)
        mask = mask.rotate(ang, expand=True, resample=Image.BICUBIC)
        x = int(round(cx - rw / 2))
        y = int(round(cy - rh / 2))
        scene.paste(rot, (x, y), mask)
        gt.append({"center": [float(cx), float(cy)], "angle": float(ang)})

    arr = np.asarray(scene, dtype=np.float32)
    if brightness != 0:
        arr += brightness
    if noise > 0:
        arr += rng.normal(0, noise, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB"), gt


def main():
    ap = argparse.ArgumentParser(description="Generate fpm test images with ground truth.")
    ap.add_argument("--image", help="Source image to crop the template from (optional).")
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    help="Crop box for the template (with --image).")
    ap.add_argument("--scene", nargs=2, type=int, default=(1280, 960),
                    metavar=("W", "H"), help="Scene size. Default 1280x960.")
    ap.add_argument("--angle", type=float, default=0.0,
                    help="Rotation (deg) of the first instance.")
    ap.add_argument("--instances", type=int, default=1, help="Number of pasted copies.")
    ap.add_argument("--noise", type=float, default=5.0, help="Gaussian noise sigma.")
    ap.add_argument("--brightness", type=float, default=0.0, help="Brightness offset.")
    ap.add_argument("--bg", choices=["gray", "noise"], default="noise",
                    help="Background fill.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="out", help="Output folder.")
    ap.add_argument("--verify", action="store_true",
                    help="Run fpm and report error vs ground truth.")
    args = ap.parse_args()

    random.seed(args.seed)

    if args.image:
        src = Image.open(args.image).convert("RGB")
        if args.crop:
            x, y, w, h = args.crop
            tmpl = src.crop((x, y, x + w, y + h))
        else:  # default: center 1/4 region
            W, H = src.size
            tmpl = src.crop((W // 2 - W // 8, H // 2 - H // 8,
                             W // 2 + W // 8, H // 2 + H // 8))
    else:
        tmpl = synthetic_template(seed=args.seed)

    sw, sh = args.scene
    tw, th = tmpl.size
    margin = int(max(tw, th) * 0.8) + 10
    placements = []
    for i in range(max(1, args.instances)):
        cx = random.randint(margin, max(margin + 1, sw - margin))
        cy = random.randint(margin, max(margin + 1, sh - margin))
        ang = args.angle if i == 0 else round(random.uniform(-args.angle, args.angle), 1)
        placements.append((cx, cy, ang))

    scene, gt = make_scene(tmpl, sw, sh, placements, args.noise,
                           args.brightness, args.bg, args.seed)

    os.makedirs(args.out, exist_ok=True)
    src_path = os.path.join(args.out, "src.png")
    tmpl_path = os.path.join(args.out, "tmpl.png")
    gt_path = os.path.join(args.out, "ground_truth.json")
    scene.save(src_path)
    tmpl.save(tmpl_path)
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump({"template_size": [tw, th], "instances": gt}, f, indent=2)

    print(f"Wrote:\n  {src_path}  ({sw}x{sh})\n  {tmpl_path}  ({tw}x{th})\n  {gt_path}")
    print("Ground truth:")
    for g in gt:
        print(f"  center=({g['center'][0]:.1f},{g['center'][1]:.1f})  angle={g['angle']:.1f}")

    if args.verify:
        _verify(src_path, tmpl_path, gt, args.angle)


def _verify(src_path, tmpl_path, gt, tol_angle):
    try:
        from fpm_env import setup_fpm_dll_dirs
        setup_fpm_dll_dirs()
        import fpm
    except Exception as e:
        print(f"\n[verify] cannot import fpm: {e}")
        return
    src = np.asarray(Image.open(src_path).convert("L"), dtype=np.uint8)
    tmpl = np.asarray(Image.open(tmpl_path).convert("L"), dtype=np.uint8)
    p = fpm.MatchParams()
    p.score = 0.4
    p.max_pos = max(1, len(gt))
    p.tolerance_angle = max(5.0, abs(tol_angle) + 5.0)
    res = fpm.match(src, tmpl, p)
    print(f"\n[verify] fpm found {len(res)} match(es):")
    truth = [(g["center"][0], g["center"][1], g["angle"]) for g in gt]
    used = set()
    for r in res:
        cx, cy = r["center"]
        # nearest unused ground-truth point
        best, bi = None, -1
        for i, (gx, gy, ga) in enumerate(truth):
            if i in used:
                continue
            d = ((cx - gx) ** 2 + (cy - gy) ** 2) ** 0.5
            if best is None or d < best:
                best, bi = d, i
        if bi >= 0:
            used.add(bi)
            gx, gy, ga = truth[bi]
            da = ((r["angle"] - ga + 180) % 360) - 180
            print(f"  score={r['score']:.3f} center=({cx:.1f},{cy:.1f}) "
                  f"angle={r['angle']:.1f}  | pos_err={best:.2f}px angle_err={da:.2f}deg")
        else:
            print(f"  score={r['score']:.3f} center=({cx:.1f},{cy:.1f}) (no GT left)")


if __name__ == "__main__":
    main()
