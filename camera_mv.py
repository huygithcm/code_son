#coding=utf-8
"""Camera MindVision dung chung cho teach_board.py va detect_gui.py.

Camera().open() -> mo camera dau tien, CameraPlay (thu lien tuc).
Camera().grab() -> (gray (H,W) uint8, rgb (H,W,3) uint8).
Camera().close().
"""
import os
import sys
import platform

import numpy as np
from PIL import Image

# cho phep import mvsdk tu thu muc mindvision_python
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "mindvision_python"))
import mvsdk  # noqa: E402


class Camera:
    def __init__(self):
        self.h = None
        self.buf = None
        self.mono = False
        self.flip = (platform.system() == "Windows")

    def open(self, force_mono=False):
        """force_mono=True: ISP xuat MONO8 (it du lieu hon -> FPS cao hon, ke ca
        voi cam mau). Khi do khong co thong tin mau (HSV tach board se dung Otsu)."""
        devs = mvsdk.CameraEnumerateDevice()
        if not devs:
            raise RuntimeError("Khong tim thay camera MindVision nao!")
        info = devs[0]
        self.h = mvsdk.CameraInit(info, -1, -1)
        cap = mvsdk.CameraGetCapability(self.h)
        self.mono = (cap.sIspCapacity.bMonoSensor != 0) or force_mono
        mvsdk.CameraSetIspOutFormat(
            self.h, mvsdk.CAMERA_MEDIA_TYPE_MONO8 if self.mono else mvsdk.CAMERA_MEDIA_TYPE_BGR8)
        mvsdk.CameraSetTriggerMode(self.h, 0)
        mvsdk.CameraSetAeState(self.h, 1)
        mvsdk.CameraPlay(self.h)
        size = cap.sResolutionRange.iWidthMax * cap.sResolutionRange.iHeightMax * (1 if self.mono else 3)
        self.buf = mvsdk.CameraAlignMalloc(size, 16)
        return "{} {}".format(info.GetFriendlyName(), info.GetPortType())

    def grab(self, timeout_ms=2000):
        raw, head = mvsdk.CameraGetImageBuffer(self.h, timeout_ms)
        mvsdk.CameraImageProcess(self.h, raw, self.buf, head)
        mvsdk.CameraReleaseImageBuffer(self.h, raw)
        if self.flip:
            mvsdk.CameraFlipFrameBuffer(self.buf, head, 1)
        data = (mvsdk.c_ubyte * head.uBytes).from_address(self.buf)
        ch = 1 if head.uiMediaType == mvsdk.CAMERA_MEDIA_TYPE_MONO8 else 3
        frame = np.frombuffer(data, dtype=np.uint8).reshape((head.iHeight, head.iWidth, ch))
        if ch == 3:
            rgb = frame[:, :, ::-1]
            gray = np.asarray(Image.fromarray(np.ascontiguousarray(rgb)).convert("L"), dtype=np.uint8)
        else:
            rgb = np.repeat(frame, 3, axis=2)
            gray = frame[:, :, 0]
        return np.ascontiguousarray(gray), np.ascontiguousarray(rgb)

    def reopen(self, force_mono):
        """Dong va mo lai camera o che do mau/mono khac."""
        self.close()
        return self.open(force_mono=force_mono)

    def close(self):
        if self.h:
            mvsdk.CameraUnInit(self.h); self.h = None
        if self.buf:
            mvsdk.CameraAlignFree(self.buf); self.buf = None
