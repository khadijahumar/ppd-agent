# PPD Assistant - Windows installer
#
# One-liner install (works regardless of which branch is the GitHub default):
#   iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/HEAD/install.ps1 | iex
#
# What it does:
#   1. Verifies Python >= 3.10 is on PATH (or via the 'py' launcher).
#   2. Ensures pipx is installed and on PATH.
#   3. Installs / upgrades the package from GitHub via pipx.
#   4. Creates %USERPROFILE%\.ppd\ skeleton and a template .env.
#   5. Prints next steps.
#
# Re-running the script is safe (idempotent).

# NOTE: We deliberately DO NOT use $ErrorActionPreference = 'Stop' globally,
# because piping stderr from native processes (like pip's "not on PATH"
# warnings) trips PowerShell's strict mode and aborts the script even on
# benign warnings. We check $LASTEXITCODE manually instead.
$ErrorActionPreference = 'Continue'
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
# Helpers
# ---------------------------------------------------------------------------

# Run a Python command (e.g. "-m pip install ..."). $PyCmd is split into the
# executable + args so we can call it as a native PowerShell command (no cmd /c).
# Streams stdout/stderr live to the host. The exit code is left in the
# caller's $LASTEXITCODE; we deliberately DO NOT use `return` here because
# PowerShell would mix the return value with any captured stdout.
function Invoke-PyExe {
    param(
        [Parameter(Mandatory)] [string[]] $PyCmd,
        [Parameter(Mandatory)] [string[]] $ExtraArgs
    )
    $exe = $PyCmd[0]
    $base_args = @()
    if ($PyCmd.Length -gt 1) { $base_args = $PyCmd[1..($PyCmd.Length - 1)] }
    $all_args = $base_args + $ExtraArgs
    & $exe @all_args
}

# Get a Python interpreter's "M.m" version string, or $null on failure.
function Get-PyVersion {
    param([Parameter(Mandatory)] [string[]] $PyCmd)
    $exe = $PyCmd[0]
    $base_args = @()
    if ($PyCmd.Length -gt 1) { $base_args = $PyCmd[1..($PyCmd.Length - 1)] }
    $all_args = $base_args + @('-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    try {
        $raw = & $exe @all_args 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
        return ($raw | Out-String).Trim()
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

# ---------------------------------------------------------------------------
# 1. Locate a usable Python interpreter
# ---------------------------------------------------------------------------

Write-Step 'Looking for Python >= 3.10 ...'

$candidates = @(
    @('py',      '-3'),
    @('python'),
    @('python3')
)

$pyCmd = $null
foreach ($cand in $candidates) {
    $exe = $cand[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $ver = Get-PyVersion $cand
    $human = ($cand -join ' ')
    if (Test-PyVersion $ver) {
        $pyCmd = $cand
        Write-Ok "$human  (Python $ver)"
        break
    } elseif ($ver) {
        Write-Warn2 "$human  -> Python $ver  (need >= $MinPyMajor.$MinPyMinor)"
    }
}

if (-not $pyCmd) {
    Write-Fail 'No suitable Python found.'
    Write-Host ''
    Write-Host 'Install Python 3.10 or newer first:'
    Write-Host '  https://www.python.org/downloads/windows/'
    Write-Host 'When the installer runs, tick "Add python.exe to PATH".'
    Write-Host 'Then re-run this installer.'
    exit 1
}

# Find the user's "Scripts" dir for this Python (where pip --user installs
# console_scripts go). We do this NOW so we can prepend it to PATH for the
# rest of this session, even before pipx exists. Use sysconfig with the
# 'nt_user' scheme — this returns the correct version-specific Scripts dir
# (e.g. "%APPDATA%\Python\Python314\Scripts"), unlike site.USER_BASE which
# only gives the parent.
$scriptsArgs = @()
if ($pyCmd.Length -gt 1) { $scriptsArgs = $pyCmd[1..($pyCmd.Length - 1)] }
$scriptsArgs += @('-c', "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))")
$userScripts = (& $pyCmd[0] @scriptsArgs) 2>$null
if ($userScripts) {
    $userScripts = ($userScripts | Out-String).Trim()
    if ((Test-Path $userScripts) -and (-not ($env:PATH -like "*$userScripts*"))) {
        $env:PATH = "$userScripts;$env:PATH"
        Write-Host "  Added to session PATH: $userScripts"
    }
}

# ---------------------------------------------------------------------------
# 2. Ensure pipx is installed and on PATH
# ---------------------------------------------------------------------------

Write-Step 'Checking pipx ...'

function Test-Pipx() {
    return [bool] (Get-Command pipx -ErrorAction SilentlyContinue)
}

if (-not (Test-Pipx)) {
    Write-Host '  pipx not found, installing via pip ...'
    Invoke-PyExe -PyCmd $pyCmd -ExtraArgs @('-m', 'pip', 'install', '--user', '--upgrade', 'pip', 'pipx')
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install pipx failed (exit $LASTEXITCODE)."
        exit 1
    }

    Write-Host '  Adding pipx to PATH (user, persistent) ...'
    Invoke-PyExe -PyCmd $pyCmd -ExtraArgs @('-m', 'pipx', 'ensurepath')
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 "pipx ensurepath returned exit $LASTEXITCODE (continuing)."
    }
}

if (-not (Test-Pipx)) {
    # Even after PATH manipulation, pipx still not visible. Fall back to
    # invoking it via Python: every subsequent "pipx ..." goes through pyCmd.
    Write-Warn2 'pipx not on PATH yet in this session; using python -m pipx instead.'
    $pipxRunner = $pyCmd + @('-m', 'pipx')
} else {
    Write-Ok 'pipx available'
    $pipxRunner = @('pipx')
}

# ---------------------------------------------------------------------------
# 3. Install (or upgrade) the ppd-agent package
# ---------------------------------------------------------------------------

Write-Step "Installing $PackageName from GitHub ..."

# Use 'install --force' so re-running upgrades cleanly.
$exe = $pipxRunner[0]
$tail = @()
if ($pipxRunner.Length -gt 1) { $tail = $pipxRunner[1..($pipxRunner.Length - 1)] }
$pipxArgs = $tail + @('install', '--force', "git+$RepoUrl")
& $exe @pipxArgs
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pipx install failed (exit $LASTEXITCODE)."
    exit 1
}
Write-Ok "$PackageName installed"

