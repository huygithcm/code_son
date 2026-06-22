#coding=utf-8
# Chup 1 anh tu camera MindVision va luu ra file (headless, khong can cua so)
import os, platform, numpy as np, mvsdk

def main():
    devs = mvsdk.CameraEnumerateDevice()
    if not devs:
        print("No camera found"); return
    info = devs[0]
    print("Open:", info.GetFriendlyName(), info.GetPortType())

    h = mvsdk.CameraInit(info, -1, -1)
    cap = mvsdk.CameraGetCapability(h)
    mono = cap.sIspCapacity.bMonoSensor != 0
    mvsdk.CameraSetIspOutFormat(h, mvsdk.CAMERA_MEDIA_TYPE_MONO8 if mono else mvsdk.CAMERA_MEDIA_TYPE_BGR8)
    mvsdk.CameraSetTriggerMode(h, 0)          # lien tuc
    mvsdk.CameraSetAeState(h, 1)              # tu dong phoi sang
    mvsdk.CameraPlay(h)

    size = cap.sResolutionRange.iWidthMax * cap.sResolutionRange.iHeightMax * (1 if mono else 3)
    buf = mvsdk.CameraAlignMalloc(size, 16)

    # bo vai frame dau cho on dinh phoi sang
    for _ in range(5):
        try:
            raw, head = mvsdk.CameraGetImageBuffer(h, 2000)
            mvsdk.CameraImageProcess(h, raw, buf, head)
            mvsdk.CameraReleaseImageBuffer(h, raw)
        except mvsdk.CameraException as e:
            print("grab warn:", e.message)

    if platform.system() == "Windows":
        mvsdk.CameraFlipFrameBuffer(buf, head, 1)

    data = (mvsdk.c_ubyte * head.uBytes).from_address(buf)
    frame = np.frombuffer(data, dtype=np.uint8).reshape(
        (head.iHeight, head.iWidth, 1 if head.uiMediaType == mvsdk.CAMERA_MEDIA_TYPE_MONO8 else 3))

    import cv2
    out = os.path.join(os.path.dirname(__file__), "snapshot.jpg")
    cv2.imwrite(out, frame)
    print("Saved:", out, "size:", head.iWidth, "x", head.iHeight)

    mvsdk.CameraUnInit(h)
    mvsdk.CameraAlignFree(buf)

main()
