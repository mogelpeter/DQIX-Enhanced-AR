@echo off
rem Dragon Quest IX (PC) with your mods. Start the game with this (or with the
rem shortcut "Make a desktop shortcut.bat" makes).
rem
rem It opens the cheat menu: a window with every cheat as a switch, and a Play
rem button. Before that it
rem   1. works the cheat list out against your ROM (mods\tools\catalog.py)
rem   2. makes the menu itself from its source (mods\src\CheatMenu.cs) when it's
rem      missing or older, with the C# compiler that comes with Windows
rem
rem The menu's Play button runs this file again as "Play with mods.bat apply":
rem   1. puts the code mods that are on, and the cheats' own part of the game (so
rem      they work with friends too), into the game's build: an update of the
rem      game takes them out, this puts them back
rem   2. rebuilds the game if they changed (only what changed: a few minutes)
rem and then the menu starts the game. "catalog" only makes the list again.
rem
rem "cheat_window = no" in settings.txt: no menu; this builds the mods in and
rem starts the game (switch mods on in the files, as the README says).
setlocal
cd /d "%~dp0.."
set "WHAT=%~1"
rem (run by the menu: nothing may wait for a key)
if defined WHAT set DQIX_NOPAUSE=1
if not defined WHAT title DQIX Enhanced - mods
if not exist "BUILD.bat" goto wrong_place
if not exist "patches.txt" goto wrong_place

rem ---- the build tools (MSYS2): the ones found last time, else the game's own finder
set "MSYSROOT="
if exist "mods\msys2-root.txt" set /p MSYSROOT=<"mods\msys2-root.txt"
if defined MSYSROOT if exist "%MSYSROOT%\usr\bin\bash.exe" goto have_msys
set "MSYSROOT="
echo Looking for the build tools (MSYS2)...
set "MSYSRES=%TEMP%\dqix-mods-%RANDOM%.txt"
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\msys2-setup.ps1" -Out "%MSYSRES%"
if errorlevel 1 goto no_tools
set /p MSYSROOT=<"%MSYSRES%"
del "%MSYSRES%" >nul 2>&1
if not defined MSYSROOT goto no_tools
>"mods\msys2-root.txt" echo %MSYSROOT%
:have_msys
set MSYSTEM=UCRT64
set CHERE_INVOKING=1
set "BASH=%MSYSROOT%\usr\bin\bash.exe"
set "PYRUN=PY=python3; command -v python3 >/dev/null 2>&1 || PY=python; $PY"

rem ---- the game has to be built once first (the mods are checked against its code)
if exist "game\dqix.exe" if exist "build\extract\arm9\arm9.bin" if exist "build\recomp\dispatch_table.c" goto built
tasklist /fi "imagename eq dqix.exe" 2>nul | find /i "dqix.exe" >nul && goto game_running
echo The game isn't built yet: building it first.
set DQIX_NOPAUSE=1
call BUILD.bat
if errorlevel 1 goto build_failed
:built

if /i "%WHAT%"=="apply" goto apply
if /i "%WHAT%"=="catalog" goto catalog

rem ---- no menu wanted: the old way
findstr /i /r /c:"^ *cheat_window *= *no" "mods\settings.txt" >nul 2>&1 && goto no_menu

rem ---- the cheat list, worked out against this ROM
echo Reading the cheat list...
"%BASH%" -lc "%PYRUN% mods/tools/catalog.py ."
if errorlevel 1 goto list_failed

rem ---- the menu, made here from its source when it's missing or older
if not exist "mods\bin" mkdir "mods\bin"
"%BASH%" -lc "[ mods/bin/dqix-cheat-menu.exe -nt mods/src/CheatMenu.cs ]" && goto menu_made
set "NET=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319"
if not exist "%NET%\csc.exe" goto no_csc
set "ICON="
if exist "build\icon\dqix.ico" set "ICON=-win32icon:build\icon\dqix.ico"
echo Making the cheat menu...
tasklist /fi "imagename eq dqix-cheat-menu.exe" 2>nul | find /i "dqix-cheat-menu.exe" >nul && goto menu_made
"%NET%\csc.exe" -nologo -target:winexe -platform:x64 -optimize+ "-out:mods\bin\dqix-cheat-menu.exe" %ICON% "-r:%NET%\WPF\PresentationFramework.dll" "-r:%NET%\WPF\PresentationCore.dll" "-r:%NET%\WPF\WindowsBase.dll" -r:System.Xaml.dll -r:System.Core.dll "mods\src\CheatMenu.cs"
if errorlevel 1 goto no_csc
:menu_made
if not exist "mods\bin\dqix-cheat-menu.exe" goto no_csc
start "" "mods\bin\dqix-cheat-menu.exe" "%CD%"
exit /b 0

:no_csc
echo.
echo The cheat menu couldn't be made (it needs the C# compiler of .NET Framework 4,
echo which comes with Windows 10 and 11). The game starts without it; switch mods
echo on in the files in mods\code, as the README says.
:no_menu
call :put_in
if errorlevel 1 exit /b %errorlevel%
echo Starting the game...
start "Dragon Quest IX" /min cmd /c "game\play.bat"
exit /b 0

:catalog
"%BASH%" -lc "%PYRUN% mods/tools/catalog.py ."
if errorlevel 1 exit /b 1
exit /b 0

:apply
call :put_in
exit /b %errorlevel%

rem ---- the mods into the game's build (mods\tools\put_in.sh), and the build itself when
rem      something changed. Leaves 0 = the game has them, 1 = it failed, 3 = the game is running
:put_in
"%BASH%" -lc "sh mods/tools/put_in.sh"
if "%errorlevel%"=="1" goto apply_failed
if not "%errorlevel%"=="10" exit /b 0
tasklist /fi "imagename eq dqix.exe" 2>nul | find /i "dqix.exe" >nul && goto game_running
echo.
echo Rebuilding the game with the mods (only what changed)...
set DQIX_NOPAUSE=1
call BUILD.bat
if errorlevel 1 goto build_failed
"%BASH%" -lc "%PYRUN% mods/tools/build_stamp.py . write; $PY mods/tools/catalog.py . >/dev/null 2>&1"
exit /b 0

:wrong_place
echo The "mods" folder has to be inside the DQIX Enhanced folder (the one with BUILD.bat).
if not defined WHAT pause
exit /b 1
:no_tools
echo The build tools (MSYS2) aren't ready: run BUILD.bat once, then this again.
if not defined WHAT pause
exit /b 1
:list_failed
echo.
echo The cheat list couldn't be made (see above).
if not defined WHAT pause
exit /b 1
:game_running
echo.
echo The mods changed and the game has to be rebuilt, but it is still running.
echo Close the game, then try again.
if not defined WHAT pause
exit /b 3
:apply_failed
echo.
echo The mods couldn't be put in (see above). The game wasn't changed.
if not defined WHAT pause
exit /b 1
:build_failed
echo.
echo The build failed (see above). To go back to the game without code mods,
echo switch them all off and start this again.
if not defined WHAT pause
exit /b 1
