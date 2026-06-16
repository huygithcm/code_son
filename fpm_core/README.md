# fpm_core — Fastest Image Pattern Matching core for Python (Windows)

The template-matching algorithm (NCC + image pyramid + rotation-invariant + SIMD) was
**extracted from MFC** (`MatchTool/MatchToolDlg.cpp`) and packaged as:

- A **pure C++ library** (`CFastMatch`) — depends only on OpenCV + STL.
- A **Python module** `fpm` (a pure C++ DLL for Python) via **pybind11**.
- A **Tkinter GUI** to run matching and display the processed image.

This folder is **self-contained**: it ships a prebuilt `fpm.cp312-win_amd64.pyd`
(Python 3.12, x64), the required OpenCV runtime DLLs in `opencv_bin/`, and sample
images in `Test Images/`. No external project folder is needed at run time.

## Layout

| File / folder | Role |
|---|---|
| `fpm_core.h` | Data structs, `MatchParams`, `CFastMatch` declaration + core function decls |
| `fpm_core.cpp` | 14 core functions (pure OpenCV + SIMD `IM_Conv_SIMD` + `s_BlockMax`) |
| `fpm_match.cpp` | `CFastMatch::LearnPattern` + `Match` (ported from MFC, GUI removed) |
| `fpm_pybind.cpp` | pybind11 wrapper: numpy ↔ `cv::Mat`, returns `list[dict]` |
| `fpm.cp312-win_amd64.pyd` | Prebuilt Python 3.12 extension module |
| `fpm_env.py` | Runtime helper: adds the `.pyd` + OpenCV DLL dirs to the search path |
| `fpm_gui.py` | Tkinter GUI (pick images, set params, match, draw + display result) |
| `run_gui.bat` | Launches the GUI with the venv interpreter |
| `opencv_bin/` | OpenCV runtime DLLs needed by the `.pyd` (~14 MB) |
| `Test Images/` | Sample source/template images |
| `CMakeLists.txt` / `setup.py` | Build the module from source (only if you rebuild) |
| `test_fpm.cpp` / `test_fpm.py` | C++ smoke test / Python test |

## Quick start (use the prebuilt module)

```powershell
cd C:\Users\huybu\Desktop\tempalate_maching\fpm_core

# 1) Create the virtual environment (Python 3.12 — matches the prebuilt .pyd)
py -3.12 -m venv .venv

# 2) Install runtime dependencies
.\.venv\Scripts\python.exe -m pip install numpy pillow

# 3) Launch the GUI
.\run_gui.bat
```

In the GUI: pick a **Source** image and a **Template** image, adjust the parameters,
click **Match**. The source image is annotated with the matched boxes, centers and
scores, and shown on the right. Use **Save result image** to export it.

## Python API

```python
import fpm_env
fpm_env.setup_fpm_dll_dirs()   # call BEFORE importing fpm (sets up DLL search path)
import fpm

import numpy as np
from PIL import Image

src  = np.asarray(Image.open("Test Images/Src1.bmp").convert("L"), dtype=np.uint8)
tmpl = np.asarray(Image.open("Test Images/Dst1.bmp").convert("L"), dtype=np.uint8)

# Parameters (defaults match the original MatchTool app)
p = fpm.MatchParams()
p.score = 0.5            # score threshold
p.max_pos = 10           # max number of targets
p.tolerance_angle = 30   # angle tolerance (degrees); 0 = no rotation
p.use_simd = True        # SIMD in the refine layer
p.sub_pixel = False      # sub-pixel refinement
# also: max_overlap, min_reduce_area, tolerance_range, tolerance1..4,
#       stop_layer1, bitwise_not

# Stateful: learn once, match many
m = fpm.FastMatch()
m.learn(tmpl, p)               # numpy uint8 (gray HxW, or color HxWx3 -> auto gray)
results = m.match(src, p)

# Or one-shot: learn + match
results = fpm.match(src, tmpl, p)

# results: list[dict]
#   { "score": float, "angle": float (degrees),
#     "center": (x, y),
#     "corners": ((LTx,LTy),(RTx,RTy),(RBx,RBy),(LBx,LBy)) }
for r in results:
    print(r["score"], r["angle"], r["center"])
```

Input images should be **uint8**; color images (HxWx3) are converted to gray internally.

## Runtime DLLs

The `.pyd` links `opencv_core4`, `opencv_imgproc4`, `opencv_imgcodecs4` and their
dependencies. `fpm_env.setup_fpm_dll_dirs()` locates the OpenCV `bin` directory by
probing, in order:

1. `%FPM_OPENCV_BIN%` (if set)
2. `fpm_core/opencv_bin/`  ← shipped here
3. `../build/vcpkg_installed/x64-windows/bin`
4. a vcpkg package path

If none is found it prints a warning. To point at a different OpenCV build, set
`FPM_OPENCV_BIN` to the folder containing `opencv_core4.dll`.

## Rebuilding from source (optional)

Only needed if you change the C++ or target a different Python version. Requires
Visual Studio C++ (x64), OpenCV 4 + pybind11 (e.g. via vcpkg).

### CMake (recommended)
```powershell
cmake -S fpm_core -B build_fpm -A x64 `
  -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake `
  -DVCPKG_TARGET_TRIPLET=x64-windows
cmake --build build_fpm --config Release
# -> build_fpm/Release/fpm.pyd
```

### pip / setuptools
```powershell
cd fpm_core
$env:FPM_OPENCV_ROOT = "C:\path\to\opencv"   # folder with include/ and lib/
.\.venv\Scripts\python.exe -m pip install -e .
```

## Tests

```powershell
.\.venv\Scripts\python.exe test_fpm.py
```
Loads `Test Images/Src1.bmp` + `Dst1.bmp`, runs `match`, prints score/positions.

## Verification

C++ core and Python module produce **identical results** on `Src1/Dst1`:
top match `center=(1942.0, 1677.5)`, `angle=0`, `score=0.9485`; SIMD on/off differ by 0 px.
</content>
</invoke>
