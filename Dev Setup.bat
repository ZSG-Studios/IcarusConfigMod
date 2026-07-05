@echo off
setlocal
cd /d "%~dp0"
python tools\scripts\dev_setup.py %*
exit /b %ERRORLEVEL%
