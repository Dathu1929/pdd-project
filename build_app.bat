@echo off
title Rebuild Smart Electricity Android App
echo ========================================================
echo   Compiling SmartElectricity APK with Gradle...
echo ========================================================
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
call android-app\gradle-8.0\gradle-8.0\bin\gradle.bat -p android-app assembleDebug
if errorlevel 1 (
    echo.
    echo [ERROR] Gradle compilation failed.
    pause
    exit /b 1
)
copy android-app\app\build\outputs\apk\debug\app-debug.apk SmartElectricity-v2.apk /Y
echo.
echo [SUCCESS] New APK created at SmartElectricity-v2.apk
echo.
pause
