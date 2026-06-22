#coding=utf-8
"""
Stream lien tuc camera MindVision (GigE/USB).
Phim tat:
  q / ESC : thoat
  s       : luu anh hien tai (snap_XXX.jpg)
  a       : bat/tat tu dong phoi sang (auto exposure)
  + / -   : tang / giam phoi sang (khi o che do thu cong)
  f       : bat/tat lat anh doc
"""
import os, time, platform
import cv2
import numpy as np
import mvsdk


def open_camera():
    devs = mvsdk.CameraEnumerateDevice()
    if not devs:
        raise RuntimeError("Khong tim thay camera nao!")
    for i, d in enumerate(devs):
        print("{}: {} {}".format(i, d.GetFriendlyName(), d.GetPortType()))
    idx = 0 if len(devs) == 1 else int(input("Chon camera: "))
    info = devs[idx]

    h = mvsdk.CameraInit(info, -1, -1)
    cap = mvsdk.CameraGetCapability(h)
    mono = cap.sIspCapacity.bMonoSensor != 0

    mvsdk.CameraSetIspOutFormat(
        h, mvsdk.CAMERA_MEDIA_TYPE_MONO8 if mono else mvsdk.CAMERA_MEDIA_TYPE_BGR8)
    mvsdk.CameraSetTriggerMode(h, 0)        # 0 = thu lien tuc
    mvsdk.CameraSetAeState(h, 1)            # 1 = auto exposure
    mvsdk.CameraPlay(h)

    size = cap.sResolutionRange.iWidthMax * cap.sResolutionRange.iHeightMax * (1 if mono else 3)
    buf = mvsdk.CameraAlignMalloc(size, 16)
    return h, cap, mono, buf


def main():
    h, cap, mono, buf = open_camera()
    flip = (platform.system() == "Windows")
    auto_ae = True
    exp_us = 30 * 1000          # phoi sang thu cong mac dinh: 30ms
    saved = 0
    t_prev, fps = time.time(), 0.0

    win = "MindVision stream - q:thoat  s:luu  a:auto  +/-:phoi sang"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 960, 720)

    print("Dang stream... (focus tren cua so anh)")
    while True:
        try:
            raw, head = mvsdk.CameraGetImageBuffer(h, 200)
            mvsdk.CameraImageProcess(h, raw, buf, head)
            mvsdk.CameraReleaseImageBuffer(h, raw)
        except mvsdk.CameraException as e:
            if e.error_code != mvsdk.CAMERA_STATUS_TIME_OUT:
                print("Grab loi({}): {}".format(e.error_code, e.message))
            continue

        if flip:
            mvsdk.CameraFlipFrameBuffer(buf, head, 1)

        data = (mvsdk.c_ubyte * head.uBytes).from_address(buf)
        ch = 1 if head.uiMediaType == mvsdk.CAMERA_MEDIA_TYPE_MONO8 else 3
        frame = np.frombuffer(data, dtype=np.uint8).reshape((head.iHeight, head.iWidth, ch))

        # FPS
        now = time.time()
        dt = now - t_prev
        t_prev = now
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt)

        show = cv2.resize(frame, (960, 720), interpolation=cv2.INTER_LINEAR)
        mode = "AE:auto" if auto_ae else "AE:manual {:.0f}ms".format(exp_us / 1000.0)
        cv2.putText(show, "FPS {:.1f}  {}".format(fps, mode), (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow(win, show)

        k = cv2.waitKey(1) & 0xFF
        if k in (ord('q'), 27):
            break
        elif k == ord('s'):
            fn = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "snap_{:03d}.jpg".format(saved))
            cv2.imwrite(fn, frame)
            saved += 1
            print("Da luu:", fn)
        elif k == ord('a'):
            auto_ae = not auto_ae
            mvsdk.CameraSetAeState(h, 1 if auto_ae else 0)
            if not auto_ae:
                mvsdk.CameraSetExposureTime(h, exp_us)
            print("Auto exposure:", auto_ae)
        elif k == ord('f'):
            flip = not flip
        elif k in (ord('+'), ord('=')) and not auto_ae:
            exp_us = min(exp_us * 1.25, 1000000)
            mvsdk.CameraSetExposureTime(h, exp_us)
        elif k in (ord('-'), ord('_')) and not auto_ae:
            exp_us = max(exp_us * 0.8, 100)
            mvsdk.CameraSetExposureTime(h, exp_us)

    mvsdk.CameraUnInit(h)
    mvsdk.CameraAlignFree(buf)
    cv2.destroyAllWindows()
    print("Da dong camera.")


if __name__ == "__main__":
    main()
