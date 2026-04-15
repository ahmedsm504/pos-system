@echo off
setlocal EnableExtensions
title POS Cashier System
cd /d "%~dp0"

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%venv\Scripts\python.exe"
set "VENV_PYW=%ROOT%venv\Scripts\pythonw.exe"
set "VENV_WAITRESS=%ROOT%venv\Scripts\waitress-serve.exe"

:: Print service: use venv interpreters explicitly ^(works with shortcuts / Startup^)
if exist "%VENV_PYW%" (
  start "" /B "%VENV_PYW%" "%ROOT%print_service\print_service.py" 2>nul
  if errorlevel 1 start "" /B "%VENV_PY%" "%ROOT%print_service\print_service.py"
) else (
  echo [WARN] venv not found — using system Python. Run setup.bat for a proper install.
  if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
  start "" /B pythonw "%ROOT%print_service\print_service.py" 2>nul
  if errorlevel 1 start "" /B python "%ROOT%print_service\print_service.py"
)

timeout /t 2 /nobreak >nul

:: Django / Waitress
if exist "%VENV_WAITRESS%" (
  "%VENV_WAITRESS%" --host=0.0.0.0 --port=8000 pos_system.wsgi:application
) else if exist "%VENV_PY%" (
  echo [ERROR] waitress-serve missing in venv. Run: pip install -r requirements.txt
  pause
  exit /b 1
) else (
  waitress-serve --host=0.0.0.0 --port=8000 pos_system.wsgi:application
)

endlocal
