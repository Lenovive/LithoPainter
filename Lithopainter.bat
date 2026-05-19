@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM Lithopainter launcher
REM First run: verifies Python and Java, creates .venv, installs deps.
REM Later runs: launches the GUI directly.
REM ---------------------------------------------------------------------------

REM --- Detect Python ---
REM Prefer a stable release with broad wheel coverage. The very latest Python
REM often lacks compiled wheels for NumPy/PySide6 on Windows.
set "PY="
call :try_py 3.13
if not defined PY call :try_py 3.12
if not defined PY call :try_py 3.11
if not defined PY call :try_py 3.10
if not defined PY (
    where py >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :no_python

REM --- Detect Java ---
where java >nul 2>&1
if errorlevel 1 goto :no_java

REM --- Create the virtual environment on first run ---
if not exist ".venv\Scripts\python.exe" (
    echo [Lithopainter] First run: creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :venv_failed
)
REM Microsoft Store python stub returns success without making an interpreter.
if not exist ".venv\Scripts\python.exe" goto :venv_failed

set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"

REM --- Install / refresh dependencies if anything is missing ---
"%VENV_PY%" -c "import PySide6, PIL, numpy" >nul 2>&1
if not errorlevel 1 goto :launch

echo [Lithopainter] Installing dependencies into .venv, this may take a minute...
"%VENV_PY%" -m pip install --upgrade pip >nul
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

REM Verify the install actually works. Pip can report success but the wheels
REM may still fail at import time on bleeding-edge Python builds.
"%VENV_PY%" -c "import PySide6, PIL, numpy" >nul 2>&1
if errorlevel 1 goto :import_failed

:launch
if exist "%VENV_PYW%" (
    start "" "%VENV_PYW%" lithopainter_gui.py
) else (
    "%VENV_PY%" lithopainter_gui.py
    if errorlevel 1 pause
)
endlocal
exit /b 0

REM --- Helpers ---------------------------------------------------------------
:try_py
py -%~1 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -%~1"
goto :eof

:no_python
echo.
echo [Lithopainter] Python 3.10 or newer is required but was not found on PATH.
echo.
echo   Install Python from https://www.python.org/downloads/
echo   IMPORTANT: tick "Add python.exe to PATH" during install.
echo.
pause
exit /b 1

:no_java
echo.
echo [Lithopainter] Java is required to generate STLs but was not found on PATH.
echo.
echo   Install a Java 17+ runtime, e.g. Adoptium Temurin:
echo     https://adoptium.net/
echo.
pause
exit /b 1

:venv_failed
echo.
echo [Lithopainter] Failed to create the virtual environment.
echo This often means the "python" on PATH is the Microsoft Store stub
echo rather than a real Python install.
echo.
echo   Install real Python from https://www.python.org/downloads/
echo   IMPORTANT: tick "Add python.exe to PATH", then close all command
echo   windows before trying again.
echo.
pause
exit /b 1

:pip_failed
echo.
echo [Lithopainter] Failed to install Python dependencies.
echo Check your internet connection (or corporate proxy) and try again.
echo.
pause
exit /b 1

:import_failed
echo.
echo [Lithopainter] Dependencies installed but failed to import. This usually
echo means your Python version is too new for the available NumPy/PySide6
echo wheels. Install Python 3.13 from https://www.python.org/downloads/ ,
echo then delete the .venv folder and re-run this launcher.
echo.
pause
exit /b 1
