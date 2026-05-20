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
echo   ARRANCANDO SOUNDDASH
echo ========================================
echo.
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
echo   TUDO A CORRER!
echo ========================================
echo.
echo Acesso: http://10.64.137.6/
echo.
pause