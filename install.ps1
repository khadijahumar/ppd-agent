# PPD Assistant - Windows installer
#
# One-liner install:
#   iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/main/install.ps1 | iex
#
# What it does:
#   1. Verifies Python >= 3.10 is on PATH (or via the 'py' launcher).
#   2. Ensures pipx is installed and on PATH.
#   3. Installs / upgrades the package from GitHub via pipx.
#   4. Creates %USERPROFILE%\.ppd\ skeleton and a template .env.
#   5. Prints next steps.
#
# Re-running the script is safe (idempotent).

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # speeds up Invoke-WebRequest

$RepoOwner   = 'khadijahumar'
$RepoName    = 'ppd-agent'
$RepoUrl     = "https://github.com/$RepoOwner/$RepoName.git"
$PackageName = 'ppd-agent'
$MinPyMajor  = 3
$MinPyMinor  = 10

function Write-Step($msg) { Write-Host ">> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "OK   $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "WARN $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "FAIL $msg" -ForegroundColor Red }

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  PPD Assistant - Windows installer' -ForegroundColor Cyan
Write-Host "  Source: $RepoUrl"  -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

# ---------------------------------------------------------------------------
# 1. Locate a usable Python interpreter
# ---------------------------------------------------------------------------

Write-Step 'Looking for Python >= 3.10 ...'

function Get-PyVersion($exe) {
    try {
        $raw = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
        return $raw.Trim()
    } catch {
        return $null
    }
}

function Test-PyVersion($verString) {
    if (-not $verString) { return $false }
    $parts = $verString.Split('.')
    if ($parts.Length -lt 2) { return $false }
    [int]$maj = $parts[0]; [int]$min = $parts[1]
    if ($maj -gt $MinPyMajor) { return $true }
    if ($maj -eq $MinPyMajor -and $min -ge $MinPyMinor) { return $true }
    return $false
}

$pyExe = $null
foreach ($candidate in @('py -3', 'python', 'python3')) {
    $exe = $candidate.Split(' ')[0]
    $args_extra = if ($candidate.Contains(' ')) { $candidate.Split(' ', 2)[1] } else { $null }
    $cmd = Get-Command $exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $verCmd = if ($args_extra) { "$exe $args_extra" } else { $exe }
    $ver = Get-PyVersion $verCmd
    if (Test-PyVersion $ver) {
        $pyExe = $verCmd
        Write-Ok "$verCmd  (Python $ver)"
        break
    } elseif ($ver) {
        Write-Warn2 "$verCmd  -> Python $ver  (need >= $MinPyMajor.$MinPyMinor)"
    }
}

if (-not $pyExe) {
    Write-Fail 'No suitable Python found.'
    Write-Host ''
    Write-Host 'Install Python 3.10 or newer first:'
    Write-Host '  https://www.python.org/downloads/windows/'
    Write-Host 'When the installer runs, tick "Add python.exe to PATH".'
    Write-Host 'Then re-run this installer.'
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Ensure pipx is installed and on PATH
# ---------------------------------------------------------------------------

Write-Step 'Checking pipx ...'

function Test-Pipx() {
    $cmd = Get-Command pipx -ErrorAction SilentlyContinue
    return [bool]$cmd
}

if (-not (Test-Pipx)) {
    Write-Host '  pipx not found, installing via pip ...'
    & cmd /c "$pyExe -m pip install --user --upgrade pip pipx" 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Fail 'pip install pipx failed. See output above.'
        exit 1
    }
    Write-Host '  Adding pipx to PATH (user) ...'
    & cmd /c "$pyExe -m pipx ensurepath" 2>&1 | Out-Host

    # ensurepath updates the registry, but the *current* session's PATH still
    # doesn't have it. Add the user-Scripts dir to this session's PATH.
    $userBase = & cmd /c "$pyExe -c ""import site; print(site.USER_BASE)""" 2>$null
    if ($userBase) {
        $userBase = $userBase.Trim()
        $userScripts = Join-Path $userBase 'Scripts'
        if (Test-Path $userScripts) {
            $env:PATH = "$userScripts;$env:PATH"
        }
    }
}

if (-not (Test-Pipx)) {
    Write-Fail 'pipx still not found after install.'
    Write-Host ''
    Write-Host 'Open a NEW PowerShell window (so PATH is reloaded) and re-run:'
    Write-Host '  iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/main/install.ps1 | iex'
    exit 1
}

Write-Ok 'pipx available'

# ---------------------------------------------------------------------------
# 3. Install (or upgrade) the ppd-agent package
# ---------------------------------------------------------------------------

Write-Step "Installing $PackageName from GitHub ..."

# Use 'install --force' so re-running upgrades cleanly.
& pipx install --force "git+$RepoUrl" 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pipx install failed."
    exit 1
}
Write-Ok "$PackageName installed"

# ---------------------------------------------------------------------------
# 4. Create $env:USERPROFILE\.ppd skeleton + template .env
# ---------------------------------------------------------------------------

Write-Step 'Creating PPD home directory ...'

$ppdHome = Join-Path $env:USERPROFILE '.ppd'
$rawDir     = Join-Path $ppdHome 'data\raw'
$parquetDir = Join-Path $ppdHome 'data\parquet'
$plotsDir   = Join-Path $ppdHome 'data\plots'

New-Item -ItemType Directory -Force -Path $ppdHome     | Out-Null
New-Item -ItemType Directory -Force -Path $rawDir      | Out-Null
New-Item -ItemType Directory -Force -Path $parquetDir  | Out-Null
New-Item -ItemType Directory -Force -Path $plotsDir    | Out-Null

Write-Ok "PPD home: $ppdHome"

# Trigger the package's own template-write if .env is missing.
& ppd init --non-interactive 2>&1 | Out-Host

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  Installation complete!' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Next steps:'
Write-Host ''
Write-Host '  1. Run the wizard to enter your credentials:' -ForegroundColor White
Write-Host '       ppd init' -ForegroundColor Yellow
Write-Host ''
Write-Host '  2. Drop the 8 .xlsx files into:' -ForegroundColor White
Write-Host "       $rawDir" -ForegroundColor Yellow
Write-Host ''
Write-Host '       Required filenames:'
Write-Host '         FT_CT_Design.xlsx'
Write-Host '         HR_Chem_Std.xlsx'
Write-Host '         HR_Elongation_Std.xlsx'
Write-Host '         HR_Mech_Std.xlsx'
Write-Host '         HR_Thick_Toler.xlsx'
Write-Host '         Z001.xlsx'
Write-Host '         Chemical_Design.xls'
Write-Host '         Produksi_2021_HRC.xlsx'
Write-Host ''
Write-Host '  3. Convert raw Excel -> parquet (run once):' -ForegroundColor White
Write-Host '       ppd prepare-data' -ForegroundColor Yellow
Write-Host ''
Write-Host '  4. Start the bot (foreground; Ctrl+C to stop):' -ForegroundColor White
Write-Host '       ppd start' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Anytime, run "ppd doctor" to diagnose your install.'
Write-Host ''
