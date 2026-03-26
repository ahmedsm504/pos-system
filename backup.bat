@echo off
title Backup - نظام الكاشير
cd /d %~dp0

:: إنشاء مجلد الـ backups
if not exist backups mkdir backups

:: اسم الملف بالتاريخ
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set dt=%%a
set backup_name=backup_%dt:~0,8%_%dt:~8,6%.sqlite3

:: نسخ قاعدة البيانات
copy db.sqlite3 backups\%backup_name% >nul

echo ✅ تم الـ Backup: backups\%backup_name%

:: حذف الـ backups الأقدم من 30 يوم
forfiles /p backups /m *.sqlite3 /d -30 /c "cmd /c del @path" >nul 2>&1

echo ✅ تم حذف الـ backups القديمة (+30 يوم)
