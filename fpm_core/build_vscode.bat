@echo off
REM Build/cài module fpm bằng pip trong môi trường MSVC x64 (đúng cho Python x64).
REM Dùng cho VS Code task hoặc chạy tay: fpm_core\build_vscode.bat
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" -vcvars_ver=14.51.36231 >nul 2>nul
set DISTUTILS_USE_SDK=1
set MSSdk=1
python -m pip install -e "%~dp0." --no-build-isolation
