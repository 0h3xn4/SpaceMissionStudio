<#
.SYNOPSIS
    Builds missionstudio's own wheel + sdist -- the Basilisk-independent
    part of packaging. Windows/PowerShell counterpart of build_wheel.sh;
    see that script's own header comment for the two real bugs already
    found and fixed on the Linux side, both of which apply here unchanged
    since they're about setuptools/`python -m build`, not the shell:

      1. missionstudio/scenarios/*.json (data with no __init__.py) needs
         pyproject.toml's [tool.setuptools.package-data] entry, or it's
         silently missing from the built wheel.
      2. `python -m build`'s own temp ./build/ output directory (gitignored)
         shadows the installed `build` package on the next Python process
         if left behind (`python` inserts the current directory at the
         front of sys.path for both `-c` and `-m`) -- this script cleans
         it first, same as build_wheel.sh.

    NOT independently run against a real Windows machine in this project's
    development sandbox (Linux-only, no Windows environment available
    here) -- written against documented, standard `python -m build`/pip
    behavior and this same logic already verified on the Linux side, but
    flagged here rather than claimed as verified. Please report any
    issues building on a real Windows 11 machine.

.PARAMETER DistDir
    Output directory for the built wheel + sdist. Default: <project root>\dist
#>

param(
    [string]$DistDir = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
if (-not $DistDir) {
    $DistDir = Join-Path $ProjectDir "dist"
}

Set-Location $ProjectDir

$BuildDir = Join-Path $ProjectDir "build"
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}

$null = python -m pip show build 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing the PEP 517 'build' frontend (python -m pip install build)..."
    python -m pip install --quiet build
    if ($LASTEXITCODE -ne 0) {
        throw "pip install build failed (exit code $LASTEXITCODE)"
    }
}

Write-Host "Building missionstudio wheel + sdist into $DistDir ..."
python -m build --wheel --sdist --outdir $DistDir
if ($LASTEXITCODE -ne 0) {
    throw "python -m build failed (exit code $LASTEXITCODE)"
}

Write-Host ""
Write-Host "Built:"
Get-ChildItem (Join-Path $DistDir "missionstudio-*") | ForEach-Object { Write-Host $_.Name }
