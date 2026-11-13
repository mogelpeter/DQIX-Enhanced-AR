@echo off
rem Puts the mods into a DQIX Enhanced folder (the one with BUILD.bat).
rem   Install mods.bat                      asks which folder (or finds it next to this one)
rem   Install mods.bat "D:\Games\DQIX Enhanced"
rem Your own files in an existing mods folder (menu-state.txt, settings.txt, save-backups) are kept.
setlocal
set "TARGET=%~1"
if not defined TARGET if exist "%~dp0..\DQIX-Enhanced\BUILD.bat" set "TARGET=%~dp0..\DQIX-Enhanced"
if not defined TARGET if exist "%~dp0..\BUILD.bat" set "TARGET=%~dp0.."
if not defined TARGET (
  for /f "usebackq delims=" %%i in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Choose your DQIX Enhanced folder (the one with BUILD.bat)'; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"`) do set "TARGET=%%i"
)
if not defined TARGET ( echo No folder chosen. & pause & exit /b 1 )
if not exist "%TARGET%\BUILD.bat" ( echo "%TARGET%" has no BUILD.bat: it is not a DQIX Enhanced folder. & pause & exit /b 1 )
echo Installing into "%TARGET%\mods" ...
robocopy "%~dp0mods" "%TARGET%\mods" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XF menu-state.txt msys2-root.txt settings.txt dev-root.txt /XD bin save-backups __pycache__ >nul
if errorlevel 8 ( echo Copy failed. & pause & exit /b 1 )
if not exist "%TARGET%\mods\settings.txt" copy "%~dp0mods\settings.txt" "%TARGET%\mods\settings.txt" >nul
echo.
echo Done. Next:  build the game once with BUILD.bat if you haven't, then start "%TARGET%\mods\Play with mods.bat".
echo Check this PC any time with:  "%TARGET%\mods\dev.bat" doctor
if not defined DQIX_NOPAUSE pause
