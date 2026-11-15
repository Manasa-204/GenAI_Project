@echo off
title Demon Study Monitor - OS Hosts Setup

:: Check for Administrator elevation
net session >nul 2>&1
if %errorLevel% == 0 (
    echo ==========================================================
    echo   DEMON STUDY MONITOR - OS HOSTS SETUP (ELEVATED)
    echo ==========================================================
    echo.
    echo Granting write permission to C:\Windows\System32\drivers\etc\hosts...
    icacls "%SystemRoot%\System32\drivers\etc\hosts" /grant Users:(M)
    icacls "%SystemRoot%\System32\drivers\etc\hosts" /grant "%USERNAME%":(M)
    echo.
    echo ==========================================================
    echo   [SUCCESS] Hosts file permission granted successfully!
    echo   Demon can now block and unblock YouTube in real-time.
    echo ==========================================================
    echo.
    timeout /t 5
) else (
    echo Requesting Administrator Elevation...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
)
