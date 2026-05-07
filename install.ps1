# PPD Assistant - Windows installer
#
# One-liner install (works regardless of which branch is the GitHub default):
#   iwr -useb https://raw.githubusercontent.com/khadijahumar/ppd-agent/HEAD/install.ps1 | iex
#
# Re-running the script is safe (idempotent).

# We deliberately DO NOT use $ErrorActionPreference = 'Stop' globally,
# because piping stderr from native processes (like pip's "not on PATH"
# warnings) trips PowerShell's strict mode and aborts the script even on
# benign warnings. We check $LASTEXITCODE manually instead.
$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

# Force UTF-8 output so the box-drawing characters in the banner render
# properly even on Windows PowerShell 5.1 hosts that default to the OEM
# code page.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$RepoOwner   = 'khadijahumar'
$RepoName    = 'ppd-agent'
$RepoUrl     = "https://github.com/$RepoOwner/$RepoName.git"
$PackageName = 'ppd-agent'
$AppVersion  = '0.1.0'
$Tagline     = 'Production · Planning · Design'
$MinPyMajor  = 3
$MinPyMinor  = 10

# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

function Write-Banner {
    Write-Host ''
    # ANSI Shadow font for "PPD-AGENT" — yellow, with the right half
    # ("AGENT") rendered in a darker accent so the eye lands on "PPD".
    $left = @(
        '  ██████╗ ██████╗ ██████╗ ',
        '  ██╔══██╗██╔══██╗██╔══██╗',
        '  ██████╔╝██████╔╝██║  ██║',
        '  ██╔═══╝ ██╔═══╝ ██║  ██║',
        '  ██║     ██║     ██████╔╝',
        '  ╚═╝     ╚═╝     ╚═════╝ '
    )
    $right = @(
        '       █████╗  ██████╗ ███████╗███╗   ██╗████████╗',
        '      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝',
        '█████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ',
        '╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ',
        '      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ',
        '      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   '
    )
    for ($i = 0; $i -lt $left.Length; $i++) {
        Write-Host $left[$i]  -ForegroundColor Yellow      -NoNewline
        Write-Host $right[$i] -ForegroundColor DarkYellow
    }
    Write-Host ''
    Write-Host "  $Tagline   ·   v$AppVersion" -ForegroundColor DarkGray
    Write-Host ''
}

function Write-Step($msg) { Write-Host "  ▶ $msg"      -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  ✓ $msg"      -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  ⚠ $msg"      -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  ✗ $msg"      -ForegroundColor Red }
function Write-Info($msg) { Write-Host "    $msg"      -ForegroundColor DarkGray }

function Write-Rule {
    Write-Host ('  ' + ('─' * 64))                     -ForegroundColor DarkGray
}

# Render a yellow-bordered "card" / framed box with body lines (one entry =
# one rendered line). Width = 64 inner cols. ANSI color codes inside body
# strings are NOT counted by .Length, so we compute padding from the
# *visible* length passed alongside.
function Write-Card {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]] $Lines
    )
    $innerWidth = 64
    $top    = '  ╔' + ('═' * $innerWidth) + '╗'
    $bottom = '  ╚' + ('═' * $innerWidth) + '╝'
    Write-Host $top    -ForegroundColor Yellow
    foreach ($line in $Lines) {
        # Pad-right to inner width, accounting for visual length only.
        $visible = $line
        $pad = $innerWidth - $visible.Length
        if ($pad -lt 0) { $pad = 0 }
        Write-Host '  ║' -ForegroundColor Yellow -NoNewline
        Write-Host ($visible + (' ' * $pad)) -NoNewline
        Write-Host '║'   -ForegroundColor Yellow
    }
    Write-Host $bottom -ForegroundColor Yellow
}

Write-Banner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Run a Python command (e.g. "-m pip install ..."). Streams stdout/stderr
# live to the host. Caller checks $LASTEXITCODE.
function Invoke-Py {
    param(
        [Parameter(Mandatory)] [string]   $Exe,
        [AllowEmptyCollection()] [string[]] $Pre = @(),
        [Parameter(Mandatory)] [string[]] $ExtraArgs
    )
    $allArgs = @() + $Pre + $ExtraArgs
    & $Exe @allArgs
}

