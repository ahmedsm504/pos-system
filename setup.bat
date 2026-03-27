@echo off
title إعداد نظام الكاشير
cd /d %~dp0
echo ======================================
echo     إعداد نظام الكاشير - أول مرة
echo ======================================
python --version >nul 2>&1
if errorlevel 1 (echo ❌ Python مش مثبت! && pause && exit /b)
echo [1/5] إنشاء بيئة افتراضية...
python -m venv venv
call venv\Scripts\activate.bat
echo [2/5] تثبيت المكتبات...
pip install -r requirements.txt --quiet
echo [3/5] إعداد قاعدة البيانات...
python manage.py migrate
echo [4/5] تجهيز الملفات الثابتة...
python manage.py collectstatic --noinput --clear >nul 2>&1
echo [5/5] إنشاء حساب المدير...
echo.
echo ⚠️ مهم: هذا الحساب هو حساب الإدارة (is_staff=True)
python manage.py createsuperuser
echo.
echo ✅ تم الإعداد! شغّل start.bat
pause
