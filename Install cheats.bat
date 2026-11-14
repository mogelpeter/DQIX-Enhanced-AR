@echo off
rem One-click patcher for DQIX Enhanced: adds the Cheats tab (cheat list, save editor, treasure maps) to the game's menu bar.
rem Put this file and the "mods" folder from the download into your DQIX Enhanced folder (the one with BUILD.bat in it),
rem then double-click this file. It builds the mods into the game (through mods\Apply cheats.bat).
rem Nothing is copied, no folder is asked for, nothing else is started or put on your desktop.
setlocal
title DQIX Enhanced - cheats patcher
set "SYS32=%SystemRoot%\System32"
rem some PCs don't run programs from the current folder by bare name: this batch calls the others by their full path
set "NoDefaultCurrentDirectoryInExePath="
rem this file's own folder is the game folder (a full path without a trailing backslash)
for %%i in ("%~dp0.") do set "TARGET=%%~fi"
if not exist "%TARGET%\BUILD.bat" goto wrong_place
if not exist "%TARGET%\mods\Apply cheats.bat" goto no_mods
rem the patcher's old name: an outdated copy must not stay next to the new one
if exist "%TARGET%\mods\Play with mods.bat" del /q "%TARGET%\mods\Play with mods.bat"
rem cheats this download no longer has (copying the mods folder over an older one never deletes)
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
goto end

:wrong_place
echo.
echo This file is not in your DQIX Enhanced folder: there is no BUILD.bat next to it.
echo Move "Install cheats.bat" and the "mods" folder into the DQIX Enhanced folder ^(the one with BUILD.bat in it^), then run it again.
goto end

:no_mods
echo.
echo The "mods" folder is missing next to this file.
echo Copy the "mods" folder from the download into "%TARGET%" ^(next to BUILD.bat^), then run this again.

:end
if defined DQIX_NOPAUSE exit /b 0
pause