# Try one specific Python interpreter. Returns a PSObject {exe, pre, version}
# if it works AND meets the minimum version, else $null.
function Try-Py {
    param(
        [Parameter(Mandatory)] [string]   $Exe,
        [AllowEmptyCollection()] [string[]] $Pre = @()
    )
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) { return $null }
    $verArgs = @() + $Pre + @('-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    $raw = $null
    try { $raw = & $Exe @verArgs 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    $ver = ($raw | Out-String).Trim()
    if (-not $ver) { return $null }
    $parts = $ver.Split('.')
    if ($parts.Length -lt 2) { return $null }
    [int]$maj = $parts[0]; [int]$min = $parts[1]
    $ok = ($maj -gt $MinPyMajor) -or ($maj -eq $MinPyMajor -and $min -ge $MinPyMinor)
    if (-not $ok) {
        if ($Pre.Length -gt 0) { $human = "$Exe $($Pre -join ' ')" } else { $human = $Exe }
        Write-Warn2 "${human}: Python $ver  (need >= $MinPyMajor.$MinPyMinor)"
        return $null
    }
    return [pscustomobject]@{ exe = $Exe; pre = $Pre; version = $ver }
}

# ---------------------------------------------------------------------------
# 1. Locate a usable Python interpreter
# ---------------------------------------------------------------------------

Write-Step 'Looking for Python >= 3.10'

$pyCmd = $null
$pyCmd = Try-Py -Exe 'py'      -Pre @('-3')
if (-not $pyCmd) { $pyCmd = Try-Py -Exe 'python'  -Pre @() }
if (-not $pyCmd) { $pyCmd = Try-Py -Exe 'python3' -Pre @() }

if (-not $pyCmd) {
    Write-Fail 'No suitable Python found.'
    Write-Host ''
    Write-Host '    Install Python 3.10 or newer first:' -ForegroundColor White
    Write-Host '      https://www.python.org/downloads/windows/' -ForegroundColor Yellow
    Write-Host '    When the installer runs, tick "Add python.exe to PATH".' -ForegroundColor White
    Write-Host '    Then re-run this installer.' -ForegroundColor White
    Write-Host ''
    exit 1
}

if ($pyCmd.pre.Length -gt 0) { $pyHuman = "$($pyCmd.exe) $($pyCmd.pre -join ' ')" } else { $pyHuman = $pyCmd.exe }
Write-Ok "$pyHuman  (Python $($pyCmd.version))"

# Find the user's "Scripts" dir for this Python (where pip --user installs
# console_scripts go) so we can prepend it to PATH for the rest of this
# session. sysconfig's 'nt_user' scheme returns the correct version-specific
# path (e.g. "%APPDATA%\Python\Python314\Scripts") on Windows.
$scriptsArgs = @() + $pyCmd.pre + @('-c', "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))")
$userScripts = $null
try { $userScripts = & $pyCmd.exe @scriptsArgs 2>$null } catch {}
if ($userScripts) {
    $userScripts = ($userScripts | Out-String).Trim()
    if ((Test-Path $userScripts) -and (-not ($env:PATH -like "*$userScripts*"))) {
        $env:PATH = "$userScripts;$env:PATH"
        Write-Info "added to session PATH: $userScripts"
    }
}

# ---------------------------------------------------------------------------
# 2. Ensure pipx is installed and on PATH
# ---------------------------------------------------------------------------

Write-Step 'Checking pipx'

function Test-Pipx() {
    return [bool] (Get-Command pipx -ErrorAction SilentlyContinue)
}

if (-not (Test-Pipx)) {
    Write-Info 'pipx not found, installing via pip ...'
    Invoke-Py -Exe $pyCmd.exe -Pre $pyCmd.pre -ExtraArgs @('-m', 'pip', 'install', '--user', '--upgrade', 'pip', 'pipx')
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install pipx failed (exit $LASTEXITCODE)."
        exit 1
    }

    Write-Info 'adding pipx to PATH (user, persistent) ...'
    Invoke-Py -Exe $pyCmd.exe -Pre $pyCmd.pre -ExtraArgs @('-m', 'pipx', 'ensurepath')
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 "pipx ensurepath returned exit $LASTEXITCODE (continuing)."
    }
}

