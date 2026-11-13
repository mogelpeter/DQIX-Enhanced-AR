@echo off
rem Developer helper for the mods (see WORKFLOW.md):  dev doctor | deploy | menu | shot | test fast | test full | scratch
rem Works on any PC: uses the Python on the PATH, else the one of the MSYS2 build tools.
setlocal
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  if exist "%~dp0msys2-root.txt" set /p MS=<"%~dp0msys2-root.txt"
  if not defined MS set "MS=C:\msys64"
  if exist "%MS%\ucrt64\bin\python.exe" set "PY=%MS%\ucrt64\bin\python.exe"
)
if not defined PY ( echo No Python found. Install Python 3.8+ from python.org ^(tick "Add to PATH"^) and try again. & exit /b 1 )
set NoDefaultCurrentDirectoryInExePath=
%PY% "%~dp0tools\dev.py" %*
exit /b %errorlevel%