# Resolve the user's home directory. $env:USERPROFILE is the right answer
# on Windows; PowerShell also exposes $HOME on every platform — fall back
# to that so the script behaves sensibly when run under pwsh on Linux/Mac.
$homeBase = $env:USERPROFILE
if (-not $homeBase) { $homeBase = $HOME }
if (-not $homeBase) {
    Write-Fail 'Could not resolve user home directory ($env:USERPROFILE / $HOME both empty).'
    exit 1
}

# Make sure the new pipx-managed bin dir is in *this* session's PATH so
# `ppd` resolves immediately (without opening a new PowerShell window).
$pipxBin = Join-Path $homeBase '.local\bin'
if ((Test-Path $pipxBin) -and (-not ($env:PATH -like "*$pipxBin*"))) {
    $env:PATH = "$pipxBin;$env:PATH"
    Write-Host "  Added to session PATH: $pipxBin"
}

# ---------------------------------------------------------------------------
# 4. Create %USERPROFILE%\.ppd skeleton + template .env
# ---------------------------------------------------------------------------

Write-Step 'Creating PPD home directory ...'

$ppdHome = Join-Path $homeBase '.ppd'
$rawDir     = Join-Path $ppdHome 'data\raw'
$parquetDir = Join-Path $ppdHome 'data\parquet'
$plotsDir   = Join-Path $ppdHome 'data\plots'

New-Item -ItemType Directory -Force -Path $ppdHome     | Out-Null
New-Item -ItemType Directory -Force -Path $rawDir      | Out-Null
New-Item -ItemType Directory -Force -Path $parquetDir  | Out-Null
New-Item -ItemType Directory -Force -Path $plotsDir    | Out-Null

Write-Ok "PPD home: $ppdHome"

# Trigger the package's own template-write if .env is missing. We swallow
# any non-fatal output here.
if (Get-Command ppd -ErrorAction SilentlyContinue) {
    & ppd init --non-interactive
} else {
    Write-Warn2 "'ppd' not on PATH yet; open a new PowerShell window and run 'ppd init'."
}

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  Installation complete!' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'IMPORTANT: open a NEW PowerShell window now so the updated PATH'
Write-Host '           is fully picked up before running any "ppd" command.'
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
