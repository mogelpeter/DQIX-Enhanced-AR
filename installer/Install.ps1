# Installer for DQIX Enhanced AR (cheats for DQIX Enhanced).
# Started by "Install.bat". Works with Windows PowerShell 5.1 (comes with Windows 10 and 11).
#
#   1. finds your DQIX Enhanced folder (asks you in a folder window when it is not sure)
#   2. puts the files of this download into its "mods" folder (your settings stay)
#   3. builds the cheats into the game ("mods\Apply.bat")
# Before that it checks the requirements (and offers to fix what is missing) once, and looks on GitHub for a newer
# version of itself. "mods\Update.bat" in the game folder runs just the update.
#
# Switches (for tests and for people who know what they do):
#   -GameFolder <path>   skip the question
#   -NoApply             only copy the files, do not build
#   -Quiet               no windows, no questions (the answers are the default ones), no waiting at the end
#   -Update              only look for a newer version and install it (mods\Update.bat)
#   -Recheck             check the requirements again even if they were checked before
#   -NoUpdateCheck       do not look for a newer version
#   -UpdateCheck         look for a newer version even with -Quiet
#   -Auto                the game asked for the update: no questions, starts the game again at the end (mods\Update.bat -Auto)
#
# This file is plain ASCII on purpose: no character can be changed by a different code page.

param(
    [Parameter(Position = 0)][string]$GameFolder = '',
    [switch]$NoApply,
    [switch]$Quiet,
    [switch]$Update,
    [switch]$Recheck,
    [switch]$NoUpdateCheck,
    [switch]$UpdateCheck,
    [switch]$Auto
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# this file is in the folder 'installer'; the download's own folder (with Install.bat and mods) is the one around it
$script:Here = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$script:LogFile = Join-Path ([System.IO.Path]::GetTempPath()) 'dqix-cheats-install.log'
$script:Exit = 0
$script:Handed = $false      # a newer installer took over: it does the waiting at the end
$script:Repo = 'mogelpeter/DQIX-Enhanced-AR'
$script:GameRepoZip = 'https://github.com/sackchief/dqix-enhanced/archive/HEAD.zip'

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
    if ($Quiet -or ($Auto -and $script:Exit -eq 0)) { return }
    Write-Host ''
    Write-Host 'Press Enter to close this window.' -ForegroundColor DarkGray
    [void](Read-Host)
}

# ---------------------------------------------------------------- downloads, remembered answers

function Initialize-Net {
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
    $global:ProgressPreference = 'SilentlyContinue'
}

function Test-Online {
    try {
        Initialize-Net
        $r = Invoke-WebRequest -Uri 'https://github.com' -Method Head -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch { return $false }
}

function Get-File([string]$Url, [string]$Dest) {
    Initialize-Net
    Write-Log ('download ' + $Url)
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -TimeoutSec 600 -Headers @{ 'User-Agent' = 'DQIX-Enhanced-AR-installer' }
    if (-not (Test-Path -LiteralPath $Dest) -or (Get-Item -LiteralPath $Dest).Length -lt 1024) { throw "The download failed: $Url" }
}

# the .NET zip reader itself: Expand-Archive depends on which PowerShell modules are on the path
function Expand-Zip([string]$Zip, [string]$Dest) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($Zip, $Dest)
}

