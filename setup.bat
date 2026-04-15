@echo off
setlocal EnableExtensions
title POS Cashier - Setup
cd /d "%~dp0"

echo ======================================
echo     POS Cashier - First-time setup
echo ======================================
echo NOTE: This step needs INTERNET once ^(pip install^).
echo       After setup, the app runs fully OFFLINE.
echo ======================================

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not on PATH.
  pause
  exit /b 1
)

if exist "venv\Scripts\activate.bat" (
  echo [1/5] Virtual environment already exists — skipping creation.
) else (
  echo [1/5] Creating virtual environment...
  python -m venv venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Cannot activate venv.
  pause
  exit /b 1
)

echo [2/5] Installing dependencies ^(needs network unless wheels are cached^)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo [ERROR] pip install failed. Check internet connection and try again.
  pause
  exit /b 1
)

echo [3/5] Setting up database...
python manage.py migrate
if errorlevel 1 (
  echo [ERROR] migrate failed.
  pause
  exit /b 1
)

echo [4/5] Collecting static files into staticfiles\ ...
echo       ^(--clear empties that folder first, then copies admin assets + static\ etc.^)
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
if errorlevel 1 (
  echo [WARN] createsuperuser exited with an error ^(you may have cancelled^).
)

echo.
echo [OK] Setup finished. Run start.bat or the Desktop shortcut to launch.
pause
endlocal
