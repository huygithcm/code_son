r"""Camera/image source abstraction for the board inspector.

A `CameraSource` yields frames as RGB uint8 numpy arrays. Backends:
  - FolderSource : cycle through images in a folder (simulates a live feed; for testing)
  - WebcamSource : OpenCV VideoCapture (USB/DirectShow webcam)
  - IndustrialCameraSource : stub + guidance to plug a real machine-vision SDK
                             (Hikrobot MVS, Basler pylon, GenICam/Harvester, ...)

Design goal: the GUI only talks to this interface, so swapping in an industrial
camera later means writing one subclass — no GUI changes.
"""
import glob
import os
import time

import numpy as np

try:
    import cv2
except Exception:  # opencv-python optional (only needed for webcam / industrial grab)
    cv2 = None

IMG_EXTS = (".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff")


class CameraSource:
    """Base interface. Subclasses implement open(), read(), close()."""

    name = "source"

    def open(self):
        pass

    def read(self):
        """Return (ok: bool, frame_rgb: np.ndarray|None)."""
        raise NotImplementedError

    def close(self):
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


class FolderSource(CameraSource):
    """Replay images from a folder as if they were a live stream (loops)."""

    def __init__(self, folder, fps=5.0, loop=True):
        self.folder = folder
        self.loop = loop
        self.min_dt = 1.0 / fps if fps > 0 else 0.0
        self._files = []
        self._i = 0
        self._last = 0.0
        self.name = f"folder:{os.path.basename(folder.rstrip(os.sep))}"

    def open(self):
        files = []
        for ext in IMG_EXTS:
            files += glob.glob(os.path.join(self.folder, f"*{ext}"))
            files += glob.glob(os.path.join(self.folder, f"*{ext.upper()}"))
        self._files = sorted(set(files))
        if not self._files:
            raise FileNotFoundError(f"No images in {self.folder}")
        self._i = 0

    def read(self):
        if not self._files:
            return False, None
        # pace to the requested fps
        dt = time.time() - self._last
        if dt < self.min_dt:
            time.sleep(self.min_dt - dt)
        self._last = time.time()

        if self._i >= len(self._files):
            if not self.loop:
                return False, None
            self._i = 0
        path = self._files[self._i]
        self._i += 1
        frame = _read_rgb(path)
        return frame is not None, frame


class WebcamSource(CameraSource):
    """USB / DirectShow webcam via OpenCV VideoCapture."""

    def __init__(self, index=0, width=None, height=None):
        if cv2 is None:
            raise RuntimeError("opencv-python is required for WebcamSource "
                               "(pip install opencv-python).")
        self.index = index
        self.width = width
        self.height = height
        self.cap = None
        self.name = f"webcam:{index}"

    def open(self):
        self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if self.width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open webcam {self.index}")

    def read(self):
        if self.cap is None:
            return False, None
        ok, bgr = self.cap.read()
        if not ok:
            return False, None
        return True, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class IndustrialCameraSource(CameraSource):
    """Placeholder for a real machine-vision camera.

    To integrate (example: Hikrobot MVS), install the vendor Python SDK and fill in
    open()/read():

        from MvCameraControl_class import MvCamera        # Hikrobot MVS SDK
        # enumerate -> create handle -> set TriggerMode -> StartGrabbing
        # in read(): GetOneFrameTimeout -> bytes -> np.frombuffer -> reshape ->
        #            convert (e.g. BayerRG8 / Mono8) to RGB and return.

    Basler: use `pypylon` (camera.GrabOne / RetrieveResult -> array).
    GenICam generic: use `harvesters` (Harvester + ImageAcquirer).
    The rest of the app stays unchanged — it only needs read() -> (ok, rgb_uint8).
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = "industrial:not-configured"

    def open(self):
        raise NotImplementedError(
            "IndustrialCameraSource is a stub. Install the vendor SDK (Hikrobot MVS / "
            "Basler pypylon / GenICam harvesters) and implement open()/read(). "
            "See the class docstring.")

    def read(self):
        raise NotImplementedError


def _read_rgb(path):
    """Read an image file as RGB uint8 (prefer cv2, fall back to PIL)."""
    if cv2 is not None:
        # imread handles unicode paths poorly on Windows; use imdecode.
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
