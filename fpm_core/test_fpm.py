"""Test for the fpm module (.pyd) — load images with PIL, call match, print results.

Run: python test_fpm.py
DLL search paths (fpm.pyd + OpenCV) are configured by fpm_env before importing fpm.
"""
import os
import sys
import numpy as np
from PIL import Image

from fpm_env import setup_fpm_dll_dirs, HERE

setup_fpm_dll_dirs()
import fpm  # noqa: E402

# Sample images: local copy in fpm_core, else the parent project's "Test Images".
_IMG_DIRS = [os.path.join(HERE, "Test Images"),
             os.path.join(os.path.dirname(HERE), "Test Images")]
IMG_DIR = next((d for d in _IMG_DIRS if os.path.isdir(d)), HERE)

def load_gray(path):
    return np.asarray(Image.open(path).convert("L"))

def main():
    src = load_gray(os.path.join(IMG_DIR, "Src1.bmp"))
    tmpl = load_gray(os.path.join(IMG_DIR, "Dst1.bmp"))
    print(f"src={src.shape} templ={tmpl.shape} dtype={src.dtype}")

    params = fpm.MatchParams()
    params.score = 0.5
    params.max_pos = 10
    print("params:", params)

    matcher = fpm.FastMatch()
    matcher.learn(tmpl, params)
    print("learned:", matcher.is_learned())
    res = matcher.match(src, params)

    print(f"\n{len(res)} match:")
    for i, m in enumerate(res):
        cx, cy = m["center"]
        print(f"  #{i}: score={m['score']:.4f} angle={m['angle']:.2f} "
              f"center=({cx:.1f},{cy:.1f})")

    ok = len(res) > 0 and res[0]["score"] > 0.9
    print("\nPYTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
