@echo off
setlocal
cd /d "%~dp0"
python tools\scripts\package_release.py %*
exit /b %ERRORLEVEL%
