@echo off
rem One-click patcher for DQIX Enhanced: adds the Cheats tab (cheat list, save editor, treasure maps) to the game's menu bar.
rem Just double-click it. It finds your DQIX Enhanced folder by itself (asks only if it can't), copies the mods
rem and builds them into the game. Nothing else is started or put on your desktop.
rem Advanced: Install mods.bat "D:\Games\DQIX Enhanced"
setlocal
title DQIX Enhanced - cheats patcher
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
rem ---- older layout (everything loose in mods\): keep your own files, move them into mods\system, remove the old loose folders
if exist "%TARGET%\mods\tools\dev.py" (
  if not exist "%TARGET%\mods\system" mkdir "%TARGET%\mods\system"
  for %%F in (menu-state.txt msys2-root.txt dev-root.txt) do if exist "%TARGET%\mods\%%F" move /y "%TARGET%\mods\%%F" "%TARGET%\mods\system\" >nul
  for %%D in (save-backups code bin) do if exist "%TARGET%\mods\%%D" if not exist "%TARGET%\mods\system\%%D" move "%TARGET%\mods\%%D" "%TARGET%\mods\system\" >nul
  for %%D in (src tools tests lang fonts database) do if exist "%TARGET%\mods\%%D" rmdir /s /q "%TARGET%\mods\%%D"
  del /q "%TARGET%\mods\dev.bat" "%TARGET%\mods\Make a desktop shortcut.bat" "%TARGET%\mods\AR-codes-*.txt" 2>nul
)
rem ---- previous layout (mods\cheats, mods\system\code, mods\system\database): own files move into mods\system\cheats
if exist "%TARGET%\mods\cheats\*.txt" ( if not exist "%TARGET%\mods\system\cheats" mkdir "%TARGET%\mods\system\cheats" & for %%F in ("%TARGET%\mods\cheats\*.txt") do if /i not "%%~nxF"=="on.txt" if not exist "%TARGET%\mods\system\cheats\%%~nxF" copy "%%F" "%TARGET%\mods\system\cheats\" >nul )
if exist "%TARGET%\mods\system\code\*.txt" ( if not exist "%TARGET%\mods\system\cheats" mkdir "%TARGET%\mods\system\cheats" & for %%F in ("%TARGET%\mods\system\code\*.txt") do if not exist "%TARGET%\mods\system\cheats\%%~nxF" copy "%%F" "%TARGET%\mods\system\cheats\" >nul )
if exist "%TARGET%\mods\system\database" rmdir /s /q "%TARGET%\mods\system\database"
if exist "%TARGET%\mods\system\code" rmdir /s /q "%TARGET%\mods\system\code"
if exist "%TARGET%\mods\cheats" rmdir /s /q "%TARGET%\mods\cheats"
robocopy "%~dp0mods" "%TARGET%\mods" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XF menu-state.txt menu-lang.txt editor-lang.txt msys2-root.txt settings.txt dev-root.txt AR-codes-EU.txt AR-codes-USA.txt /XD bin save-backups __pycache__ >nul
if errorlevel 8 ( echo Copy failed. Close the game and the menu, then try again. & pause & exit /b 1 )
if not exist "%TARGET%\mods\settings.txt" copy "%~dp0mods\settings.txt" "%TARGET%\mods\settings.txt" >nul
rem ---- older versions made a desktop shortcut that started a separate cheat menu: it is not needed any more
for %%L in ("%USERPROFILE%\Desktop\Dragon Quest IX (mods).lnk" "%USERPROFILE%\OneDrive\Desktop\Dragon Quest IX (mods).lnk") do if exist %%L del /q %%L >nul 2>&1
if exist "%TARGET%\mods\system\fonts" rmdir /s /q "%TARGET%\mods\system\fonts"
if exist "%TARGET%\mods\system\bin\dqix-cheat-menu.exe" del /q "%TARGET%\mods\system\bin\dqix-cheat-menu.exe" >nul 2>&1
for %%F in (ui.tsv about.tsv) do if exist "%TARGET%\mods\system\lang\%%F" del /q "%TARGET%\mods\system\lang\%%F"
if exist "%TARGET%\mods\system\tools\lang_keys.py" del /q "%TARGET%\mods\system\tools\lang_keys.py"
if exist "%TARGET%\mods\system\tests\test_menu.py" del /q "%TARGET%\mods\system\tests\test_menu.py"
if exist "%TARGET%\mods\system\src\CheatMenu.cs" del /q "%TARGET%\mods\system\src\CheatMenu.cs"
if exist "%TARGET%\mods\system\Make a desktop shortcut.bat" del /q "%TARGET%\mods\system\Make a desktop shortcut.bat"
rem ---- the Cheats tab into the game itself (menu bar: Cheats), then built. Needs the built game.
if not exist "%TARGET%\game\dqix.exe" (
  echo.
  echo The game itself is not built yet: run BUILD.bat in "%TARGET%" once first ^(you need your own ROM^), then run this again.
  if not defined DQIX_NOPAUSE pause
  exit /b 0
)
echo.
echo Putting the Cheats tab into the game ^(the first time this builds it again: a few minutes^)...
call "%TARGET%\mods\Play with mods.bat" apply
if errorlevel 3 ( echo The game is still running: close it, then run this again. & goto end ) else if errorlevel 1 ( echo The Cheats tab could not be put in ^(see above^). & goto end )
echo.
echo Done. Start the game as always ^(game\dqix.exe^). In its menu bar, under Cheats, you can open the cheat list,
echo the save editor and the treasure map search. Switching cheats on or off is up to you there.
echo Updates of the game keep the tab.
:end
if defined DQIX_NOPAUSE exit /b 0
pause
