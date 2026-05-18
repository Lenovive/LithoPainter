@echo off
cd /d "%~dp0"
start "" pythonw lithopainter_gui.py
if errorlevel 1 (
    echo pythonw not found — falling back to python with console.
    echo If you see this often, install Python 3.x from https://python.org
    echo and ensure pythonw.exe is on your PATH.
    echo.
    python lithopainter_gui.py
    if errorlevel 1 pause
)
