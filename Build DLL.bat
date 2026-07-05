@echo off
setlocal
cd /d "%~dp0"
python tools\scripts\build_dll.py %*
exit /b %ERRORLEVEL%
