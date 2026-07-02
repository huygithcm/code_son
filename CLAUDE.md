# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An automated optical inspection (AOI) station: a MindVision camera photographs PCBs on a conveyor, a YOLO model counts the components on each board, and the PASS/FAIL result is exchanged with a Siemens S7-1200 PLC over `python-snap7`. `yolo_board/PLAN.md` is the authoritative system design (conveyor, PLC IO map, DB1 handshake, deployment phases); read it before extending the PLC/GUI integration. Code comments are in Vietnamese (ASCII, no diacritics) — match that style.

## Environment & running

Windows + PowerShell. There is a project-local venv at `.venv/` — **always invoke it explicitly**; the global `python` does not have the packages:

```
.venv\Scripts\python.exe <script>.py
```

- `run_gui.bat` launches the main GUI ([vision_serial_gui.py](vision_serial_gui.py)) with the venv Python. This is the primary entry point.
- Install deps: `.venv\Scripts\python.exe -m pip install -r requirements.txt` (plus `PyQt5` and `pyserial`, which are not in requirements.txt).
- No test suite, linter, or build step exists. "Testing" means running a script against images in `test_image/` or driving the GUI.

Note: the `yolo_board/README.md` and module docstrings reference `fpm_core\.venv\...` — that path is stale. The real venv is `.venv\` at the repo root.

## Critical: import order on Windows

`torch`/`ultralytics` **must be imported before `PyQt5`**, or torch fails with `WinError 1114 ... c10.dll` (DLL init conflict). Also, never trigger torch's first import from inside a `QThread` — it causes an access violation crash. In [vision_serial_gui.py](vision_serial_gui.py) the top-of-file import block enforces this (torch/ultralytics, then cv2/numpy, then PyQt5); the YOLO worker thread only calls the already-loaded model. Preserve this ordering in any new entry point that mixes Qt and torch.

## Architecture

The GUI wires together four independent, reusable modules — each also runs standalone from the CLI:

- **[camera_mv.py](camera_mv.py)** — `Camera` wraps the MindVision SDK (`mindvision_python/mvsdk.py`, not pip-installed; needs vendor DLLs on the machine). `open()` → `grab()` returns `(gray, rgb)` numpy arrays → `close()`. Frames are BGR-flipped for OpenCV downstream.
- **[yolo_board/detect_components.py](yolo_board/detect_components.py)** — the inspection core. `detect(bgr, conf, roi, imgsz)` returns component boxes (coords always mapped back to the full original image even when `roi` crops). `evaluate(dets, expected)` counts per class and compares to `expected.json` — **PASS means `found == exp` exactly** (both missing and extra count as FAIL). `draw()` overlays boxes. Model is lazy-loaded once via module-global `_MODEL` from `yolo_board/weights/best.pt`. 5 classes: `capacitor, diode, inductor, lm2596, potentiometer`.
- **[segment_board.py](segment_board.py)** — HSV-based board segmentation. `board_bbox(bgr, margin, scale)` finds the blue PCB and returns an auto-ROI; used to crop before YOLO. Falls back to Otsu when the blue mask is too small. `scale<1` downsamples for speed.
- **[yolo_board/plc_s7.py](yolo_board/plc_s7.py)** — `S7(ip, rack, slot)` over snap7. `read_bool`/`write_bool`/`read_int`/`write_int` operate on DB byte/bit addresses; `send_result(ok_all, n_fail, ...)` writes the PASS/FAIL bits + fail count in one call. Requires TIA Portal to have **"Permit PUT/GET"** enabled and **"Optimized block access" disabled** on the DB.

### GUI data flow ([vision_serial_gui.py](vision_serial_gui.py))

`YoloWorker` (a `QThread`) holds only the latest frame under a mutex and drops stale frames, so inference never blocks the UI. A `QTimer` grabs camera frames → hands them to the worker → the worker emits results → the main thread updates the table/overlay. A separate timer polls the PLC trigger bit (rising edge on `DBX{byte}.2`); on trigger it captures, detects, and writes PASS/FAIL + NG-count back to the DB. The full DB1 handshake with heartbeat/watchdog described in `PLAN.md` is the target design; the current GUI implements a simpler trigger→result exchange.

## Performance notes

`detect()` resizes every input to a fixed `imgsz`, so cropping to an ROI lets you shrink `imgsz` while keeping detail. Benchmarks on `test_image/` (2592×1944): **ROI + imgsz=320 is both fastest and most accurate** (7/10 vs 6/10 for full-image imgsz=640). Do **not** crop an ROI and keep imgsz=640 — upscaling a small crop to 640 produces spurious boxes and tanks accuracy. `board_bbox` HSV segmentation is itself a per-frame cost (tens to hundreds of ms); if the camera is fixed, prefer a hard-coded ROI over recomputing HSV every frame.

## Model training pipeline (yolo_board/)

Sequential workflow, documented in [yolo_board/README.md](yolo_board/README.md): `capture_dataset.py` (shoot ~100–150 varied images) → `auto_label_hsv.py` (pre-label via the old HSV method, then hand-correct) → `split_dataset.py --val 0.2` (train/val split + `board.yaml`) → `train.py` (outputs to `runs/board_yolo/weights/best.pt`). `expected.json` is edited by hand to set the expected count per class (default 1 for any class not listed).
