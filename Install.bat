@echo off
rem Installer for DQIX Enhanced AR (cheats for DQIX Enhanced). Double-click it.
rem It starts "installer\Install.ps1" (next to this file), which asks where your DQIX Enhanced folder is,
rem puts the files in it and builds the cheats into the game. Nothing else is needed.
setlocal
title DQIX Enhanced AR - installer
rem some PCs don't run programs from the current folder by bare name
set "NoDefaultCurrentDirectoryInExePath="
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell.exe"
if not exist "%~dp0installer\Install.ps1" goto no_script
if not exist "%~dp0mods\Apply.bat" goto no_script
"%PS%" -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0installer\Install.ps1" %*
exit /b %errorlevel%

:no_script
echo.
echo The installer cannot find its files ("installer\Install.ps1" and the "mods" folder next to this file).
echo You probably started it from inside the ZIP. Right-click release.zip, choose "Extract All...",
echo and start "Install.bat" from the folder that was made.
echo.
pause
exit /b 1
