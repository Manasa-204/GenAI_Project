@echo off
title Demon Study Monitor - Web Dashboard
color 0A

echo ======================================================================
echo           DEMON AI STUDY MONITOR - WEB DASHBOARD LAUNCHER
echo ======================================================================
echo.

cd /d "%~dp0"

set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
)

echo [*] Using Python: %PY_EXE%

:: Terminate any lingering web_dashboard instances to prevent camera or port conflicts
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'web_dashboard\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo [*] Starting Web Dashboard Server (http://localhost:8000)...

start "Demon Web Dashboard" /min "%PY_EXE%" "%~dp0web_dashboard.py"

ping 127.0.0.1 -n 3 >nul

echo [*] Opening Web Dashboard in browser...
start http://localhost:8000

echo.
echo ======================================================================
echo [SUCCESS] Demon Web Dashboard is live at http://localhost:8000
echo ======================================================================
echo.
timeout /t 5 >nul
exit
