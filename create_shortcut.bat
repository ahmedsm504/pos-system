@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Creating desktop shortcut...

set "PROJECT=%~dp0"
set "ICO=%PROJECT%cashier.ico"
set "VBS=%PROJECT%run_cashier.vbs"

:: Detect real Desktop path (OneDrive or local)
for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul') do set "DESKTOP=%%B"
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"
:: Expand environment variables in path (e.g. %USERPROFILE%)
call set "DESKTOP=%DESKTOP%"

set "LINK=%DESKTOP%\POS System.lnk"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_LINK=%STARTUP%\POS System.lnk"

:: Build a temp VBS just to create the shortcut
set "TMP_VBS=%TEMP%\make_lnk.vbs"

(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo Set oLink = oWS.CreateShortcut^("%LINK%"^)
echo oLink.TargetPath = "wscript.exe"
echo oLink.Arguments = """%VBS%"""
echo oLink.WorkingDirectory = "%PROJECT%"
echo oLink.Description = "POS Cashier System"
echo oLink.IconLocation = "%ICO%"
echo oLink.Save
) > "%TMP_VBS%"

cscript //nologo "%TMP_VBS%"
del "%TMP_VBS%"

:: Copy shortcut to Startup folder for auto-start on boot
copy "%LINK%" "%STARTUP_LINK%" >nul 2>&1

echo.
echo ================================
echo Shortcut created on Desktop!
echo File: %LINK%
echo.
echo Auto-start on boot: ENABLED
echo Startup: %STARTUP_LINK%
echo ================================
echo.
pause
