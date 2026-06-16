# Board Component Inspector (live AOI tool)

Detect components on a PCB/board by template matching (fpm core), with a live image
feed and an in-app "teach" workflow. Works today from a **folder** or a **webcam**;
an **industrial camera** plugs in by adding one subclass — the GUI is unchanged.

## Run

```powershell
cd C:\Users\huybu\Desktop\tempalate_maching\fpm_core
.\run_inspector.bat
```

## Workflow

1. **Source** — `Folder (replay)…` (replays images in a folder as a live feed, for
   testing) or `Webcam`. Press **Start** / **Stop**.
2. **Teach a component** — click **✎ Teach region**, drag a rectangle over a part on
   the image, type its name. It is saved to the template library and detected
   immediately. (Detection pauses while teaching; turn Teach off to resume.)
3. **Load an existing library** — `Load folder…` points at a folder of template images
   (one file per component, filename = component name) + optional `components.json`.
4. **Live results** — matched parts are boxed and labelled on the image; the table on
   the left shows **found / expected** counts per component, green when `found >=
   expected`, red otherwise.

## Files

| File | Role |
|---|---|
| `board_inspector.py` | Tkinter GUI: live feed, overlay, teach, pass/fail counts |
| `component_detector.py` | `ComponentLibrary` — learns one template per component (once), runs fpm per frame |
| `camera_source.py` | `FolderSource`, `WebcamSource`, `IndustrialCameraSource` (stub) |

## Template library config (`components.json`)

Per-component matching parameters live next to the template images:

```json
{
  "R1":     { "score": 0.75, "angle": 0,  "max_pos": 4, "expected": 4 },
  "IC_U1":  { "score": 0.80, "angle": 10, "max_pos": 1, "expected": 1 }
}
```
Keys: `score` (threshold), `angle` (rotation tolerance, deg), `max_pos` (max hits),
`max_overlap`, `enabled`, `expected` (count used for the pass/fail color).

## Plugging in an industrial camera

Implement a `CameraSource` subclass in `camera_source.py` (see
`IndustrialCameraSource` for guidance). You only need `open()` and
`read() -> (ok, rgb_uint8)`:

- **Hikrobot / Hikvision (MVS):** vendor `MvCameraControl` SDK — enumerate, create
  handle, `StartGrabbing`, `GetOneFrameTimeout`, convert (Mono8 / BayerRG8) → RGB.
- **Basler:** `pip install pypylon` — `camera.GrabOne()` / `RetrieveResult()` → array.
- **GenICam (generic GigE/USB3 Vision):** `pip install harvesters` — `Harvester` +
  `ImageAcquirer`, load the vendor CTI/GenTL producer.

Then in the GUI add a button that calls `self._set_source(YourCameraSource(...))`.

## Performance notes

- Each template is **learned once** on load/teach; only `match` runs per frame — keep
  the template count and image size reasonable for the frame rate you need.
- Use `angle = 0` when parts are always upright (much faster). Raise `score` to cut
  false positives; lower it if real parts are missed.
- The fpm core uses an image pyramid + SIMD, so large frames are handled efficiently,
  but very large libraries × large frames will reduce fps.
```
