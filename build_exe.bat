@echo off
setlocal enabledelayedexpansion
title Demon Study Monitor - Headless Tracker Build Pipeline

echo ======================================================================
echo   DEMON PARENTAL MONITOR - HEADLESS BACKGROUND TRACKER BUILD PIPELINE
echo ======================================================================
echo.

:: 1. Locate Python
set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1 && set "PY_CMD=py"
)
if not defined PY_CMD (
    if exist "C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe" (
        set "PY_CMD=C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe"
    )
)

if not defined PY_CMD (
    echo [ERROR] Python not found in PATH or standard directories!
    pause
    exit /b 1
)

echo [*] Using Python: "!PY_CMD!"
echo.

:: 2. Check for PyInstaller
!PY_CMD! -c "import PyInstaller" >nul 2>&1
if %errorLevel% neq 0 (
    echo [*] Installing PyInstaller...
    !PY_CMD! -m pip install pyinstaller
)

:: 3. Run PyInstaller Compilation
echo.
echo [*] Compiling headless background tracker with PyInstaller...
echo     Specification : Demon.spec
echo     Console Mode  : False (Completely Hidden)
echo     Target Script : main.py
echo.

!PY_CMD! -m PyInstaller --noconfirm --clean Demon.spec

if not exist "dist\Demon\Demon.exe" (
    echo.
    echo [ERROR] PyInstaller compilation failed! Check output above.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   [SUCCESS] Headless Background Tracker Compiled Successfully!
echo   Output Directory: dist\Demon\
echo   Executable:       dist\Demon\Demon.exe
echo ======================================================================
echo.
echo   Next Step: Run install_background_service.bat to register Demon.exe
echo              in Windows Task Scheduler to run at startup with Highest Privileges.
echo.
pause
