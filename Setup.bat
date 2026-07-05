@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Icarus Balance Configurator - Setup
echo ==================================
echo.
echo This will verify/install:
echo   - Python 3 with Tkinter
echo   - UE4SS loader
echo   - Prebuilt Configuration_Mod runtime files from Premade_Configuration
echo.

where winget.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: winget is required for automatic dependency installation.
    echo Install "App Installer" from Microsoft Store, then run this again.
    echo.
    pause
    exit /b 1
)

call :ensure_python
if errorlevel 1 goto failed

echo.
echo Running runtime mod setup...
where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 "%~dp0tools\scripts\install_runtime.py" %*
    if errorlevel 1 goto failed
) else (
    python.exe "%~dp0tools\scripts\install_runtime.py" %*
    if errorlevel 1 goto failed
)
if errorlevel 1 goto failed

echo.
echo Player setup is complete.
echo Fully close and restart Icarus before testing.
echo.
pause
exit /b 0

:ensure_python
where py.exe >nul 2>nul
if not errorlevel 1 (
    echo OK: Python launcher found.
    exit /b 0
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    echo OK: Python found.
    exit /b 0
)
echo Installing Python 3.13...
winget install --exact --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo ERROR: Python installation failed.
    exit /b 1
)
where py.exe >nul 2>nul
if not errorlevel 1 exit /b 0
where python.exe >nul 2>nul
if not errorlevel 1 exit /b 0
echo ERROR: Python installed, but is not visible in this command window yet.
echo Close this window and run Setup.bat again.
exit /b 1

:failed
echo.
echo Player setup did not complete.
echo Fix the error above, then run this file again.
echo.
pause
exit /b 1
