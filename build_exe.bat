@echo off
setlocal enabledelayedexpansion
title Demon Study Monitor - Standalone Build Pipeline

echo ======================================================================
echo   DEMON STUDY MONITOR - WINDOWS STANDALONE BUILD PIPELINE
echo ======================================================================
echo.

:: 1. Check Python
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python not found in PATH!
    pause
    exit /b 1
)

:: 2. Check PyInstaller
python -c "import PyInstaller" >nul 2>&1
if %errorLevel% neq 0 (
    echo [*] Installing PyInstaller and PyWebView...
    pip install pyinstaller pywebview
)

:: 3. Run PyInstaller Compilation
echo.
echo [*] Compiling standalone distribution with PyInstaller...
echo     Specification: Demon.spec
pyinstaller --noconfirm --clean Demon.spec

if not exist "dist\Demon\Demon.exe" (
    echo.
    echo [ERROR] PyInstaller compilation failed! Check output above.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   [SUCCESS] PyInstaller compilation finished!
echo   Output Directory: dist\Demon\
echo   Executable:       dist\Demon\Demon.exe
echo ======================================================================
echo.

:: 4. Check for Inno Setup compiler (ISCC.exe)
set "ISCC_PATH="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
where iscc >nul 2>&1 && for /f "delims=" %%i in ('where iscc') do set "ISCC_PATH=%%i"

if defined ISCC_PATH (
    echo [*] Inno Setup compiler detected: "!ISCC_PATH!"
    echo [*] Compiling single installer (DemonSetup-v1.0.exe)...
    "!ISCC_PATH!" setup.iss
    if %errorLevel% == 0 (
        echo.
        echo ==================================================================
        echo   [SUCCESS] Single Installer Created Successfully!
        echo   Installer: Output\DemonSetup-v1.0.exe
        echo ==================================================================
    )
) else (
    echo [NOTE] Inno Setup 6 not found in standard directories.
    echo        To build the single DemonSetup-v1.0.exe installer, install Inno Setup 6
    echo        from https://jrsoftware.org/isdl.php and re-run build_exe.bat.
    echo.
    echo        You can run Demon standalone directly from:
    echo        dist\Demon\Demon.exe
)

echo.
pause
