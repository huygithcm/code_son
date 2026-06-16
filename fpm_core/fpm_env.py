"""Cấu hình runtime cho module fpm trên Windows.

import fpm cần:
  - thư mục chứa fpm.*.pyd  (mặc định: cạnh file này)
  - thư mục chứa OpenCV release DLL (opencv_core4/imgproc4/imgcodecs4)

Gọi `setup_fpm_dll_dirs()` TRƯỚC khi `import fpm`. Có thể ép đường dẫn OpenCV
bằng biến môi trường FPM_OPENCV_BIN.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Các vị trí khả dĩ của thư mục bin OpenCV (vcpkg release).
_OPENCV_BIN_CANDIDATES = [
    os.environ.get("FPM_OPENCV_BIN", ""),
    os.path.join(HERE, "opencv_bin"),
    os.path.join(os.path.dirname(HERE), "build", "vcpkg_installed", "x64-windows", "bin"),
    r"C:\Users\huybu\Desktop\Fastest_Image_Pattern_Matching\build\vcpkg_installed\x64-windows\bin",
    r"C:\vcpkg\packages\opencv4_x64-windows\bin",
]


def find_opencv_bin():
    """Trả về thư mục bin OpenCV đầu tiên thực sự chứa opencv_core4.dll, hoặc None."""
    for d in _OPENCV_BIN_CANDIDATES:
        if d and os.path.isfile(os.path.join(d, "opencv_core4.dll")):
            return d
    return None


def setup_fpm_dll_dirs():
    """Thêm thư mục pyd + OpenCV bin vào DLL search path. Trả về thư mục OpenCV bin."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    if os.path.isdir(HERE):
        os.add_dll_directory(HERE)
    opencv_bin = find_opencv_bin()
    if opencv_bin:
        os.add_dll_directory(opencv_bin)
    else:
        sys.stderr.write(
            "[fpm_env] CẢNH BÁO: không tìm thấy OpenCV bin (opencv_core4.dll). "
            "Set FPM_OPENCV_BIN trỏ tới thư mục chứa DLL.\n"
        )
    return opencv_bin
