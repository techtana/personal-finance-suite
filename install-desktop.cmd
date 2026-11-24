@echo off
rem Personal Finance desktop app for Windows: double-click this file.
rem Adds a Start menu entry and a tray icon that open the app and share this PC's AI with the server.
rem Run it again to update. See desktop\install.py for what it does and --uninstall.
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Python from python.org is needed: winget install --id Python.Python.3.13 --scope user
    pause
    exit /b 1
)
rem The python.org launcher picks a signed Python, which Smart App Control requires for the app's environment.
py -3 desktop\install.py %*
if errorlevel 1 (
    echo.
    echo Installing failed; see the messages above.
    pause
    exit /b 1
)
endlocal
