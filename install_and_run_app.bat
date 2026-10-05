@echo off
title Install & Run Smart Electricity App
echo ========================================================
echo   Installing Smart Electricity App on your phone...
echo ========================================================
 %LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe install -r SmartElectricity-v2.apk
echo.
echo Launching app...
%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe shell am start -n com.smartelectricity.app/.MainActivity
echo.
echo Success! App is running on your phone.
pause
