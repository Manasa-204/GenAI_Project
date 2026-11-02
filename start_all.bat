@echo off
setlocal enabledelayedexpansion
title Demon Study Monitor - Dual-View Launcher

echo ======================================================================
echo   DEMON PARENTAL CONTROL & STUDY MONITOR - RUNTIME LAUNCHER
echo ======================================================================
echo.

:: 1. Locate Real Python
set "PY_EXE="
if exist "C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe" (
    set "PY_EXE=C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe"
)
if not defined PY_EXE (
    where py >nul 2>&1 && set "PY_EXE=py"
)
if not defined PY_EXE (
    where python >nul 2>&1 && set "PY_EXE=python"
)

if not defined PY_EXE (
    echo [ERROR] Python not found in PATH or standard directories!
    pause
    exit /b 1
)

:: 2. Launch Background Headless Tracker in new window
echo [*] Starting Headless Background Tracker (main.py)...
start "Demon Background Tracker" !PY_EXE! main.py --verbose

:: 3. Launch Parental Web Dashboard server
echo [*] Starting Parental Web Dashboard (web_dashboard.py)...
start "Demon Web Dashboard" !PY_EXE! web_dashboard.py

:: 4. Launch Child Desktop App GUI
echo [*] Starting Child Desktop App (desktop_app.py)...
start "Demon Child App" !PY_EXE! desktop_app.py

:: 5. Open Dashboard in Browser
timeout /t 2 >nul
echo [*] Opening Parental Web Dashboard in default browser: http://localhost:8000
start http://localhost:8000

echo.
echo ======================================================================
echo   [SUCCESS] All 3 components are actively running!
echo   1. Headless Background Tracker : Monitoring processes & enforcing rules
echo   2. Parental Web Dashboard      : http://localhost:8000
echo   3. Child Desktop GUI App       : Displaying remaining study time
echo ======================================================================
echo.
pause
