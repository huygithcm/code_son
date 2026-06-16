"""fpm — Fastest Image Pattern Matching (NCC + pyramid + rotation, pure C++ core).

This package bundles the compiled extension (``fpm.fpm``) together with the OpenCV
runtime DLLs it needs (in ``_libs/``), so it works on any Windows x64 machine with the
matching Python version — no external OpenCV install required.

Usage::

    import fpm
    import numpy as np
    from PIL import Image

    src  = np.asarray(Image.open("src.bmp").convert("L"),  dtype=np.uint8)
    tmpl = np.asarray(Image.open("tmpl.bmp").convert("L"), dtype=np.uint8)

    p = fpm.MatchParams()
    p.score = 0.5
    p.max_pos = 10
    results = fpm.match(src, tmpl, p)   # list[dict]: score, angle, center, corners
"""
import os as _os

__version__ = "0.1.0"

# Make the bundled OpenCV DLLs (and the .pyd's own folder) discoverable BEFORE the
# C++ extension is loaded. add_dll_directory is the Windows-safe mechanism.
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_LIBS = _os.path.join(_HERE, "_libs")
for _d in (_LIBS, _HERE):
    if _os.path.isdir(_d):
        try:
            _os.add_dll_directory(_d)
        except (FileNotFoundError, AttributeError):
            pass

# The compiled extension ships as the submodule fpm.fpm (file fpm.<abi>.pyd).
# Its init symbol is PyInit_fpm, which matches the final name component "fpm".
from .fpm import FastMatch, MatchParams, match  # noqa: E402,F401

__all__ = ["FastMatch", "MatchParams", "match", "__version__"]
