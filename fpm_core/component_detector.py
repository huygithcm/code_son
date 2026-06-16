r"""Component detector for PCB/board inspection, built on the fpm core.

A ComponentLibrary holds one learned template per component (learned ONCE for speed),
plus per-component matching parameters stored in a JSON config. On each frame it runs
fpm and returns labelled detections.

Library folder layout::

    templates/
        R1.png            # template image (name = component label)
        C3.png
        IC_U1.png
        components.json   # optional per-component params {name: {...}}
"""
import json
import os

import numpy as np
from PIL import Image

from fpm_env import setup_fpm_dll_dirs

setup_fpm_dll_dirs()
import fpm  # noqa: E402

IMG_EXTS = (".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
CONFIG_NAME = "components.json"

DEFAULTS = {"score": 0.7, "angle": 0.0, "max_pos": 10, "max_overlap": 0.3,
            "enabled": True}


def to_gray(img):
    """numpy RGB/gray or PIL -> gray uint8 numpy."""
    if isinstance(img, Image.Image):
        return np.asarray(img.convert("L"), dtype=np.uint8)
    arr = np.asarray(img)
    if arr.ndim == 3:
        return np.asarray(Image.fromarray(arr).convert("L"), dtype=np.uint8)
    return arr.astype(np.uint8, copy=False)


class Component:
    def __init__(self, name, gray, cfg):
        self.name = name
        self.gray = gray
        self.h, self.w = gray.shape[:2]
        self.cfg = dict(DEFAULTS, **(cfg or {}))
        self.matcher = fpm.FastMatch()
        self._learn()

    def _learn(self):
        p = fpm.MatchParams()
        p.tolerance_angle = float(self.cfg["angle"])
        self.matcher.learn(self.gray, p)

    def detect(self, frame_gray):
        p = fpm.MatchParams()
        p.score = float(self.cfg["score"])
        p.max_pos = int(self.cfg["max_pos"])
        p.tolerance_angle = float(self.cfg["angle"])
        p.max_overlap = float(self.cfg["max_overlap"])
        out = []
        for r in self.matcher.match(frame_gray, p):
            out.append({
                "name": self.name, "score": r["score"], "angle": r["angle"],
                "center": r["center"], "corners": r["corners"],
            })
        return out


class ComponentLibrary:
    def __init__(self, folder):
        self.folder = folder
        self.components = {}   # name -> Component
        self._config = {}

    # ---- persistence ----
    def _config_path(self):
        return os.path.join(self.folder, CONFIG_NAME)

    def load(self):
        """Load every template image in the folder (+ optional config)."""
        os.makedirs(self.folder, exist_ok=True)
        cfg_path = self._config_path()
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        self.components.clear()
        for fn in sorted(os.listdir(self.folder)):
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in IMG_EXTS:
                continue
            path = os.path.join(self.folder, fn)
            gray = to_gray(Image.open(path))
            self.components[stem] = Component(stem, gray, self._config.get(stem))
        return self

    def save_config(self):
        cfg = {name: c.cfg for name, c in self.components.items()}
        with open(self._config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    # ---- teaching ----
    def add(self, name, gray_patch, cfg=None):
        """Add/replace a component from a cropped patch and persist its image."""
        gray_patch = to_gray(gray_patch)
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, f"{name}.png")
        Image.fromarray(gray_patch, "L").save(path)
        self.components[name] = Component(name, gray_patch, cfg)
        self.save_config()
        return self.components[name]

    def remove(self, name):
        self.components.pop(name, None)
        for ext in IMG_EXTS:
            p = os.path.join(self.folder, f"{name}{ext}")
            if os.path.isfile(p):
                os.remove(p)
        self.save_config()

    # ---- detection ----
    def detect(self, frame_gray):
        """Run all enabled components against a frame. Returns flat list of dicts."""
        results = []
        for c in self.components.values():
            if c.cfg.get("enabled", True):
                results.extend(c.detect(frame_gray))
        return results

    def expected_counts(self):
        """Per-component expected count (default 1) for pass/fail, from config."""
        return {name: int(c.cfg.get("expected", 1)) for name, c in self.components.items()}
