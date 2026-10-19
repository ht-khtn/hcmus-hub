@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0hcmus-hub.ps1" (
    echo ERROR: Cannot find hcmus-hub.ps1 in this folder.
    echo Put this .bat file beside hcmus-hub.ps1 in D:\app\hcmus-hub.
    pause
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0hcmus-hub.ps1"
set "HUB_EXIT_CODE=%ERRORLEVEL%"

if not "%HUB_EXIT_CODE%"=="0" (
    echo.
    echo HCMUS Hub exited with code %HUB_EXIT_CODE%.
    pause
)

exit /b %HUB_EXIT_CODE%
