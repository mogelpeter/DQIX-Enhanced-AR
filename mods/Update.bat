@echo off
rem Updates DQIX Enhanced AR: looks on GitHub for a newer version and, when you say yes, downloads and installs it
rem (your settings, cheat choices and save are kept). Double-click it. It needs the internet.
rem If the updater's own files are missing in this folder it fetches the newest release by itself (the PowerShell part at the end of this file).
setlocal
title DQIX Enhanced AR - update
set "NoDefaultCurrentDirectoryInExePath="
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell.exe"
if not exist "%~dp0system\installer\Install.ps1" goto fetch
"%PS%" -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0system\installer\Install.ps1" -Update -GameFolder "%~dp0.." %*
exit /b %errorlevel%

:fetch
echo.
echo The updater's files are missing in this folder (mods\system\installer\Install.ps1).
echo Getting the newest release from GitHub and installing it over this game folder...
echo.
set "DQ_GAME=%~dp0.."
set "DQ_SELF=%~f0"
"%PS%" -NoProfile -ExecutionPolicy Bypass -STA -Command "$t = [IO.File]::ReadAllText($env:DQ_SELF); Invoke-Expression $t.Substring($t.LastIndexOf('#PSBEGIN'))"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  echo That did not work. Download the newest release yourself from
  echo https://github.com/mogelpeter/DQIX-Enhanced-AR/releases/latest and run its Install.bat.
  echo.
  pause
)
exit /b %RC%

#PSBEGIN
$ErrorActionPreference = 'Stop'
try {
    $game = (Resolve-Path -LiteralPath $env:DQ_GAME).Path
    $hdr = @{ 'User-Agent' = 'DQIX-Enhanced-AR-updater' }
    $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/mogelpeter/DQIX-Enhanced-AR/releases/latest' -Headers $hdr -TimeoutSec 30
    $asset = @($rel.assets | Where-Object { $_.name -like 'release-*.zip' })[0]
    if (-not $asset) { throw 'The newest release has no download.' }
    if ([string]$asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') { throw 'GitHub gives no SHA-256 for the download: not using it.' }
    $want = $Matches[1]
    $work = Join-Path $env:LOCALAPPDATA ('DQIX-Enhanced-AR\work-' + [guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $work -Force)
    try {
        $zip = Join-Path $work 'release.zip'
        Write-Host ('Downloading ' + $asset.name + ' ...')
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing -Headers $hdr -TimeoutSec 600
        $fs = [IO.File]::OpenRead($zip); $got = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($fs))).Replace('-', ''); $fs.Close()
        if ($got -ne $want) { throw 'The download does not match the SHA-256 GitHub states: not using it.' }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $x = Join-Path $work 'x'
        [IO.Compression.ZipFile]::ExtractToDirectory($zip, $x)
        $ps1 = Join-Path $x 'installer\Install.ps1'
        if (-not (Test-Path -LiteralPath $ps1)) { throw 'The download has no installer.' }
        & (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -NoProfile -ExecutionPolicy Bypass -STA -File $ps1 -GameFolder $game
        exit $LASTEXITCODE
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
