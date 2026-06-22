# fpm_core — Tình trạng build & cách chạy (matching)

> Cập nhật 2026-06-22: đã **build xong và chạy PASS**. Phần camera
> (`mindvision_python/`) **chưa tích hợp** — triển khai sau.

## 1. Thư mục này là gì

`fpm_core` là phần **template matching** (NCC + image pyramid + xoay góc + SIMD), trích từ
MFC `MatchTool`, đóng gói thành:

- Thư viện **C++ thuần** `CFastMatch` (chỉ phụ thuộc OpenCV + STL).
- Module **Python `fpm`** (qua pybind11) — file biên dịch `fpm.cp312-win_amd64.pyd`.
- **GUI Tkinter** (`fpm_gui.py`) để chọn ảnh, đặt tham số, match và xem kết quả.

Chi tiết API xem [README.md](README.md).

## 2. Trạng thái hiện tại — ✅ CHẠY ĐƯỢC

| Thành phần | Trạng thái |
|---|---|
| Source C++ (`fpm_core.cpp`, `fpm_match.cpp`, `fpm_pybind.cpp`) | ✅ Có |
| venv Python 3.12 + numpy + pillow + pybind11 + setuptools/wheel | ✅ Có |
| Toolchain C++ (MSVC 14.51 + Windows SDK 10.0.26100) | ✅ Đã cài |
| OpenCV dev + runtime (vcpkg `opencv4:x64-windows` 4.12.0) | ✅ Đã cài tại `C:\vcpkg` |
| **`fpm.cp312-win_amd64.pyd`** | ✅ **Đã build** (`fpm_core/`) |
| `opencv_bin/` DLL | ✅ Đã đồng bộ theo OpenCV 4.12 (vcpkg) |

Kết quả test (khớp đúng kỳ vọng README):

```
test_fpm.py  -> #0 score=0.9485 angle=-0.00 center=(1942.0,1677.5)  | PYTEST PASS
test_m12.py  -> Chars with >=1 hit: 36/36 | total detections: 412
```

## 3. Đã làm gì để build được (môi trường này)

Ban đầu máy thiếu môi trường C++ (không có headers/libs MSVC, không có Windows SDK,
thiếu `vcvarsall.bat`). Sau khi cài workload **"Desktop development with C++"** + Windows SDK
trong Visual Studio Installer, các bước đã thực hiện:

1. Bootstrap **vcpkg** → `C:\vcpkg`.
2. `vcpkg install opencv4:x64-windows` (OpenCV 4.12.0; ~20–40 phút).
3. Sửa [setup.py](setup.py):
   - Headers vcpkg nằm ở `include/opencv4/opencv2` → tự dò chọn `include/opencv4`.
   - `packages=[]`, `py_modules=[]` để setuptools không nhầm `packaging/`, `opencv_bin/`
     là package.
4. Cài build-deps vào venv: `pip install setuptools wheel` (vì build `--no-build-isolation`).
5. Build editable trong môi trường MSVC x64 (xem mục 4).
6. Đồng bộ `opencv_bin/` bằng DLL OpenCV 4.12 của vcpkg (DLL cũ lệch phiên bản → khi import
   bị `ImportError: DLL load failed`).

## 4. Build lại từ đầu (tái lập)

```powershell
# (1) OpenCV qua vcpkg — chỉ cần làm 1 lần
$env:VCPKG_DISABLE_METRICS = 1
C:\vcpkg\vcpkg.exe install opencv4:x64-windows

# (2) Build module fpm trong môi trường MSVC x64
#     Lưu ý: máy này là VS 2026 INSIDERS (không phải Community như build_vscode.bat).
cmd /c '"C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvarsall.bat" x64 ^
  && set "FPM_OPENCV_ROOT=C:\vcpkg\installed\x64-windows" ^
  && set DISTUTILS_USE_SDK=1 ^
  && set MSSdk=1 ^
  && ".venv\Scripts\python.exe" -m pip install -e . --no-build-isolation'

# (3) Nếu cập nhật OpenCV vcpkg, đồng bộ lại DLL runtime:
Copy-Item C:\vcpkg\installed\x64-windows\bin\*.dll .\opencv_bin\ -Force
Remove-Item .\opencv_bin\zlib1.dll -ErrorAction SilentlyContinue   # vcpkg dùng z.dll
```

Kết quả: `fpm_core/fpm.cp312-win_amd64.pyd`.

## 5. Chạy

```powershell
# Smoke test
.\.venv\Scripts\python.exe test_fpm.py
# Test bộ ảnh M12 (xuất m12_result.png)
.\.venv\Scripts\python.exe test_m12.py
# GUI
.\run_gui.bat
```

Runtime tự tìm OpenCV DLL theo thứ tự trong `fpm_env.py`: `%FPM_OPENCV_BIN%` →
`opencv_bin/` (đã đồng bộ) → vcpkg. Mặc định dùng `opencv_bin/` nên không cần set gì thêm.
Muốn ép dùng DLL vcpkg: `set FPM_OPENCV_BIN=C:\vcpkg\installed\x64-windows\bin`.

## 6. Việc còn lại

- [x] Cài VS C++ workload + Windows SDK.
- [x] `vcpkg install opencv4:x64-windows`.
- [x] Build `fpm.cp312-win_amd64.pyd` + chạy test PASS.
- [ ] (Sau) Tích hợp camera `mindvision_python/` → cấp frame trực tiếp cho `fpm.match()`.
