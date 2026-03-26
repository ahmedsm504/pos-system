@echo off
title نظام الكاشير
cd /d %~dp0

echo ======================================
echo        نظام الكاشير - جاري التشغيل
echo ======================================

:: تفعيل البيئة الافتراضية لو موجودة
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

:: تشغيل Print Service في نافذة منفصلة
echo [1/2] تشغيل خدمة الطباعة...
start "Print Service" cmd /k "python print_service\print_service.py"

:: انتظر ثانيتين عشان الـ print service يقوم
timeout /t 2 /nobreak >nul

:: تشغيل Django
echo [2/2] تشغيل السيستم...
echo.
echo ✅ السيستم شغّال على: http://localhost:8000
echo.

waitress-serve --host=0.0.0.0 --port=8000 pos_system.wsgi:application

pause
