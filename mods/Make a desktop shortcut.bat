@echo off
rem A desktop shortcut "Dragon Quest IX (mods)" to "Play with mods.bat", with the game's icon.
setlocal
set "TARGET=%~dp0Play with mods.bat"
set "ICON=%~dp0..\game\dqix.exe"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Dragon Quest IX (mods).lnk'); $s.TargetPath = $env:TARGET; $s.WorkingDirectory = (Split-Path $env:TARGET); $s.WindowStyle = 1; if (Test-Path $env:ICON) { $s.IconLocation = $env:ICON }; $s.Save()"
if errorlevel 1 (echo The shortcut couldn't be made.) else (echo Made "Dragon Quest IX (mods)" on your desktop.)
pause
