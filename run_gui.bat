@echo off
rem Chay giao dien Vision Serial bang Python trong .venv
cd /d "%~dp0"
".venv\Scripts\python.exe" vision_serial_gui.py
pause
