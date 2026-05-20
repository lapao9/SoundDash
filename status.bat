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
echo   STATUS SOUNDDASH
echo ========================================
echo.
echo InfluxDB:
nssm status SoundDash-InfluxDB
echo.
echo Mosquitto:
nssm status SoundDash-Mosquitto
echo.
echo Node-RED:
nssm status SoundDash-NodeRED
echo.
echo Grafana:
sc query Grafana | findstr STATE
echo.
echo Flask:
nssm status SoundDash-Flask
echo.
echo Nginx:
nssm status SoundDash-Nginx
echo.
pause