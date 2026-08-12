@echo off
setlocal enabledelayedexpansion
title Parlaklik Kontrolu

py --version >nul 2>&1
if errorlevel 1 (
    echo Python bulunamadi.
    echo py.org adresinden Python kurun ve tekrar deneyin.
    pause
    exit /b 1
)

py -c "import PyQt5" >nul 2>&1
if errorlevel 1 (
    echo PyQt5 kuruluyor, lutfen bekleyin...
    py -m pip install PyQt5 --quiet --no-warn-script-location
    if errorlevel 1 (
        echo Kurulum basarisiz. Internet baglantinizi kontrol edin.
        pause
        exit /b 1
    )
)

if not exist "%~dp0ControlMyMonitor.exe" (
    echo Harici monitor araci indiriliyor...
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://www.nirsoft.net/utils/controlmymonitor.zip' -OutFile '%~dp0cmm.zip' -UseBasicParsing -TimeoutSec 30; Expand-Archive -Path '%~dp0cmm.zip' -DestinationPath '%~dp0' -Force; Remove-Item '%~dp0cmm.zip' -Force } catch { }"
)

py "%~dp0brightness_controller.py"
