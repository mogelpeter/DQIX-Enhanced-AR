# Installer for DQIX Enhanced AR (cheats for DQIX Enhanced).
# Started by "Install cheats.bat". Works with Windows PowerShell 5.1 (comes with Windows 10 and 11).
#
#   1. finds your DQIX Enhanced folder (asks you in a folder window when it is not sure)
#   2. puts the files of this download into its "mods" folder (your settings stay)
#   3. builds the cheats into the game ("mods\Apply cheats.bat")
#
# Switches (for tests and for people who know what they do):
#   -GameFolder <path>   skip the question
#   -NoApply             only copy the files, do not build
#   -Quiet               no windows, no questions (the answers are the default ones), no waiting at the end
#
# This file is plain ASCII on purpose: no character can be changed by a different code page.

param(
    [Parameter(Position = 0)][string]$GameFolder = '',
    [switch]$NoApply,
    [switch]$Quiet
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:LogFile = Join-Path ([System.IO.Path]::GetTempPath()) 'dqix-cheats-install.log'
$script:Exit = 0

# ---------------------------------------------------------------- the small helpers

function Write-Log([string]$Text) {
    try { Add-Content -LiteralPath $script:LogFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Text) } catch { }
}

function Say([string]$Text, [string]$Color = 'Gray') {
    Write-Host $Text -ForegroundColor $Color
    Write-Log $Text
}

function Step([string]$Text) {
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
    Write-Log $Text
}

function Initialize-Windows {
    if ($Quiet) { return }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.Application]::EnableVisualStyles()
}

# a window that is only there to keep the dialogs in front
function New-Owner {
    $f = New-Object System.Windows.Forms.Form
    $f.TopMost = $true
    $f.ShowInTaskbar = $false
    $f.StartPosition = 'CenterScreen'
    $f.Size = New-Object System.Drawing.Size(1, 1)
    $f.Opacity = 0
    $f.Show()
    return $f
}

# buttons: 'OK', 'YesNo', 'RetryCancel'; icon: 'Information', 'Question', 'Warning', 'Error'
# returns 'OK', 'Yes', 'No', 'Retry' or 'Cancel'. With -Quiet nothing is shown and the first (default) answer is returned.
function Show-Box([string]$Text, [string]$Buttons = 'OK', [string]$Icon = 'Information') {
    if ($Quiet) {
        switch ($Buttons) { 'YesNo' { return 'Yes' } 'RetryCancel' { return 'Cancel' } default { return 'OK' } }
    }
    $owner = New-Owner
    try {
        return [System.Windows.Forms.MessageBox]::Show($owner, $Text, 'DQIX Enhanced AR - installer', $Buttons, $Icon).ToString()
    } finally {
        $owner.Close()
        $owner.Dispose()
    }
}

function Wait-Key {
    if ($Quiet) { return }
    Write-Host ''
    Write-Host 'Press Enter to close this window.' -ForegroundColor DarkGray
    [void](Read-Host)
}

# ---------------------------------------------------------------- the DQIX Enhanced folder

# a DQIX Enhanced folder has BUILD.bat in it
function Test-GameFolder([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        return (Test-Path -LiteralPath (Join-Path $Path 'BUILD.bat') -PathType Leaf)
    } catch { return $false }
}

