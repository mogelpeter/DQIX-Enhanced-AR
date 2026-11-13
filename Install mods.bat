@echo off
rem One-click installer for the DQIX Enhanced cheat menu. Just double-click it.
rem It finds your DQIX Enhanced folder by itself (asks only if it can't), copies the mods,
rem puts a shortcut on your desktop and offers to start the menu.
rem Advanced: Install mods.bat "D:\Games\DQIX Enhanced"
setlocal
title DQIX cheat menu - installer
set "TARGET=%~1"
if not defined TARGET if exist "%~dp0..\BUILD.bat" set "TARGET=%~dp0.."
if not defined TARGET (
  echo Looking for your DQIX Enhanced folder...
  for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$r=@(); foreach($b in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('MyDocuments'),$env:USERPROFILE+'\Downloads',$env:USERPROFILE,'C:\','D:\','E:\')){ if(Test-Path $b){ $r+=Get-ChildItem $b -Directory -ErrorAction SilentlyContinue; $r+=Get-ChildItem $b -Directory -ErrorAction SilentlyContinue | ForEach-Object { Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue } } }; $r | Where-Object { Test-Path ($_.FullName+'\BUILD.bat') } | Where-Object { Test-Path ($_.FullName+'\recomp') } | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "TARGET=%%i"
)
if not defined TARGET (
  echo Not found automatically. Please choose your DQIX Enhanced folder in the window that opens.
  for /f "usebackq delims=" %%i in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Choose your DQIX Enhanced folder (the one with BUILD.bat in it)'; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"`) do set "TARGET=%%i"
)
if not defined TARGET ( echo No folder chosen. Run this again and pick the folder. & pause & exit /b 1 )
if not exist "%TARGET%\BUILD.bat" ( echo That folder has no BUILD.bat, so it is not DQIX Enhanced. Run this again and pick the right folder. & pause & exit /b 1 )
echo Installing into "%TARGET%\mods" ...
robocopy "%~dp0mods" "%TARGET%\mods" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XF menu-state.txt msys2-root.txt settings.txt dev-root.txt /XD bin save-backups __pycache__ >nul
if errorlevel 8 ( echo Copy failed. Close the game and the menu, then try again. & pause & exit /b 1 )
if not exist "%TARGET%\mods\settings.txt" copy "%~dp0mods\settings.txt" "%TARGET%\mods\settings.txt" >nul
call "%TARGET%\mods\Make a desktop shortcut.bat" nopause >nul 2>&1
echo.
echo Installed. A shortcut "Dragon Quest IX (mods)" is on your desktop.
if not exist "%TARGET%\game\dqix.exe" (
  echo.
  echo The game itself is not built yet: run BUILD.bat in "%TARGET%" once first ^(you need your own ROM^).
  if not defined DQIX_NOPAUSE pause
  exit /b 0
)
if defined DQIX_NOPAUSE exit /b 0
choice /m "Start the menu now"
if not errorlevel 2 start "" "%TARGET%\mods\Play with mods.bat"
