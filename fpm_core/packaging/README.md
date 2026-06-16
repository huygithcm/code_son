# fpm — Fastest Image Pattern Matching (prebuilt, Windows x64)

A pure C++ template-matching core (NCC + image pyramid + rotation-invariant + SIMD)
exposed to Python via pybind11. This wheel **bundles the compiled extension and the
OpenCV runtime DLLs**, so it installs and runs on any Windows x64 machine with a
matching Python version — no separate OpenCV install or DLL juggling required.

## Install

```powershell
pip install fpm-0.1.0-cp312-cp312-win_amd64.whl        # core
pip install "fpm-0.1.0-cp312-cp312-win_amd64.whl[gui]" # core + Tkinter GUI (Pillow)
```

> The wheel is tied to **Python 3.12, Windows, x64** (it carries a prebuilt `.pyd`).
> For another Python version or platform, rebuild the extension from `fpm_core/`.

## Use

```python
import fpm
import numpy as np
from PIL import Image

src  = np.asarray(Image.open("src.bmp").convert("L"),  dtype=np.uint8)
tmpl = np.asarray(Image.open("tmpl.bmp").convert("L"), dtype=np.uint8)

p = fpm.MatchParams()
p.score = 0.5
p.max_pos = 10
p.tolerance_angle = 30
results = fpm.match(src, tmpl, p)   # or: m = fpm.FastMatch(); m.learn(tmpl, p); m.match(src, p)

for r in results:
    print(r["score"], r["angle"], r["center"], r["corners"])
```

Each result is a dict: `score`, `angle` (degrees), `center` `(x, y)`,
`corners` `((LTx,LTy),(RTx,RTy),(RBx,RBy),(LBx,LBy))`.

## GUI

```powershell
fpm-gui            # or: python -m fpm.gui
```
Pick a source + template image, set parameters, click **Match**; the source image is
annotated with the matched boxes/centers/scores and displayed.
