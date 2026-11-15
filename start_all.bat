@echo off
title Demon Study Monitor - Master One-Click Startup
color 0A

echo ======================================================================
echo           DEMON AI STUDY MONITOR - ONE-CLICK LAUNCHER
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/3] Booting Dual-Portal Web Dashboard Server (http://localhost:8000)...
start "Demon Web Dashboard" /min python web_dashboard.py

timeout /t 2 /nobreak >nul

echo [2/3] Booting Background Tracker Daemon...
start "Demon Background Daemon" /min python main.py --verbose

timeout /t 1 /nobreak >nul

echo [3/3] Booting Student Desktop Focus HUD GUI...
start "Demon Student Focus HUD" python desktop_app.py

echo.
echo ======================================================================
echo [SUCCESS] All 3 Demon components are live and running!
echo   - Web Dashboard:  http://localhost:8000 (Student View & Parent Admin PIN: 1323)
echo   - Student HUD:    Floating GUI running with live circular focus arc
echo   - Daemon:         Autonomous background enforcement & policy engine
echo ======================================================================
echo.
pause
