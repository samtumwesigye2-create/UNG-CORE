@echo off
setlocal
set "DIR=%USERPROFILE%\.ung-cad"
if not exist "%DIR%" mkdir "%DIR%"
where py >nul 2>nul || (echo Python 3 is required & pause & exit /b 1)
py -m pip install --user --upgrade flashforge-python-api || exit /b 1
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://ung-cad-3d-production.up.railway.app/ung-cad-ad5m-bridge.py' -OutFile '%DIR%\ung-cad-ad5m-bridge.py'"
set /p CODE=Enter the AD5M Access / Check Code once: 
> "%DIR%\agent.cmd" echo @echo off
>>"%DIR%\agent.cmd" echo set "UNG_CAD_PRINTER_ID=a51a5435"
>>"%DIR%\agent.cmd" echo set "UNG_CAD_CHECK_CODE=%CODE%"
>>"%DIR%\agent.cmd" echo set "UNG_CAD_CLOUD=https://ung-cad-3d-production.up.railway.app"
>>"%DIR%\agent.cmd" echo py "%DIR%\ung-cad-ad5m-bridge.py"
schtasks /Create /F /SC ONLOGON /TN "UNG-CAD AD5M Agent" /TR "\"%DIR%\agent.cmd\"" >nul
start "" "%DIR%\agent.cmd"
echo UNG-CAD AD5M agent installed and set to start automatically.
pause
