@echo off
REM Launch the board component inspector (live AOI tool).
cd /d "%~dp0"
".venv\Scripts\python.exe" board_inspector.py %*
