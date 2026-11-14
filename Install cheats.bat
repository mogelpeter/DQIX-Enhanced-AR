@echo off
rem One-click patcher for DQIX Enhanced: adds the Cheats tab (cheat list, save editor, treasure maps) to the game's menu bar.
rem Just double-click it. It finds your DQIX Enhanced folder by itself (asks only if it can't), copies the mods
rem and builds them into the game (through mods\Apply cheats.bat). Nothing else is started or put on your desktop.
rem Advanced: Install cheats.bat "D:\Games\DQIX Enhanced"
setlocal
title DQIX Enhanced - cheats patcher
rem Windows' own tools by their full path: a PC with Git, MSYS2 or other tools early in PATH has its own "find" etc.
set "SYS32=%SystemRoot%\System32"
set "PS=%SYS32%\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"
rem some PCs don't run programs from the current folder by bare name: this batch calls BUILD.bat by its full path anyway
set "NoDefaultCurrentDirectoryInExePath="
set "TARGET=%~1"
if not defined TARGET if exist "%~dp0..\BUILD.bat" set "TARGET=%~dp0.."
if not defined TARGET (
  echo Looking for your DQIX Enhanced folder...
  for /f "usebackq delims=" %%i in (`"%PS%" -NoProfile -Command "$r=@(); foreach($b in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('MyDocuments'),$env:USERPROFILE+'\Downloads',$env:USERPROFILE,'C:\','D:\','E:\')){ if(Test-Path $b){ $r+=Get-ChildItem $b -Directory -ErrorAction SilentlyContinue; $r+=Get-ChildItem $b -Directory -ErrorAction SilentlyContinue | ForEach-Object { Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue } } }; $r | Where-Object { Test-Path ($_.FullName+'\BUILD.bat') } | Where-Object { Test-Path ($_.FullName+'\recomp') } | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "TARGET=%%i"
)
if not defined TARGET (
  echo Not found automatically. Please choose your DQIX Enhanced folder in the window that opens.
  for /f "usebackq delims=" %%i in (`"%PS%" -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Choose your DQIX Enhanced folder (the one with BUILD.bat in it)'; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"`) do set "TARGET=%%i"
)
rem a full path without a trailing backslash (also for "." or a relative path given on the command line)
if defined TARGET for %%i in ("%TARGET%\.") do set "TARGET=%%~fi"
if not defined TARGET ( echo No folder chosen. Run this again and pick the folder. & pause & exit /b 1 )
if not exist "%TARGET%\BUILD.bat" ( echo That folder has no BUILD.bat, so it is not DQIX Enhanced. Run this again and pick the right folder. & pause & exit /b 1 )
echo Installing into "%TARGET%\mods" ...
"%SYS32%\robocopy.exe" "%~dp0mods" "%TARGET%\mods" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XF menu-state.txt editor-lang.txt msys2-root.txt settings.txt dev-root.txt AR-codes-EU.txt AR-codes-USA.txt /XD bin save-backups __pycache__ >nul
if errorlevel 8 ( echo Copy failed. Close the game, then try again. & pause & exit /b 1 )
if not exist "%TARGET%\mods\settings.txt" copy "%~dp0mods\settings.txt" "%TARGET%\mods\settings.txt" >nul
rem the patcher's old name: an outdated copy must not stay next to the new one
if exist "%TARGET%\mods\Play with mods.bat" del /q "%TARGET%\mods\Play with mods.bat"
rem cheats this download no longer has (copying never deletes)
for %%F in (no-touch-battles.txt) do if exist "%TARGET%\mods\system\cheats\%%F" del /q "%TARGET%\mods\system\cheats\%%F"
rem ---- the Cheats tab into the game itself (menu bar: Cheats), then built. Needs the built game.
if not exist "%TARGET%\game\dqix.exe" (
  echo.
  echo The game itself is not built yet: run BUILD.bat in "%TARGET%" once first ^(you need your own ROM^), then run this again.
  if not defined DQIX_NOPAUSE pause
  exit /b 0
)
echo.
echo Putting the Cheats tab into the game ^(the first time this builds it again: a few minutes^)...
call "%TARGET%\mods\Apply cheats.bat" apply
if errorlevel 3 ( echo The game is still running: close it, then run this again. & goto end ) else if errorlevel 1 ( echo The Cheats tab could not be put in ^(see above^). & goto end )
echo.
echo Done. Start the game as always ^(game\dqix.exe^). In its menu bar, under Cheats, you can open the cheat list,
echo the save editor and the treasure map search. Switching cheats on or off is up to you there.
echo Updates of the game keep the tab.
:end
if defined DQIX_NOPAUSE exit /b 0
pause
