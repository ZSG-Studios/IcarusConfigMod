@echo off
setlocal
cd /d "%~dp0..\.."

py -3 tools\scripts\build_dll.py
if errorlevel 1 exit /b %errorlevel%

echo.
echo Built tools\dll\out\main.dll
