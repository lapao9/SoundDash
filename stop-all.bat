@echo off
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B
)
if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )

echo Parando SoundDash...
nssm stop SoundDash-Nginx
nssm stop SoundDash-Flask
net stop Grafana
nssm stop SoundDash-NodeRED
nssm stop SoundDash-Mosquitto
nssm stop SoundDash-InfluxDB
echo.
echo Tudo parado!
pause