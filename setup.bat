@echo off
title POS Cashier - Setup
cd /d %~dp0
echo ======================================
echo     POS Cashier - First-time setup
echo ======================================
python --version >nul 2>&1
if errorlevel 1 (echo [ERROR] Python is not installed! && pause && exit /b)
echo [1/5] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
echo [2/5] Installing dependencies...
pip install -r requirements.txt --quiet
echo [3/5] Setting up database...
python manage.py migrate
echo [4/5] Collecting static files into staticfiles\ ...
echo       (--clear empties that folder first, then copies admin assets + static\img\ etc.)
python manage.py collectstatic --noinput --clear -v 0
if errorlevel 1 (
  echo [WARN] collectstatic failed — see messages above. Put logo at static\img\logo.png
) else (
  echo       Done.
)
echo [5/5] Creating admin account...
echo.
echo NOTE: This account is for admin access ^(is_staff=True^)
python manage.py createsuperuser
echo.
echo [OK] Setup finished. Run start.bat to launch the app.
pause
