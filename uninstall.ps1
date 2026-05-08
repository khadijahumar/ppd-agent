#requires -Version 5.1
<#
.SYNOPSIS
    PPD Assistant - one-line uninstaller for Windows.

.DESCRIPTION
    Removes the pipx-installed `ppd-agent` package and (by default) the
    user's `%USERPROFILE%\.ppd` data folder.

    Usage (one-liner):

        iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/HEAD/uninstall.ps1 | iex

    Use this when `ppd uninstall` (the in-package command) is broken or the
    package is already gone but you want to clean up the data folder.

    Safe to run twice: missing pipx package and missing folder are tolerated.
#>

# Pure ASCII output - identical render in PowerShell 5.1 and PowerShell 7.

$ErrorActionPreference = 'Continue'  # be tolerant; this is a cleanup script
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Banner {
    Write-Host ''
    $left = @(
        '   _____  _____  _____  ',
        '  |  __ \|  __ \|  __ \ ',
        '  | |__) | |__) | |  | |',
        '  |  ___/|  ___/| |  | |',
        '  | |    | |    | |__| |',
        '  |_|    |_|    |_____/ '
    )
    $right = @(
        '              _____ ______ _   _ _______ ',
        '        /\   / ____|  ____| \ | |__   __|',
        '______ /  \ | |  __| |__  |  \| |  | |   ',
        '______/ /\ \| | |_ |  __| | . ` |  | |   ',
        '     / ____ \ |__| | |____| |\  |  | |   ',
        '    /_/    \_\_____|______|_| \_|  |_|   '
    )
    for ($i = 0; $i -lt $left.Length; $i++) {
        Write-Host ($left[$i] + $right[$i]) -ForegroundColor Yellow
    }
    Write-Host ''
    Write-Host '  Uninstaller   |   removes ppd-agent + data folder' -ForegroundColor DarkGray
    Write-Host ''
}

function Write-Step ($m) { Write-Host ">> $m"   -ForegroundColor Cyan }
function Write-Ok   ($m) { Write-Host "[+] $m"  -ForegroundColor Green }
function Write-Warn ($m) { Write-Host "[!] $m"  -ForegroundColor Yellow }
function Write-Fail ($m) { Write-Host "[x] $m"  -ForegroundColor Red }

Write-Banner

$home_dir = Join-Path $env:USERPROFILE '.ppd'

Write-Host "  This will:"
Write-Host "    - Run 'pipx uninstall ppd-agent'"
Write-Host "    - DELETE the data folder, including .env and parquet:"
Write-Host "        $home_dir"
Write-Host ''
$confirm = Read-Host "  Type 'yes' to proceed"
if ($confirm.Trim().ToLower() -ne 'yes') {
    Write-Warn 'Cancelled. Nothing changed.'
    return
}

# 1. Try pipx uninstall (preferred path).
Write-Step 'Removing pipx package ppd-agent ...'
$pipxCmd = Get-Command pipx -ErrorAction SilentlyContinue
if ($pipxCmd) {
    & pipx uninstall ppd-agent
    if ($LASTEXITCODE -eq 0) {
        Write-Ok 'pipx package removed'
    } else {
        Write-Warn "pipx uninstall returned code $LASTEXITCODE (package may already be missing)"
    }
} else {
    # Fallback: try `python -m pipx`.
    $pyCmd = $null
    foreach ($exe in @('py', 'python', 'python3')) {
        $resolved = Get-Command $exe -ErrorAction SilentlyContinue
        if ($resolved) { $pyCmd = $exe; break }
    }
    if ($pyCmd) {
        if ($pyCmd -eq 'py') {
            & py -3 -m pipx uninstall ppd-agent
        } else {
            & $pyCmd -m pipx uninstall ppd-agent
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Ok 'pipx package removed (via python -m pipx)'
        } else {
            Write-Warn "python -m pipx returned code $LASTEXITCODE (package may already be missing)"
        }
    } else {
        Write-Warn 'pipx not found and no python on PATH; skipping package uninstall.'
    }
}

# 2. Remove the data folder.
Write-Step "Removing data folder $home_dir ..."
if (Test-Path -LiteralPath $home_dir) {
    try {
        Remove-Item -LiteralPath $home_dir -Recurse -Force -ErrorAction Stop
        Write-Ok "Removed $home_dir"
    } catch {
        Write-Fail "Could not remove $home_dir : $($_.Exception.Message)"
        Write-Host '    Delete it manually if you want a clean slate.'
    }
} else {
    Write-Ok "$home_dir does not exist (nothing to remove)"
}

Write-Host ''
Write-Host '  +---------------------------------------------------------------+' -ForegroundColor Yellow
Write-Host '  |  PPD Agent fully uninstalled.                                  |' -ForegroundColor Yellow
Write-Host '  |                                                                |' -ForegroundColor Yellow
Write-Host '  |  Re-install any time with:                                     |' -ForegroundColor Yellow
Write-Host '  |    iwr -useb https://raw.githubusercontent.com/khadijahumar/   |' -ForegroundColor Yellow
Write-Host '  |        ppd-agent/HEAD/install.ps1 | iex                        |' -ForegroundColor Yellow
Write-Host '  +---------------------------------------------------------------+' -ForegroundColor Yellow
Write-Host ''
