@echo off
rem Builds every plugin in mods\plugins\src\<name>\ into mods\plugins\<name>.dll, with the compiler the game is
rem built with (MSYS2 UCRT64). The game loads them the next time it starts: menu bar, Plugins.
rem   Build plugins.bat            all of them
rem   Build plugins.bat performance   only that one
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "MSYS=C:\msys64"
if exist "%HERE%..\system\msys2-root.txt" set /p MSYS=<"%HERE%..\system\msys2-root.txt"
set "PATH=%MSYS%\ucrt64\bin;%MSYS%\mingw64\bin;%PATH%"
where gcc >nul 2>nul || (echo gcc not found: install MSYS2 with its UCRT64 compiler, or build the game once first. & exit /b 1)
set FAILED=0
for /d %%D in ("%HERE%src\*") do (
    if "%~1"=="" (set "GO=1") else (if /i "%~1"=="%%~nxD" (set "GO=1") else (set "GO="))
    if defined GO (
        gcc -shared -O2 -static-libgcc -I"%HERE%sdk" -o "%HERE%%%~nxD.dll" "%%D\*.c" && (echo   built mods\plugins\%%~nxD.dll) || (echo   FAILED: %%~nxD & set FAILED=1)
    )
)
if "%FAILED%"=="1" exit /b 1
echo Start the game: the plugins are in the menu bar under Plugins.
