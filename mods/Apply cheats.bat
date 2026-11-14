@echo off
rem The patcher for DQIX Enhanced: puts the cheats into the game and builds it. Install cheats.bat runs it,
rem the game's updater runs it after an update, and the Cheats window runs it when a built-in code mod
rem was switched. You can run it yourself any time (after an update by hand, after you changed a cheat file).
rem
rem   Apply cheats.bat            = apply, then wait for a key
rem   Apply cheats.bat apply      = the same, nothing waits (installer, updater, Cheats window)
rem   Apply cheats.bat catalog    = only make the cheat list again
rem
rem What "apply" does:
rem   1. works the cheat list out against your ROM (mods\system\tools\catalog.py)
rem   2. puts the code mods that are on, and the cheats' own part of the game (so they work with friends too),
rem      into the game's build: an update of the game takes them out, this puts them back
rem   3. rebuilds the game if they changed (only what changed: a few minutes)
rem   4. makes the save editor's helper (mods\system\src\editor\EditorHost.cs) with the C# compiler that comes with Windows
rem Then start the game as always (game\dqix.exe) and use the menu bar: Cheats > Cheats...
setlocal
cd /d "%~dp0.."
set "WHAT=%~1"
rem Windows' own tools by their full path: a PC with Git, MSYS2 or other tools early in PATH has its own "find" etc.
set "SYS32=%SystemRoot%\System32"
set "PS=%SYS32%\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"
rem some PCs don't run programs from the current folder by bare name: BUILD.bat is called by its full path
set "NoDefaultCurrentDirectoryInExePath="
rem (run by the installer or the updater: nothing may wait for a key)
if defined WHAT set DQIX_NOPAUSE=1
if not defined WHAT title DQIX Enhanced - apply cheats
if not exist "BUILD.bat" goto wrong_place
if not exist "patches.txt" goto wrong_place

rem ---- the build tools (MSYS2): the ones found last time, else the game's own finder
set "MSYSROOT="
if exist "mods\system\msys2-root.txt" set /p MSYSROOT=<"mods\system\msys2-root.txt"
if defined MSYSROOT if exist "%MSYSROOT%\usr\bin\bash.exe" goto have_msys
set "MSYSROOT="
echo Looking for the build tools (MSYS2)...
set "MSYSRES=%TEMP%\dqix-mods-%RANDOM%.txt"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "tools\msys2-setup.ps1" -Out "%MSYSRES%"
if errorlevel 1 goto no_tools
set /p MSYSROOT=<"%MSYSRES%"
del "%MSYSRES%" >nul 2>&1
if not defined MSYSROOT goto no_tools
>"mods\system\msys2-root.txt" echo %MSYSROOT%
:have_msys
set MSYSTEM=UCRT64
set CHERE_INVOKING=1
set "BASH=%MSYSROOT%\usr\bin\bash.exe"
set "PYRUN=PY=python3; command -v python3 >/dev/null 2>&1 || PY=python; $PY"

rem ---- the game has to be built once first (the mods are checked against its code)
if exist "game\dqix.exe" if exist "build\extract\arm9\arm9.bin" if exist "build\recomp\dispatch_table.c" goto built
"%SYS32%\tasklist.exe" /fi "imagename eq dqix.exe" 2>nul | "%SYS32%\find.exe" /i "dqix.exe" >nul && goto game_running
echo The game isn't built yet: building it first.
set DQIX_NOPAUSE=1
call "%CD%\BUILD.bat"
if errorlevel 1 goto build_failed
:built

if /i "%WHAT%"=="catalog" goto catalog

rem ---- the cheat list, worked out against this ROM
echo Reading the cheat list...
"%BASH%" -lc "%PYRUN% mods/system/tools/catalog.py ."
if errorlevel 1 goto list_failed

rem ---- the mods into the game (and the build, when something changed)
call :put_in
if errorlevel 1 goto end_bad

rem ---- the save editor's helper, made here from its source when it's missing or older
if not exist "mods\system\bin" mkdir "mods\system\bin"
"%BASH%" -lc "[ mods/system/bin/dqix-editor.exe -nt mods/system/src/editor/EditorHost.cs ]" && goto editor_made
set "NET=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319"
if not exist "%NET%\csc.exe" set "NET=%WINDIR%\Microsoft.NET\Framework\v4.0.30319"
if not exist "%NET%\csc.exe" goto no_csc
set "ICON="
if exist "build\icon\dqix.ico" set "ICON=-win32icon:build\icon\dqix.ico"
echo Making the save editor helper...
"%SYS32%\tasklist.exe" /fi "imagename eq dqix-editor.exe" 2>nul | "%SYS32%\find.exe" /i "dqix-editor.exe" >nul && goto editor_made
"%NET%\csc.exe" -nologo -target:winexe -platform:x64 -optimize+ "-out:mods\system\bin\dqix-editor.exe" %ICON% -r:System.Windows.Forms.dll -r:System.Core.dll "mods\system\src\editor\EditorHost.cs"
if errorlevel 1 goto no_csc
:editor_made
echo.
echo Done. Start the game as always (game\dqix.exe), then: menu bar, Cheats, Cheats...
if not defined WHAT pause
exit /b 0

:no_csc
echo.
echo The save editor helper couldn't be made (it needs the C# compiler of .NET Framework 4,
echo which comes with Windows 10 and 11). The cheats work without it; only Cheats, Save editor needs it.
if not defined WHAT pause
exit /b 0

:end_bad
exit /b %errorlevel%

:catalog
"%BASH%" -lc "%PYRUN% mods/system/tools/catalog.py ."
if errorlevel 1 exit /b 1
exit /b 0

rem ---- the mods into the game's build (mods\system\tools\put_in.sh), and the build itself when
rem      something changed. Leaves 0 = the game has them, 1 = it failed, 3 = the game is running
:put_in
"%BASH%" -lc "sh mods/system/tools/put_in.sh"
if "%errorlevel%"=="1" goto apply_failed
if not "%errorlevel%"=="10" exit /b 0
"%SYS32%\tasklist.exe" /fi "imagename eq dqix.exe" 2>nul | "%SYS32%\find.exe" /i "dqix.exe" >nul && goto game_running
echo.
echo Rebuilding the game with the mods (only what changed)...
set DQIX_NOPAUSE=1
rem (repatch.py: BUILD.bat, and when the build fails in one of the mods' places, the same without that place)
"%BASH%" -lc "%PYRUN% mods/system/tools/repatch.py ."
if errorlevel 1 goto build_failed
"%BASH%" -lc "%PYRUN% mods/system/tools/build_stamp.py . write; $PY mods/system/tools/catalog.py . >/dev/null 2>&1"
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
echo The build failed (see above; all of it is in mods\system\bin\build.log). To go back to the game without code mods,
echo switch them all off and start this again.
if not defined WHAT pause
exit /b 1