# the folder itself, or (when somebody picked the folder around it) the one folder inside it that is one
function Resolve-GameFolder([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    $Path = $Path.Trim().Trim('"')
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $null }
    $full = (Resolve-Path -LiteralPath $Path).ProviderPath.TrimEnd('\')
    if (Test-GameFolder $full) { return $full }
    $found = @()
    foreach ($d in @(Get-ChildItem -LiteralPath $full -Directory -ErrorAction SilentlyContinue)) {
        if (Test-GameFolder $d.FullName) { $found += $d.FullName }
    }
    if ($found.Count -eq 1) { return $found[0] }
    return $null
}

function Get-RememberedFile {
    return (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'DQIX-Enhanced-AR\game-folder.txt')
}

# places where the folder usually is, best guess first
function Find-Candidates {
    $list = New-Object System.Collections.ArrayList
    $try = New-Object System.Collections.ArrayList
    $remembered = Get-RememberedFile
    if (Test-Path -LiteralPath $remembered) {
        try { [void]$try.Add(([string](Get-Content -LiteralPath $remembered -TotalCount 1))) } catch { }
    }
    [void]$try.Add($script:Here)
    [void]$try.Add((Split-Path -Parent $script:Here))
    $docs = [Environment]::GetFolderPath('MyDocuments')
    $desk = [Environment]::GetFolderPath('Desktop')
    foreach ($base in @($docs, $desk, (Join-Path $env:USERPROFILE 'Downloads'), (Join-Path $env:USERPROFILE 'Documents'), (Join-Path $env:USERPROFILE 'Desktop'), 'C:\', 'D:\')) {
        if ([string]::IsNullOrWhiteSpace($base)) { continue }
        foreach ($name in @('DQIX-Enhanced', 'DQIX Enhanced', 'dqix-enhanced', 'dqix-enhanced-main', 'DQIX', 'Games\DQIX-Enhanced')) {
            [void]$try.Add((Join-Path $base $name))
        }
    }
    foreach ($t in $try) {
        try {
            if (-not (Test-GameFolder $t)) { continue }
            $full = (Resolve-Path -LiteralPath $t).ProviderPath.TrimEnd('\')
            if (-not ($list -contains $full)) { [void]$list.Add($full) }
        } catch { }
    }
    return @($list)
}

function Select-GameFolder([string]$Start) {
    $owner = New-Owner
    try {
        while ($true) {
            $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
            $dlg.Description = "Select your DQIX Enhanced folder: the one with BUILD.bat in it (and with the folders 'game' and 'build' once the game is built)."
            $dlg.ShowNewFolderButton = $false
            if ($Start -and (Test-Path -LiteralPath $Start -PathType Container)) { $dlg.SelectedPath = $Start }
            if ($dlg.ShowDialog($owner).ToString() -ne 'OK') { return $null }
            $picked = $dlg.SelectedPath
            $resolved = Resolve-GameFolder $picked
            if ($resolved) { return $resolved }
            $a = Show-Box ("This is not a DQIX Enhanced folder:`r`n`r`n" + $picked + "`r`n`r`nThere is no BUILD.bat in it. Pick the folder you got from DQIX Enhanced (the one you installed the game with).`r`n`r`nTry again?") 'RetryCancel' 'Warning'
            if ($a -ne 'Retry') { return $null }
            $Start = $picked
        }
    } finally {
        $owner.Close()
        $owner.Dispose()
    }
}

function Get-TargetFolder {
    if ($GameFolder) {
        $r = Resolve-GameFolder $GameFolder
        if (-not $r) { throw "The folder '$GameFolder' is not a DQIX Enhanced folder (no BUILD.bat in it)." }
        return $r
    }
    $cands = @(Find-Candidates)
    $start = $null
    if ($cands.Count -ge 1) {
        $start = $cands[0]
        $a = Show-Box ("Found your DQIX Enhanced folder:`r`n`r`n" + $cands[0] + "`r`n`r`nInstall the cheats there?`r`n(No = choose another folder)") 'YesNo' 'Question'
        if ($a -eq 'Yes') { return $cands[0] }
    } else {
        [void](Show-Box "Next, choose your DQIX Enhanced folder: the one with BUILD.bat in it.`r`n`r`nDo not have it yet? Get DQIX Enhanced from github.com/sackchief/dqix-enhanced, set it up with your own ROM (its installer does that), then start this installer again." 'OK' 'Information')
    }
    if ($Quiet) { throw 'No DQIX Enhanced folder found. Give one with -GameFolder.' }
    $r = Select-GameFolder $start
    if (-not $r) { return $null }
    return $r
}

# ---------------------------------------------------------------- the files

function Get-RelativePath([string]$Base, [string]$Full) {
    $b = $Base.TrimEnd('\') + '\'
    if ($Full.StartsWith($b, [StringComparison]::OrdinalIgnoreCase)) { return $Full.Substring($b.Length) }
    throw "internal: '$Full' is not inside '$Base'"
}

function Test-SameFile([string]$A, [string]$B) {
    if (-not (Test-Path -LiteralPath $B -PathType Leaf)) { return $false }
    $fa = Get-Item -LiteralPath $A
    $fb = Get-Item -LiteralPath $B
    if ($fa.Length -ne $fb.Length) { return $false }
    $sha = [System.Security.Cryptography.SHA1]::Create()
    try {
        $ha = [BitConverter]::ToString($sha.ComputeHash([System.IO.File]::ReadAllBytes($A)))
        $hb = [BitConverter]::ToString($sha.ComputeHash([System.IO.File]::ReadAllBytes($B)))
    } finally { $sha.Dispose() }
    return ($ha -eq $hb)
}

# files that belong to the player, not to the download: never replaced when they exist, never removed
$script:KeepIfThere = @('mods\settings.txt')

function Install-Files([string]$Target) {
    $srcRoot = Join-Path $script:Here 'mods'
    $dstRoot = Join-Path $Target 'mods'
    $manifest = Join-Path $dstRoot 'system\installed-files.txt'
    if (-not (Test-Path -LiteralPath $srcRoot -PathType Container)) { throw "The 'mods' folder is missing next to the installer: $srcRoot" }

    $new = New-Object System.Collections.Generic.List[string]
    foreach ($f in @(Get-ChildItem -LiteralPath $srcRoot -Recurse -File)) {
        [void]$new.Add('mods\' + (Get-RelativePath $srcRoot $f.FullName))
    }
    $versionFile = Join-Path $script:Here 'VERSION'
    $versionRel = 'mods\system\version.txt'

    $copied = 0; $same = 0; $kept = 0
    foreach ($rel in $new) {
        $src = Join-Path $script:Here $rel
        $dst = Join-Path $Target $rel
        if (($script:KeepIfThere -contains $rel) -and (Test-Path -LiteralPath $dst)) { $kept++; continue }
        if (Test-SameFile $src $dst) { $same++; continue }
        $dir = Split-Path -Parent $dst
        if (-not (Test-Path -LiteralPath $dir)) { [void](New-Item -ItemType Directory -Path $dir -Force) }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copied++
    }

    # the version of this download, so the game folder says what is in it
    if (Test-Path -LiteralPath $versionFile) {
        $vdst = Join-Path $Target $versionRel
        if (-not (Test-Path -LiteralPath (Split-Path -Parent $vdst))) { [void](New-Item -ItemType Directory -Path (Split-Path -Parent $vdst) -Force) }
        Copy-Item -LiteralPath $versionFile -Destination $vdst -Force
        [void]$new.Add($versionRel)
    }

    # files an older download had and this one has not (copying never deletes by itself)
    $removed = 0
    $old = @()
    if (Test-Path -LiteralPath $manifest) { $old = @(Get-Content -LiteralPath $manifest) }
    foreach ($rel in $old) {
        $rel = $rel.Trim()
        if (-not $rel.StartsWith('mods\')) { continue }
        if ($rel.Contains('..')) { continue }
        if ($new -contains $rel) { continue }
        if ($script:KeepIfThere -contains $rel) { continue }
        $p = Join-Path $Target $rel
        if (Test-Path -LiteralPath $p -PathType Leaf) { Remove-Item -LiteralPath $p -Force; $removed++ }
    }
    # names of earlier versions of this installer's files
    foreach ($rel in @('mods\Play with mods.bat', 'mods\system\cheats\no-touch-battles.txt')) {
        $p = Join-Path $Target $rel
        if (Test-Path -LiteralPath $p -PathType Leaf) { Remove-Item -LiteralPath $p -Force; $removed++ }
    }
    # folders that were left empty
    foreach ($d in @(Get-ChildItem -LiteralPath $dstRoot -Recurse -Directory -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length } -Descending)) {
        if (@(Get-ChildItem -LiteralPath $d.FullName -Force -ErrorAction SilentlyContinue).Count -eq 0) {
            Remove-Item -LiteralPath $d.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    Set-Content -LiteralPath $manifest -Value @($new) -Encoding ASCII

    # files from a downloaded ZIP carry a "from the internet" mark that makes Windows ask questions; take it off the copies
    try { Get-ChildItem -LiteralPath $dstRoot -Recurse -File | Unblock-File -ErrorAction SilentlyContinue } catch { }

    Say ("  {0} files put in, {1} were already up to date, {2} removed (not in this download any more), {3} of yours left as they are." -f $copied, $same, $removed, $kept) 'Gray'
}

# ---------------------------------------------------------------- the game must not run

function Wait-GameClosed {
    while ($true) {
        $p = @(Get-Process -Name 'dqix' -ErrorAction SilentlyContinue)
        if ($p.Count -eq 0) { return $true }
        $a = Show-Box "DQIX is running. Close the game, then press Retry.`r`n(The cheats are built into the game, which cannot be rebuilt while it runs.)" 'RetryCancel' 'Warning'
        if ($a -ne 'Retry') { return $false }
    }
}

# ---------------------------------------------------------------- main

function Invoke-Install {
    $version = '?'
    $vf = Join-Path $script:Here 'VERSION'
    if (Test-Path -LiteralPath $vf) { $version = ([string](Get-Content -LiteralPath $vf -TotalCount 1)).Trim() }

    Write-Host ''
    Write-Host ('  DQIX Enhanced AR - installer   (version ' + $version + ')') -ForegroundColor White
    Write-Host '  Cheats for DQIX Enhanced: put into your game and built in.' -ForegroundColor DarkGray
    Write-Log ('start, version ' + $version + ', from ' + $script:Here)

    Initialize-Windows

    Step '[1/4] Looking for your DQIX Enhanced folder...'
    $target = Get-TargetFolder
    if (-not $target) {
        Say 'Cancelled: no folder chosen. Nothing was changed.' 'Yellow'
        $script:Exit = 2
        return
    }
    Say ('  ' + $target) 'White'
    try {
        $mem = Get-RememberedFile
        if (-not (Test-Path -LiteralPath (Split-Path -Parent $mem))) { [void](New-Item -ItemType Directory -Path (Split-Path -Parent $mem) -Force) }
        Set-Content -LiteralPath $mem -Value $target -Encoding ASCII
    } catch { }

    $built = (Test-Path -LiteralPath (Join-Path $target 'game\dqix.exe'))
    if (-not $built -and -not $NoApply) {
        $a = Show-Box ("The game in this folder is not built yet:`r`n`r`n" + $target + "`r`n`r`nThe installer will build it now, together with the cheats. That asks for your own Dragon Quest IX ROM (.nds) and takes 10 to 20 minutes the first time.`r`n`r`nContinue?") 'YesNo' 'Question'
        if ($a -ne 'Yes') { Say 'Cancelled. Nothing was changed.' 'Yellow'; $script:Exit = 2; return }
    }

    Step '[2/4] Checking that the game is closed...'
    if (-not (Wait-GameClosed)) {
        Say 'Cancelled: the game is still running. Nothing was changed.' 'Yellow'
        $script:Exit = 2
        return
    }
    Say '  ok' 'Gray'

    Step '[3/4] Putting the files in...'
    Install-Files $target

    if ($NoApply) {
        Step '[4/4] Building skipped (-NoApply).'
        return
    }

    Step '[4/4] Building the cheats into the game (the first time this takes a few minutes; black windows are normal)...'
    $apply = Join-Path $target 'mods\Apply cheats.bat'
    if (-not (Test-Path -LiteralPath $apply)) { throw "The file was not put in: $apply" }
    Remove-Item Env:NoDefaultCurrentDirectoryInExePath -ErrorAction SilentlyContinue
    $env:DQIX_NOPAUSE = '1'
    $cmd = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $argLine = '/d /c ""' + $apply + '" apply"'
    $p = Start-Process -FilePath $cmd -ArgumentList $argLine -WorkingDirectory $target -NoNewWindow -Wait -PassThru
    $rc = $p.ExitCode
    Write-Log ('Apply cheats.bat ended with ' + $rc)
    if ($rc -eq 3) {
        throw 'The game was started while it was being built. Close it and start this installer again.'
    }
    if ($rc -ne 0) {
        throw ("Building the cheats into the game failed (code $rc). The details are above and in:`r`n" + (Join-Path $target 'mods\system\bin\build.log'))
    }

    Write-Host ''
    Say 'Done. The Cheats tab is in the game.' 'Green'
    Say 'Start the game as always. In its menu bar: Cheats > Cheats...   Nothing is switched on until you do it.' 'Green'
    $a = Show-Box ("Done. The cheats are installed.`r`n`r`nIn the game's menu bar: Cheats > Cheats...`r`nNothing is switched on until you do it.`r`n`r`nStart the game now?") 'YesNo' 'Information'
    if ($a -eq 'Yes' -and -not $Quiet) {
        $play = Join-Path $target 'game\play.bat'
        if (Test-Path -LiteralPath $play) {
            Start-Process -FilePath $cmd -ArgumentList ('/d /c ""' + $play + '""') -WorkingDirectory (Join-Path $target 'game') -WindowStyle Minimized
        }
    }
}

try {
    Invoke-Install
} catch {
    $msg = $_.Exception.Message
    Write-Log ('ERROR: ' + $msg)
    Write-Log ($_ | Out-String)
    Write-Host ''
    Write-Host ('Something went wrong: ' + $msg) -ForegroundColor Red
    Write-Host ('(a log of this run: ' + $script:LogFile + ')') -ForegroundColor DarkGray
    try { [void](Show-Box ("Something went wrong:`r`n`r`n" + $msg + "`r`n`r`nA log of this run is in:`r`n" + $script:LogFile) 'OK' 'Error') } catch { }
    $script:Exit = 1
}
Wait-Key
exit $script:Exit
