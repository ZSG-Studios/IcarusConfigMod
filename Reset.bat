@echo off
setlocal
cd /d "%~dp0"

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 "%~dp0tools\scripts\reset.py" %*
    goto done
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%~dp0tools\scripts\reset.py" %*
    goto done
)

echo Python 3 is required. Run Setup.bat if Python is not installed.
exit /b 1

:done
echo.
pause
exit /b %errorlevel%
