@echo off
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B
)
if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )

cls
echo ========================================
echo   REINICIANDO SOUNDDASH
echo ========================================
echo.
echo --- A PARAR ---
echo [1/6] Nginx...
nssm stop SoundDash-Nginx
echo [2/6] Flask...
nssm stop SoundDash-Flask
echo [3/6] Grafana...
net stop Grafana
echo [4/6] Node-RED...
nssm stop SoundDash-NodeRED
echo [5/6] Mosquitto...
nssm stop SoundDash-Mosquitto
echo [6/6] InfluxDB...
nssm stop SoundDash-InfluxDB
timeout /t 5 /nobreak >nul

echo.
echo --- A ARRANCAR ---
echo [1/6] InfluxDB...
nssm start SoundDash-InfluxDB
timeout /t 3 /nobreak >nul

echo [2/6] Mosquitto...
nssm start SoundDash-Mosquitto
timeout /t 2 /nobreak >nul

echo [3/6] Node-RED...
nssm start SoundDash-NodeRED
timeout /t 3 /nobreak >nul

echo [4/6] Grafana...
net start Grafana
timeout /t 3 /nobreak >nul

echo [5/6] Flask...
nssm start SoundDash-Flask
timeout /t 3 /nobreak >nul

echo [6/6] Nginx...
nssm start SoundDash-Nginx
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   TUDO REINICIADO!
echo ========================================
echo.
echo Acesso: http://10.64.137.6/
echo.
pause