function New-TempFolder {
    $d = Join-Path (Get-StateDir) ('work-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    [void](New-Item -ItemType Directory -Path $d -Force)
    return $d
}

# what was checked before: %LOCALAPPDATA%\DQIX-Enhanced-AR\requirements.txt, lines of key=value
function Get-StateFile {
    return (Join-Path (Get-StateDir) 'requirements.txt')
}

function Read-State {
    $h = @{}
    $f = Get-StateFile
    if (Test-Path -LiteralPath $f) {
        foreach ($l in @(Get-Content -LiteralPath $f -ErrorAction SilentlyContinue)) {
            $i = ([string]$l).IndexOf('=')
            if ($i -gt 0) { $h[$l.Substring(0, $i).Trim()] = $l.Substring($i + 1).Trim() }
        }
    }
    return $h
}

function Write-State([hashtable]$H) {
    try {
        $f = Get-StateFile
        if (-not (Test-Path -LiteralPath (Split-Path -Parent $f))) { [void](New-Item -ItemType Directory -Path (Split-Path -Parent $f) -Force) }
        $lines = @(); foreach ($k in ($H.Keys | Sort-Object)) { $lines += ($k + '=' + $H[$k]) }
        Set-Content -LiteralPath $f -Value $lines -Encoding ASCII
    } catch { }
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

function Get-StateDir {
    if ($env:DQIX_AR_STATE_DIR) { return $env:DQIX_AR_STATE_DIR }       # for tests: keeps them away from the real remembered answers
    return (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'DQIX-Enhanced-AR')
}

function Get-RememberedFile {
    return (Join-Path (Get-StateDir) 'game-folder.txt')
}

# the version of the cheats that are installed in a game folder (mods\system\version.txt), or $null
function Get-InstalledVersion([string]$Folder) {
    $f = Join-Path $Folder 'mods\system\version.txt'
    if (Test-Path -LiteralPath $f) {
        $v = ([string](Get-Content -LiteralPath $f -TotalCount 1)).Trim()
        if ($v -match '^\d+\.\d+\.\d+$') { return $v }
    }
    return $null
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
    $with = @($list | Where-Object { Get-InstalledVersion $_ })
    $without = @($list | Where-Object { -not (Get-InstalledVersion $_) })
    return @($with + $without)
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

# downloads DQIX Enhanced (the game's own files, as the "Download ZIP" button gives them) into <Parent>\DQIX-Enhanced
function Install-GameFolder([string]$Parent) {
    $tmp = New-TempFolder
    try {
        if (-not (Test-Online)) { Say '  No internet connection: cannot download DQIX Enhanced.' 'Yellow'; return $null }
        Say '  Downloading DQIX Enhanced from github.com/sackchief/dqix-enhanced ...' 'Gray'
        $zip = Join-Path $tmp 'game.zip'
        Get-File $script:GameRepoZip $zip
        Say '  Unpacking ...' 'Gray'
        Expand-Zip $zip (Join-Path $tmp 'x')
        $inner = @(Get-ChildItem -LiteralPath (Join-Path $tmp 'x') -Directory | Where-Object { Test-GameFolder $_.FullName })
        if ($inner.Count -ne 1) { throw 'The download does not look like DQIX Enhanced (no BUILD.bat in it).' }
        $dest = Join-Path $Parent 'DQIX-Enhanced'
        $n = 2
        while (Test-Path -LiteralPath $dest) { $dest = Join-Path $Parent ('DQIX-Enhanced-' + $n); $n++ }
        Move-Item -LiteralPath $inner[0].FullName -Destination $dest
        Say ('  DQIX Enhanced is now in ' + $dest) 'Green'
        return $dest
    } catch {
        Say ('  ' + $_.Exception.Message) 'Yellow'
        return $null
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
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
        $iv = Get-InstalledVersion $cands[0]
        $what = 'The cheats are not installed there yet.'
        if ($iv) { $what = 'The cheats are already installed there (version ' + $iv + '); the installer will check for an update.' }
        $a = Show-Box ("Found your DQIX Enhanced folder:`r`n`r`n" + $cands[0] + "`r`n`r`n" + $what + "`r`n`r`nUse this folder?`r`n(No = choose another folder)") 'YesNo' 'Question'
        if ($a -eq 'Yes') { return $cands[0] }
    } else {
        if ($Quiet) { throw 'No DQIX Enhanced folder found. Give one with -GameFolder.' }
        $docs = [Environment]::GetFolderPath('MyDocuments')
        $a = Show-Box ("No DQIX Enhanced folder was found on this PC.`r`n`r`nDQIX Enhanced is the game these cheats go into. Download it now from github.com/sackchief/dqix-enhanced and put it in:`r`n`r`n" + (Join-Path $docs 'DQIX-Enhanced') + "`r`n`r`nYes = download it (needs the internet)`r`nNo = I have it already: let me choose the folder") 'YesNo' 'Question'
        if ($a -eq 'Yes') {
            $r = Install-GameFolder $docs
            if ($r) { return $r }
            [void](Show-Box 'The download did not work. Choose your DQIX Enhanced folder yourself, or get the game from github.com/sackchief/dqix-enhanced and start this installer again.' 'OK' 'Warning')
        }
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
    foreach ($rel in @('mods\Apply cheats.bat', 'mods\Play with mods.bat', 'mods\system\cheats\no-touch-battles.txt')) {
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

# ---------------------------------------------------------------- the requirements

function Get-MsysRoot([string]$Target) {
    $f = Join-Path $Target 'mods\system\msys2-root.txt'
    $c = @()
    if (Test-Path -LiteralPath $f) { $c += ([string](Get-Content -LiteralPath $f -TotalCount 1)).Trim() }
    $c += 'C:\msys64'
    foreach ($r in $c) { if ($r -and (Test-Path -LiteralPath (Join-Path $r 'usr\bin\bash.exe'))) { return $r } }
    return $null
}

function Get-Csc {
    foreach ($d in @('Framework64', 'Framework')) {
        $p = Join-Path $env:WINDIR ('Microsoft.NET\' + $d + '\v4.0.30319\csc.exe')
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Get-Rom([string]$Target) {
    $rom = Join-Path $Target 'rom'
    if (Test-Path -LiteralPath $rom) {
        foreach ($pat in @('*.nds', '*.zip')) {
            $f = @(Get-ChildItem -LiteralPath $rom -Filter $pat -File -ErrorAction SilentlyContinue)
            if ($f.Count -gt 0) { return $f[0].FullName }
        }
    }
    return $null
}

# asks for the ROM and copies it to <game>\rom (the build takes it from there). Returns the path or $null.
function Request-Rom([string]$Target) {
    if ($Quiet) { return $null }
    [void](Show-Box "Your Dragon Quest IX ROM is needed to build the game.`r`n`r`nIt is the .nds file you made from your own cartridge (a .zip with it inside also works). It stays on this PC, nothing is uploaded.`r`n`r`nChoose the file in the next window." 'OK' 'Information')
    $owner = New-Owner
    try {
        $dlg = New-Object System.Windows.Forms.OpenFileDialog
        $dlg.Title = 'Choose your Dragon Quest IX ROM (.nds or .zip)'
        $dlg.Filter = 'Nintendo DS ROM (*.nds;*.zip)|*.nds;*.zip|All files (*.*)|*.*'
        if ($dlg.ShowDialog($owner).ToString() -ne 'OK') { return $null }
        $romDir = Join-Path $Target 'rom'
        if (-not (Test-Path -LiteralPath $romDir)) { [void](New-Item -ItemType Directory -Path $romDir -Force) }
        $dst = Join-Path $romDir (Split-Path -Leaf $dlg.FileName)
        Copy-Item -LiteralPath $dlg.FileName -Destination $dst -Force
        return $dst
    } finally { $owner.Close(); $owner.Dispose() }
}

function Report-Req([bool]$Ok, [string]$What) {
    if ($Ok) { Say ('  ok       ' + $What) 'Gray' } else { Say ('  MISSING  ' + $What) 'Yellow' }
}

# prints one line per requirement and fixes what it can with the player's OK. Returns $false when the player stops
# (or something that cannot be fixed here is missing).
function Test-Requirements([string]$Target, [bool]$Built) {
    $os64 = [Environment]::Is64BitOperatingSystem
    Report-Req $os64 'Windows 10 or 11, 64-bit'
    if (-not $os64) { [void](Show-Box 'This needs a 64-bit Windows 10 or 11. The game and its build tools do not run on 32-bit Windows.' 'OK' 'Error'); return $false }
    Report-Req ($PSVersionTable.PSVersion.Major -ge 5) ('Windows PowerShell ' + $PSVersionTable.PSVersion)

    $writable = $false
    try {
        $t = Join-Path $Target ('.write-test-' + [Guid]::NewGuid().ToString('N').Substring(0, 6))
        Set-Content -LiteralPath $t -Value 'x'; Remove-Item -LiteralPath $t -Force; $writable = $true
    } catch { }
    Report-Req $writable ('Write access to ' + $Target)
    if (-not $writable) {
        [void](Show-Box ("The installer cannot write into this folder:`r`n`r`n" + $Target + "`r`n`r`nMove DQIX Enhanced to a normal place such as Documents (not Program Files), then start this installer again.") 'OK' 'Error')
        return $false
    }
    if ($Target -match '\\OneDrive[^\\]*\\') {
        Say '  note: the game folder is inside OneDrive. Syncing can disturb the build; a folder in Documents outside OneDrive is safer.' 'Yellow'
    }

    # free space: 4 GB for a first build, 0.5 GB otherwise
    $need = 0.5
    if (-not $Built) { $need = 4 }
    try {
        $drive = New-Object System.IO.DriveInfo ($Target.Substring(0, 1))
        $free = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
        Report-Req ($free -ge $need) ('Free space on ' + $drive.Name + ' ' + $free + ' GB (needs ' + $need + ' GB)')
        if ($free -lt $need) {
            $a = Show-Box ("Only " + $free + " GB are free on " + $drive.Name + "; about " + $need + " GB are needed.`r`n`r`nFree some space and press Retry, or Cancel to stop.") 'RetryCancel' 'Warning'
            if ($a -eq 'Retry') { return (Test-Requirements $Target $Built) }
            return $false
        }
    } catch { }

    if (-not $Built) {
        # the first build: the ROM, the build tools (MSYS2), the internet
        $rom = Get-Rom $Target
        Report-Req ($null -ne $rom) 'Your Dragon Quest IX ROM in the "rom" folder'
        if (-not $rom) {
            $rom = Request-Rom $Target
            if (-not $rom) { Say '  No ROM chosen.' 'Yellow'; return $false }
            Say ('  ok       ROM copied to ' + $rom) 'Green'
        }
        $msys = Get-MsysRoot $Target
        if ($msys) { Report-Req $true ('Build tools (MSYS2): ' + $msys) } else { Say '  to do    Build tools (MSYS2): the build installs them for you (free, a few hundred MB)' 'Yellow' }
        $online = Test-Online
        Report-Req $online 'Internet connection'
        if (-not $online -and -not $msys) {
            while (-not $online) {
                $a = Show-Box "There is no internet connection, and the build tools (MSYS2) have to be downloaded for the first build.`r`n`r`nConnect to the internet and press Retry, or Cancel to stop." 'RetryCancel' 'Warning'
                if ($a -ne 'Retry') { return $false }
                $online = Test-Online
            }
            Report-Req $true 'Internet connection'
        }
    }

    $csc = Get-Csc
    Report-Req ($null -ne $csc) 'C# compiler of .NET Framework 4 (for the save editor helper)'
    if (-not $csc) {
        $a = Show-Box ("The save editor helper needs .NET Framework 4, which is part of Windows but switched off here.`r`n`r`nThe cheats work without it; only Cheats > Save editor needs it.`r`n`r`nOpen the Windows features window now to switch it on? (tick '.NET Framework 4.8 Advanced Services', press OK there, then come back)") 'YesNo' 'Question'
        if ($a -eq 'Yes') {
            try { Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\OptionalFeatures.exe') -Wait } catch { }
            Report-Req ($null -ne (Get-Csc)) 'C# compiler (after the change)'
        }
    }
    return $true
}

# ---------------------------------------------------------------- updates

# the version of this download (the folder around installer\)
function Get-OwnVersion {
    $f = Join-Path $script:Here 'VERSION'
    if (Test-Path -LiteralPath $f) {
        $v = ([string](Get-Content -LiteralPath $f -TotalCount 1)).Trim()
        if ($v -match '^\d+\.\d+\.\d+$') { return $v }
    }
    return $null
}

function Get-LatestRelease {
    try {
        Initialize-Net
        $api = 'https://api.github.com/repos/' + $script:Repo + '/releases/latest'
        if ($env:DQIX_AR_API) { $api = $env:DQIX_AR_API }       # for tests: a local server that pretends to be GitHub
        $r = Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent' = 'DQIX-Enhanced-AR-installer' } -TimeoutSec 10
        $tag = ([string]$r.tag_name).TrimStart('v')
        if ($tag -notmatch '^\d+\.\d+\.\d+$') { return $null }
        $asset = @($r.assets | Where-Object { $_.name -like 'release-*.zip' }) | Select-Object -First 1
        if (-not $asset) { return $null }
        return @{ Version = $tag; Url = [string]$asset.browser_download_url; Page = [string]$r.html_url; Digest = [string]$asset.digest }
    } catch { Write-Log ('update check failed: ' + $_.Exception.Message); return $null }
}

# looks for a newer release; when there is one and the player agrees, downloads it and lets ITS installer do the job.
# Returns $true when a newer installer took over (this one is finished then).
function Invoke-UpdateCheck([string]$Target, [string]$Current) {
    if (-not $Current) { return $false }
    $rel = Get-LatestRelease
    if (-not $rel) {
        if ($Update) { Say 'Could not look for a newer version (no internet?).' 'Yellow' }
        return $false
    }
    if ([version]$rel.Version -le [version]$Current) {
        Say ('  Up to date: you have version ' + $Current + ', the newest is ' + $rel.Version + '.') 'Gray'
        if ($Update -and -not $Auto) { [void](Show-Box ('You have the newest version (' + $Current + ').') 'OK' 'Information') }
        return $false
    }
    Say ('  A newer version is available: ' + $rel.Version + ' (you have ' + $Current + ').') 'Cyan'
    $a = 'Yes'
    if (-not $Auto) { $a = Show-Box ("A newer version of DQIX Enhanced AR is available.`r`n`r`nYou have: " + $Current + "`r`nNewest:   " + $rel.Version + "`r`n`r`nWhat is new: " + $rel.Page + "`r`n`r`nDownload and install it now? Your settings, your cheat choices and your save are kept.") 'YesNo' 'Question' }
    if ($a -ne 'Yes') { Say '  Staying with the version you have.' 'Gray'; return $false }

    $tmp = New-TempFolder
    try {
        Say ('  Downloading version ' + $rel.Version + ' ...') 'Gray'
        $zip = Join-Path $tmp 'release.zip'
        Get-File $rel.Url $zip
        # what GitHub says the file is (sha256) must be what arrived; nothing of it runs otherwise
        $want = ([string]$rel.Digest).Replace('sha256:', '').Trim().ToLower()
        if ($want -match '^[0-9a-f]{64}$') {
            $got = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
            if ($got -ne $want) { throw 'The downloaded file does not match the checksum GitHub states for it. It was not used.' }
            Say '  Checksum (SHA-256) of the download is correct.' 'Gray'
        } elseif (-not $env:DQIX_AR_API) {
            throw 'GitHub gave no checksum for the download, so it was not used.'
        }
        Expand-Zip $zip (Join-Path $tmp 'new')
        $root = Join-Path $tmp 'new'
        if (-not (Test-Path -LiteralPath (Join-Path $root 'installer\Install.ps1'))) {
            $in = @(Get-ChildItem -LiteralPath $root -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'installer\Install.ps1') })
            if ($in.Count -eq 1) { $root = $in[0].FullName }
        }
        $newPs1 = Join-Path $root 'installer\Install.ps1'
        if (-not (Test-Path -LiteralPath $newPs1) -or -not (Test-Path -LiteralPath (Join-Path $root 'mods\Apply.bat'))) { throw 'The downloaded update is not complete (no installer or mods folder in it).' }
        $nv = ([string](Get-Content -LiteralPath (Join-Path $root 'VERSION') -TotalCount 1)).Trim()
        if ($nv -ne $rel.Version) { throw ('The downloaded update says it is version ' + $nv + ', not ' + $rel.Version + '.') }

        Say ('  Installing version ' + $rel.Version + ' ...') 'Cyan'
        $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', ('"' + $newPs1 + '"'), '-GameFolder', ('"' + $Target + '"'))
        if ($NoApply) { $argList += '-NoApply' }
        if ($Quiet) { $argList += '-Quiet' }
        if ($Auto) { $argList += '-Auto' }
        $p = Start-Process -FilePath $ps -ArgumentList $argList -Wait -PassThru -NoNewWindow
        Write-Log ('the new installer ended with ' + $p.ExitCode)
        $script:Exit = $p.ExitCode
        $script:Handed = $true
        return $true
    } catch {
        Say ('  The update did not work: ' + $_.Exception.Message) 'Yellow'
        Say '  Continuing with the version you have.' 'Yellow'
        return $false
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
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

    Step '[1/5] Looking for your DQIX Enhanced folder...'
    $target = Get-TargetFolder
    if (-not $target) {
        Say 'Cancelled: no folder chosen. Nothing was changed.' 'Yellow'
        $script:Exit = 2
        return
    }
    Say ('  ' + $target) 'White'
    if (-not $Quiet -or $env:DQIX_AR_STATE_DIR) { try {
        $mem = Get-RememberedFile
        if (-not (Test-Path -LiteralPath (Split-Path -Parent $mem))) { [void](New-Item -ItemType Directory -Path (Split-Path -Parent $mem) -Force) }
        Set-Content -LiteralPath $mem -Value $target -Encoding ASCII
    } catch { } }

    $built = (Test-Path -LiteralPath (Join-Path $target 'game\dqix.exe'))

    # is it installed already, and is there a newer version on GitHub? (not with -Quiet, unless asked; mods\Update.bat does only this)
    $installed = Get-InstalledVersion $target
    $mine = Get-OwnVersion
    if ($Update) { $mine = $installed }
    if ($installed -and $Update) { Say ('  The cheats are installed here: version ' + $installed + '.') 'Gray' }
    elseif ($installed) { Say ('  The cheats are installed here: version ' + $installed + '. This download is version ' + $mine + '.') 'Gray' }
    else { Say '  The cheats are not installed here yet.' 'Gray' }
    $current = $mine
    if ($installed -and (-not $mine -or [version]$installed -gt [version]$mine)) { $current = $installed }
    if ($Update -or ($UpdateCheck) -or (-not $Quiet -and -not $NoUpdateCheck)) {
        Step '[2/5] Looking for a newer version...'
        if (Invoke-UpdateCheck $target $current) { return }
    }
    if ($Update) { return }
    if ($installed -and $mine -and [version]$installed -gt [version]$mine) {
        $a = Show-Box ("Version " + $installed + " of the cheats is already installed, and it is newer than this download (" + $mine + ").`r`n`r`nKeep the installed version?") 'YesNo' 'Question'
        if ($a -eq 'Yes') { Say '  Keeping the installed version. Nothing was changed.' 'Green'; return }
    } elseif ($installed -and $mine -and $installed -eq $mine -and -not $Quiet -and -not $Recheck) {
        $a = Show-Box ("The newest version (" + $installed + ") is already installed here.`r`n`r`nReinstall / repair it anyway? (The game is rebuilt only if something changed.)") 'YesNo' 'Question'
        if ($a -ne 'Yes') { Say '  Already up to date. Nothing was changed.' 'Green'; return }
    }

    # the requirements: checked once, then remembered for this folder
    Step '[3/5] Checking the requirements...'
    $state = Read-State
    $known = $false
    if (-not $Recheck -and $built -and $state.ContainsKey('checked') -and $state['game'] -eq $target) { $known = $true }
    if ($known) {
        Say ('  Checked before (' + $state['checked'] + '): everything was fine. Run the installer with -Recheck to check again.') 'Gray'
    } else {
        if (-not (Test-Requirements $target $built)) {
            Say 'Stopped: a requirement is missing. Nothing was changed.' 'Yellow'
            $script:Exit = 2
            return
        }
        if (($built -or $NoApply) -and (-not $Quiet -or $env:DQIX_AR_STATE_DIR)) { Write-State @{ checked = (Get-Date -Format 'yyyy-MM-dd'); game = $target } }
    }

    if (-not $built -and -not $NoApply) {
        $a = Show-Box ("The game in this folder is not built yet:`r`n`r`n" + $target + "`r`n`r`nThe installer will build it now, together with the cheats. This installs the free build tools (MSYS2) if needed and takes 10 to 20 minutes the first time.`r`n`r`nContinue?") 'YesNo' 'Question'
        if ($a -ne 'Yes') { Say 'Cancelled. Nothing was changed.' 'Yellow'; $script:Exit = 2; return }
    }

    Step '[4/5] Checking that the game is closed...'
    if (-not (Wait-GameClosed)) {
        Say 'Cancelled: the game is still running. Nothing was changed.' 'Yellow'
        $script:Exit = 2
        return
    }
    Say '  ok' 'Gray'

    Step '[4/5] Putting the files in...'
    Install-Files $target

    if ($NoApply) {
        Step '[5/5] Building skipped (-NoApply).'
        return
    }

    Step '[5/5] Building the cheats into the game (the first time this takes a few minutes; black windows are normal)...'
    $apply = Join-Path $target 'mods\Apply.bat'
    if (-not (Test-Path -LiteralPath $apply)) { throw "The file was not put in: $apply" }
    Remove-Item Env:NoDefaultCurrentDirectoryInExePath -ErrorAction SilentlyContinue
    $env:DQIX_NOPAUSE = '1'
    $cmd = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $argLine = '/d /c ""' + $apply + '" apply"'
    $p = Start-Process -FilePath $cmd -ArgumentList $argLine -WorkingDirectory $target -NoNewWindow -Wait -PassThru
    $rc = $p.ExitCode
    Write-Log ('Apply.bat ended with ' + $rc)
    if ($rc -eq 3) {
        throw 'The game was started while it was being built. Close it and start this installer again.'
    }
    if ($rc -ne 0) {
        throw ("Building the cheats into the game failed (code $rc). The details are above and in:`r`n" + (Join-Path $target 'mods\system\bin\build.log'))
    }

    if (-not $Quiet -or $env:DQIX_AR_STATE_DIR) { Write-State @{ checked = (Get-Date -Format 'yyyy-MM-dd'); game = $target } }
    Write-Host ''
    Say 'Done. The Cheats tab is in the game.' 'Green'
    Say 'Start the game as always. In its menu bar: Cheats > Cheats...   Nothing is switched on until you do it.' 'Green'
    Say 'To update later: double-click mods\Update.bat in the game folder (or run a newer Install.bat).' 'Gray'
    $a = 'Yes'
    if (-not $Auto) { $a = Show-Box ("Done. The cheats are installed.`r`n`r`nIn the game's menu bar: Cheats > Cheats...`r`nNothing is switched on until you do it.`r`n`r`nStart the game now?") 'YesNo' 'Information' }
    if ($a -eq 'Yes' -and (-not $Quiet -or $Auto)) {
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
if (-not $script:Handed) { Wait-Key }
exit $script:Exit
