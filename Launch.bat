@echo off
setlocal
cd /d "%~dp0"

where py.exe >nul 2>nul
if %errorlevel%==0 (
    where pyw.exe >nul 2>nul
    if %errorlevel%==0 (
        start "Icarus Balance Configurator" pyw.exe -3 "%~dp0configurator.py"
    ) else (
        start "Icarus Balance Configurator" py.exe -3 "%~dp0configurator.py"
    )
    exit /b 0
)

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "Icarus Balance Configurator" pythonw.exe "%~dp0configurator.py"
    exit /b 0
)

echo Python 3 with Tkinter is required.
echo.
echo Double-click Setup.bat first, then launch this file again.
echo.
pause
exit /b 1
