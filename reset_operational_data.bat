@echo off
setlocal EnableExtensions
title POS Cashier - Reset Operational Data
cd /d "%~dp0"

echo ==============================================
echo   POS Cashier - Reset Operational Data Only
echo ==============================================
echo This will DELETE:
echo - Orders + order items + activities + table links
echo - Shifts
echo - Inventory entries
echo - Saved delivery customers
echo - Django sessions and admin logs
echo.
echo This will KEEP:
echo - Menu and categories
echo - Tables
echo - Admin and cashier accounts
echo - Waiters and delivery drivers
echo ==============================================
echo.

set /p CONFIRM=Type YES to continue: 
if /I not "%CONFIRM%"=="YES" (
  echo Cancelled.
  pause
  exit /b 0
)

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%venv\Scripts\python.exe"

if exist "%VENV_PY%" (
  "%VENV_PY%" manage.py shell -c "from pos.models import Order,Shift,InventoryEntry,DeliveryCustomer; from django.contrib.admin.models import LogEntry; from django.contrib.sessions.models import Session; [m.objects.all().delete() for m in (Order, Shift, InventoryEntry, DeliveryCustomer, LogEntry, Session)]; print('Operational data reset done')"
) else (
  echo [WARN] venv not found. Using system Python.
  python manage.py shell -c "from pos.models import Order,Shift,InventoryEntry,DeliveryCustomer; from django.contrib.admin.models import LogEntry; from django.contrib.sessions.models import Session; [m.objects.all().delete() for m in (Order, Shift, InventoryEntry, DeliveryCustomer, LogEntry, Session)]; print('Operational data reset done')"
)

if errorlevel 1 (
  echo [ERROR] Reset failed.
  pause
  exit /b 1
)

echo [OK] Operational data has been reset successfully.
pause
endlocal
