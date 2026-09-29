<#
.SYNOPSIS
    End-user Windows installer: creates a private virtualenv, installs
    missionstudio (+ the 'gui' extra) into it, installs a vendored
    Basilisk wheel into the SAME venv if one is given, and drops a
    launcher + Start Menu shortcut.

    Windows/PowerShell counterpart of install.sh -- see that script's own
    header comment for the full design rationale (the "vendor a prebuilt
    Basilisk wheel pinned to a specific release/commit" install path, and
    why the missionstudio-only path is fully supported/tested while the
    +Basilisk-wheel path is ordinary, non-missionstudio-specific `pip`
    behavior). Most users on either platform can also just follow the
    main README's "Getting started" section directly (`python -m venv`,
    `pip install "bsk[all]"`, `pip install -e ".[dev,gui]"`) -- this
    script exists for a one-command install of a BUILT wheel, matching
    install.sh's role on Linux.

    NOT independently run against a real Windows 11 machine in this
    project's development sandbox (Linux-only, no Windows environment
    available here) -- written against documented, standard PowerShell/
    venv/pip/WScript.Shell behavior and install.sh's own already-verified
    logic (same structure, same flags, same fallback messages), but
    flagged here rather than claimed as verified end-to-end. Please
    report any issues running this on a real Windows 11 machine.

.PARAMETER Prefix
    Where to create the venv. Default: $env:LOCALAPPDATA\missionstudio

.PARAMETER BasiliskWheel
    Path or URL to a prebuilt Basilisk wheel to vendor into the venv.
    Omit this and the script installs missionstudio only, with a clear
    note that Run/Check Kernels/Monte Carlo won't work until a Basilisk
    build is added to the venv some other way.

.PARAMETER MissionstudioWheel
    Install this local wheel instead of building/fetching one (defaults
    to running build_wheel.ps1 next to this script).

.PARAMETER NoShortcut
    Skip creating a Start Menu shortcut.

.EXAMPLE
    .\install.ps1 -BasiliskWheel "bsk[all]==2.12.0"

.EXAMPLE
    .\install.ps1 -Prefix "C:\Tools\missionstudio" -NoShortcut
#>

param(
    [string]$Prefix = "$env:LOCALAPPDATA\missionstudio",
    [string]$BasiliskWheel = "",
    [string]$MissionstudioWheel = "",
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

$VenvDir = Join-Path $Prefix "venv"
Write-Host "Creating virtualenv at $VenvDir ..."
python -m venv $VenvDir
if ($LASTEXITCODE -ne 0) {
    throw "python -m venv failed (exit code $LASTEXITCODE) -- is Python installed and on PATH?"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed (exit code $LASTEXITCODE)"
}

if (-not $MissionstudioWheel) {
    Write-Host "No -MissionstudioWheel given -- building one with build_wheel.ps1 ..."
    $DistDir = Join-Path $Prefix "dist"
    & (Join-Path $ScriptDir "build_wheel.ps1") $DistDir
    # Newest-BUILT, not lexicographically-last -- same reasoning as
    # install.sh's own comment: re-running this script against the same
    # -Prefix after a version bump would otherwise leave old and new
    # wheels side by side, and a plain name sort ("missionstudio-1.10.0"
    # sorting before "missionstudio-1.9.0") would silently pick the OLDER
    # one. Sort by LastWriteTime instead.
    $MissionstudioWheel = Get-ChildItem (Join-Path $DistDir "missionstudio-*.whl") |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $MissionstudioWheel) {
        throw "build_wheel.ps1 did not produce a missionstudio-*.whl in $DistDir"
    }
}

Write-Host "Installing missionstudio (+ gui extra) from $MissionstudioWheel ..."
& $VenvPython -m pip install --quiet "$MissionstudioWheel[gui]"
if ($LASTEXITCODE -ne 0) {
    throw "pip install missionstudio failed (exit code $LASTEXITCODE)"
}

if ($BasiliskWheel) {
    Write-Host "Installing vendored Basilisk wheel from $BasiliskWheel ..."
    & $VenvPython -m pip install --quiet $BasiliskWheel
    if ($LASTEXITCODE -ne 0) {
        throw "pip install '$BasiliskWheel' failed (exit code $LASTEXITCODE)"
    }
    $BasiliskStatus = "Basilisk was installed into this venv from: $BasiliskWheel"
} else {
    $BasiliskStatus = "No Basilisk wheel was provided (-BasiliskWheel) -- 'missionstudio validate' and the " +
        "GUI will open, but Run/Check Kernels/Monte Carlo need a Basilisk build on this venv's " +
        "PYTHONPATH. Re-run this script with -BasiliskWheel, or 'pip install' one into " +
        "$VenvDir yourself, once you have one."
}

# missionstudio.exe already exists in $VenvDir\Scripts (pip installs the
# [project.scripts] entry point there automatically), but this thin
# launcher matches install.sh's own launcher role: a single stable path
# outside the venv that a Start Menu shortcut/PATH entry can point at
# without the caller needing to know venv internals.
$Launcher = Join-Path $Prefix "missionstudio.bat"
$VenvMissionstudioExe = Join-Path $VenvDir "Scripts\missionstudio.exe"
@"
@echo off
"$VenvMissionstudioExe" %*
"@ | Set-Content -Path $Launcher -Encoding ASCII

if (-not $NoShortcut) {
    $StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
    $ShortcutPath = Join-Path $StartMenuDir "missionStudio.lnk"
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Launcher
    $Shortcut.Arguments = "gui"
    $Shortcut.WorkingDirectory = $Prefix
    $Shortcut.Description = "Mission-analysis GUI built on the Basilisk astrodynamics framework"
    # No custom icon set: gui/icons.py's ensure_icon_file() (used by
    # install.sh for the Linux .desktop entry) always saves PNG data --
    # see that function's own docstring -- and a Windows .lnk's
    # IconLocation needs a real .ico/.exe/.dll, not a bare .png. Rather
    # than ship an icon file that wouldn't actually resolve, the shortcut
    # falls back to missionstudio.exe's own embedded icon. Non-fatal
    # either way, same as install.sh's own icon-render step.
    $Shortcut.Save()
    $ShortcutStatus = "Start Menu shortcut installed to $ShortcutPath"
} else {
    $ShortcutStatus = "Start Menu shortcut skipped."
}

Write-Host ""
Write-Host "Installed missionstudio to $VenvDir"
Write-Host $ShortcutStatus
Write-Host $BasiliskStatus
Write-Host ""
Write-Host "Launch it with: $Launcher gui"
Write-Host "(or: $VenvDir\Scripts\Activate.ps1 ; missionstudio gui)"
