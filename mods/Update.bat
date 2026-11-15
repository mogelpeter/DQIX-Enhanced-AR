@echo off
rem Updates DQIX Enhanced AR: looks on GitHub for a newer version and, when you say yes, downloads and installs it
rem (your settings, cheat choices and save are kept). Double-click it. It needs the internet.
setlocal
title DQIX Enhanced AR - update
set "NoDefaultCurrentDirectoryInExePath="
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell.exe"
if not exist "%~dp0system\installer\Install.ps1" goto no_script
"%PS%" -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0system\installer\Install.ps1" -Update -GameFolder "%~dp0.."
exit /b %errorlevel%

:no_script
echo.
echo The updater's files are missing (mods\system\installer\Install.ps1). Download the newest release from
echo https://github.com/mogelpeter/DQIX-Enhanced-AR/releases/latest and run its Install.bat.
echo.
pause
exit /b 1