if (Test-Pipx) {
    Write-Ok 'pipx ready'
    $pipxExe = 'pipx'
    $pipxPre = @()
} else {
    # Even after PATH manipulation, pipx still not visible. Fall back to
    # invoking it via Python.
    Write-Warn2 'pipx still off-PATH in this session; using "python -m pipx" instead'
    $pipxExe = $pyCmd.exe
    $pipxPre = @() + $pyCmd.pre + @('-m', 'pipx')
}

# ---------------------------------------------------------------------------
# 3. Install (or upgrade) the ppd-agent package
# ---------------------------------------------------------------------------

Write-Step "Installing $PackageName from GitHub"

$pipxArgs = @() + $pipxPre + @('install', '--force', "git+$RepoUrl")
& $pipxExe @pipxArgs
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pipx install failed (exit $LASTEXITCODE)."
    exit 1
}
Write-Ok "$PackageName installed"

# Resolve the user's home directory. $env:USERPROFILE is the right answer
# on Windows; PowerShell also exposes $HOME on every platform.
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
    Write-Info "added to session PATH: $pipxBin"
}

# ---------------------------------------------------------------------------
# 4. Create %USERPROFILE%\.ppd skeleton + template .env
# ---------------------------------------------------------------------------

Write-Step 'Creating PPD home directory'

$ppdHome    = Join-Path $homeBase '.ppd'
$rawDir     = Join-Path $ppdHome 'data\raw'
$parquetDir = Join-Path $ppdHome 'data\parquet'
$plotsDir   = Join-Path $ppdHome 'data\plots'

New-Item -ItemType Directory -Force -Path $ppdHome     | Out-Null
New-Item -ItemType Directory -Force -Path $rawDir      | Out-Null
New-Item -ItemType Directory -Force -Path $parquetDir  | Out-Null
New-Item -ItemType Directory -Force -Path $plotsDir    | Out-Null

Write-Ok "PPD home: $ppdHome"

# Trigger the package's own template-write if .env is missing.
if (Get-Command ppd -ErrorAction SilentlyContinue) {
    & ppd init --non-interactive | Out-Null
} else {
    Write-Warn2 "'ppd' not on PATH yet; open a new PowerShell window and run 'ppd init'."
}

# ---------------------------------------------------------------------------
# 5. Done — render summary card + next-steps
# ---------------------------------------------------------------------------

Write-Host ''
Write-Card -Lines @(
    "  PPD Agent v$AppVersion  ·  $Tagline",
    '',
    "  PPD HOME    $ppdHome",
    "  CONFIG      $(Join-Path $ppdHome '.env')",
    "  DATA RAW    $rawDir",
    "  PARQUET     $parquetDir",
    "  PLOTS       $plotsDir",
    '',
    '  5 modules  ·  20 tools  ·  ppd --help for commands'
)
Write-Host ''
Write-Host '  Installation complete.' -ForegroundColor Green
Write-Host '  Open a NEW PowerShell window so the PATH refreshes,' -ForegroundColor White
Write-Host '  then run these commands in order:' -ForegroundColor White
Write-Host ''
Write-Host '    1. ppd init' -ForegroundColor Yellow -NoNewline
Write-Host '            wizard: OpenRouter / Telegram / user IDs' -ForegroundColor DarkGray
Write-Host '    2. drop the 8 .xlsx files into the DATA RAW folder above' -ForegroundColor White
Write-Host '    3. ppd prepare-data' -ForegroundColor Yellow -NoNewline
Write-Host '    convert Excel -> parquet (one-time, ~2 min)' -ForegroundColor DarkGray
Write-Host '    4. ppd start' -ForegroundColor Yellow -NoNewline
Write-Host '           launches the bot (Ctrl+C to stop)' -ForegroundColor DarkGray
Write-Host ''
Write-Host '  Tip: ' -ForegroundColor DarkGray -NoNewline
Write-Host 'ppd doctor' -ForegroundColor Yellow -NoNewline
Write-Host ' diagnoses your install at any time.' -ForegroundColor DarkGray
Write-Host ''
