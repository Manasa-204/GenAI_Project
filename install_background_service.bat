@echo off
setlocal enabledelayedexpansion
title Demon Background Tracker - Windows Task Scheduler Setup

echo ======================================================================
echo   DEMON PARENTAL MONITOR - TASK SCHEDULER PERSISTENCE SETUP
echo ======================================================================
echo.

:: 1. Verify Administrative Privileges (Elevate via UAC if needed)
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Administrator privileges required. Requesting UAC elevation...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 2. Determine Executable Path
set "TASK_NAME=DemonBackgroundTracker"
set "EXE_PATH=%~dp0dist\Demon\Demon.exe"

if not exist "!EXE_PATH!" (
    :: Fallback to standalone single exe if built with --onefile
    if exist "%~dp0dist\Demon.exe" (
        set "EXE_PATH=%~dp0dist\Demon.exe"
    ) else (
        echo [NOTE] Compiled Demon.exe not found in dist\.
        echo        Configuring Task Scheduler with Python runtime fallback:
        echo        Target: pythonw.exe "%~dp0main.py"
        for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do set "PY_PATH=%%i"
        if not defined PY_PATH (
            for /f "delims=" %%i in ('where python.exe 2^>nul') do set "PY_PATH=%%i"
        )
        if not defined PY_PATH (
            set "PY_PATH=C:\Users\nihal\AppData\Local\Programs\Python\Python313\python.exe"
        )
        set "EXE_PATH=\"!PY_PATH!\" \"%~dp0main.py\""
    )
)

echo [*] Target Executable: !EXE_PATH!
echo [*] Task Name:         !TASK_NAME!
echo.

:: 3. Register Task in Windows Task Scheduler:
::    - /sc ONSTART               : Run automatically at system startup (before user logon)
::    - /ru "NT AUTHORITY\SYSTEM" : Run whether user is logged on or not (SYSTEM context)
::    - /rl HIGHEST               : Run with Highest Administrative Privileges
::    - /f                        : Overwrite existing task if present
echo [*] Registering Windows Scheduled Task...
schtasks /create /tn "!TASK_NAME!" /tr "!EXE_PATH!" /sc ONSTART /ru "NT AUTHORITY\SYSTEM" /rl HIGHEST /f

if %errorLevel% equ 0 (
    echo.
    echo ======================================================================
    echo   [SUCCESS] Task Scheduler Entry Successfully Created!
    echo ======================================================================
    echo   Task:       !TASK_NAME!
    echo   Trigger:    At Startup (Boot)
    echo   Logon Mode: Whether user is logged on or not (SYSTEM)
    echo   Privilege:  Highest (Elevated Administrator)
    echo ======================================================================
    echo.
    
    :: 4. Start the service immediately
    echo [*] Starting background service now...
    schtasks /run /tn "!TASK_NAME!"
    echo.
    echo [*] Background tracker is now actively monitoring processes in the background.
) else (
    echo.
    echo [ERROR] Failed to register Task Scheduler entry. Check error message above.
)

echo.
pause

