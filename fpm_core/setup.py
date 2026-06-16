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
OPENCV_INC = os.path.join(OPENCV_ROOT, "include")
OPENCV_LIB = os.path.join(OPENCV_ROOT, "lib")

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
    cmdclass={"build_ext": build_ext},
    python_requires=">=3.8",
)
