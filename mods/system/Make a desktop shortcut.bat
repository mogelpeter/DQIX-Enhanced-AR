@echo off
rem A desktop shortcut "Dragon Quest IX (mods)" to "Play with mods.bat", with the game's icon.
setlocal
set "TARGET=%~dp0..\Play with mods.bat"
set "ICON=%~dp0..\..uild\icon\dqix.ico"
set "EXE=%~dp0..\..\game\dqix.exe"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Dragon Quest IX (mods).lnk'); $s.TargetPath = $env:TARGET; $s.WorkingDirectory = (Split-Path $env:TARGET); $s.WindowStyle = 1; $ico = [IO.Path]::GetFullPath($env:ICON); $exe = [IO.Path]::GetFullPath($env:EXE); if (Test-Path $ico) { $s.IconLocation = $ico + ',0' } elseif (Test-Path $exe) { $s.IconLocation = $exe + ',0' }; $s.Save()"
if errorlevel 1 (echo The shortcut couldn't be made.) else (echo Made "Dragon Quest IX (mods)" on your desktop.)
if not "%~1"=="nopause" pause
