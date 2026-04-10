@echo off
title POS Cashier System
cd /d "%~dp0"

:: Activate virtualenv if exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

:: Start print service silently
start "" /B pythonw print_service\print_service.py 2>nul
if errorlevel 1 (
    start "" /B python print_service\print_service.py
)

:: Wait 2 seconds
timeout /t 2 /nobreak >nul

:: Start Django server
waitress-serve --host=0.0.0.0 --port=8000 pos_system.wsgi:application
