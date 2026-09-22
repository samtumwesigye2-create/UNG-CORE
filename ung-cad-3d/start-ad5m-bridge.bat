@echo off
setlocal
title UNG-CAD AD5M Bridge
set "UNG_CAD_PRINTER_ID=a51a5435"
set "UNG_CAD_CHECK_CODE=a51a5435"
where py >nul 2>nul
if errorlevel 1 (
 echo Python 3 is required on this workstation.
 pause
 exit /b 1
)
py -m pip install --user --upgrade flashforge-python-api
if errorlevel 1 pause & exit /b 1
py "%~dp0ung-cad-ad5m-bridge.py"
pause
