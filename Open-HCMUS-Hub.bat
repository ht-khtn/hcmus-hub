@echo off
setlocal
cd /d "%~dp0"

set "HUB_URL=http://127.0.0.1:8787/"
set "HUB_SCRIPT=%~dp0hcmus-hub.ps1"

if not exist "%HUB_SCRIPT%" (
    echo ERROR: Cannot find hcmus-hub.ps1 in this folder.
    echo Put this .bat file beside hcmus-hub.ps1 in D:\app\hcmus-hub.
    pause
    exit /b 1
)

rem If HCMUS Hub is already running, just open it; do not start a second server.
curl.exe --silent --fail --output NUL "%HUB_URL%" 2>NUL
if not errorlevel 1 (
    echo HCMUS Hub is already running. Opening the website...
    start "" "%HUB_URL%"
    exit /b 0
)

echo Starting HCMUS Hub...
rem Start the launcher in its own window so this script can wait for the website.
start "HCMUS Hub - Server" powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%HUB_SCRIPT%"

echo Waiting for the local website to become ready...
for /L %%I in (1,1,60) do (
    curl.exe --silent --fail --output NUL "%HUB_URL%" 2>NUL
    if not errorlevel 1 goto :OPEN_BROWSER
    timeout /t 1 /nobreak >NUL
)

echo.
echo ERROR: HCMUS Hub did not respond within 60 seconds.
echo Check the PowerShell server window for startup errors.
echo The website was not opened because it may not be ready yet.
pause
exit /b 1

:OPEN_BROWSER
echo HCMUS Hub is ready. Opening the website...
start "" "%HUB_URL%"
exit /b 0
