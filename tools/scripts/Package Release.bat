@echo off
setlocal
cd /d "%~dp0..\.."

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 "%~dp0package_release.py" %*
    goto done
)

python.exe "%~dp0package_release.py" %*

:done
echo.
pause
exit /b %errorlevel%
