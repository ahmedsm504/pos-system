@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Creating desktop shortcut...

set "PROJECT=%~dp0"
set "DESKTOP=%USERPROFILE%\Desktop"
set "ICO=%PROJECT%cashier.ico"
set "VBS=%PROJECT%run_cashier.vbs"
set "LINK=%DESKTOP%\POS System.lnk"

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

echo.
echo ================================
echo Shortcut created on Desktop!
echo File: POS System.lnk
echo ================================
echo.
pause
