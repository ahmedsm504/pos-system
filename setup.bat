@echo off
title إعداد نظام الكاشير
cd /d %~dp0

echo ======================================
echo     إعداد نظام الكاشير - أول مرة
echo ======================================
echo.

:: التحقق من Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python مش مثبت! حمّله من python.org
    pause
    exit /b
)

echo ✅ Python موجود
echo.

:: إنشاء بيئة افتراضية
echo [1/5] إنشاء بيئة افتراضية...
python -m venv venv
call venv\Scripts\activate.bat

:: تثبيت المكتبات
echo [2/5] تثبيت المكتبات...
pip install -r requirements.txt --quiet

:: عمل الـ migrations
echo [3/5] إعداد قاعدة البيانات...
python manage.py migrate

:: جمع الـ static files
echo [4/5] تجهيز الملفات الثابتة...
python manage.py collectstatic --noinput --clear >nul 2>&1

:: إنشاء superuser
echo [5/5] إنشاء حساب المدير...
echo.
echo ادخل بيانات حساب المدير:
python manage.py createsuperuser

echo.
echo ======================================
echo ✅ تم الإعداد بنجاح!
echo.
echo عشان تشغّل السيستم: start.bat
echo ======================================
pause
