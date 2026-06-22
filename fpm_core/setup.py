"""Đóng gói module Python `fpm` (pure C++ matching core).

Cài đặt:
    cd fpm_core
    pip install .            # hoặc: pip install -e .  (editable)

Biến môi trường tuỳ chọn:
    FPM_OPENCV_ROOT  Thư mục vcpkg OpenCV (chứa include/ và lib/).
                     Mặc định: ../build/vcpkg_installed/x64-windows
"""
import os
import sys
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OPENCV_ROOT = os.environ.get(
    "FPM_OPENCV_ROOT",
    os.path.join(ROOT, "build", "vcpkg_installed", "x64-windows"),
)
OPENCV_LIB = os.path.join(OPENCV_ROOT, "lib")

# OpenCV headers may live in <root>/include (older layout) or
# <root>/include/opencv4 (current vcpkg layout). Pick whichever has opencv2/.
_INC_BASE = os.path.join(OPENCV_ROOT, "include")
_INC_OPENCV4 = os.path.join(_INC_BASE, "opencv4")
if os.path.isdir(os.path.join(_INC_OPENCV4, "opencv2")):
    OPENCV_INC = _INC_OPENCV4
else:
    OPENCV_INC = _INC_BASE

if not os.path.isdir(OPENCV_INC):
    sys.stderr.write(
        f"[setup.py] Không thấy OpenCV include: {OPENCV_INC}\n"
        "  -> Chạy configure CMake gốc 1 lần để vcpkg cài OpenCV, "
        "hoặc set FPM_OPENCV_ROOT.\n"
    )

ext_modules = [
    Pybind11Extension(
        "fpm",
        # setuptools yêu cầu sources tương đối với thư mục setup.py
        sources=[
            "fpm_core.cpp",
            "fpm_match.cpp",
            "fpm_pybind.cpp",
        ],
        include_dirs=[OPENCV_INC],
        library_dirs=[OPENCV_LIB],
        libraries=["opencv_core4", "opencv_imgproc4", "opencv_imgcodecs4"],
        define_macros=[("OPENCV_4X", None)],
        cxx_std=17,
    ),
]

setup(
    name="fpm",
    version="0.1.0",
    description="Fastest Image Pattern Matching — pure C++ core for Python (Windows)",
    ext_modules=ext_modules,
    # Đây chỉ là 1 extension C++ (fpm), không có package Python nào để gom.
    # Tắt auto-discovery để setuptools không nhầm packaging/ và opencv_bin/.
    packages=[],
    py_modules=[],
    cmdclass={"build_ext": build_ext},
    python_requires=">=3.8",
)
