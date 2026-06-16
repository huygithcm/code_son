@echo off
REM Khởi chạy GUI fpm bằng Python trong venv.
cd /d "%~dp0"
".venv\Scripts\python.exe" fpm_gui.py %*
