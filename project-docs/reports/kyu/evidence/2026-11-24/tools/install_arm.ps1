# Install Ghost-ALICE (Core + Autopilot) into an isolated test home.
# Usage: pwsh -NoProfile -File install_arm.ps1 -Arm a -Core <core folder> -Addon <Autopilot repository root> [-Root <test root>] [-PythonDir <python folder>]
# Every path the installer uses comes from HOME / USERPROFILE / CLAUDE_CONFIG_DIR /
# GHOST_ALICE_GHOST_ROOT, which this script points at C:\Users\N-\ga-test\home-<arm>.
param(
    [Parameter(Mandatory)][string]$Arm,
    [Parameter(Mandatory)][string]$Core,
    [Parameter(Mandatory)][string]$Addon,
    # Folder for test homes (default: ~/ga-test, or $env:GA_TEST_ROOT).
    [string]$Root = $(if ($env:GA_TEST_ROOT) { $env:GA_TEST_ROOT } else { Join-Path $HOME 'ga-test' }),
    # Folder of the Python the hooks should use (default: the python found on PATH).
    [string]$PythonDir = $(Split-Path -Parent (Get-Command python -ErrorAction Stop).Source)
)
$ErrorActionPreference = 'Stop'
$root = $Root
$testHome = Join-Path $root "home-$Arm"
New-Item -ItemType Directory -Force $testHome, (Join-Path $testHome '.claude') | Out-Null

# Drop variables inherited from the desktop session that runs this script.
Get-ChildItem Env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC|GHOST_ALICE|LANGFUSE)' } |
    ForEach-Object { Remove-Item "Env:$($_.Name)" }
$env:HOME = $testHome
$env:USERPROFILE = $testHome
$env:CLAUDE_CONFIG_DIR = Join-Path $testHome '.claude'
$env:GHOST_ALICE_GHOST_ROOT = Join-Path $testHome '.ghost-alice'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
# The installer finds Python on PATH; put the hook Python first.
$env:PATH = "$PythonDir;$(Join-Path $PythonDir 'Scripts');" + $env:PATH

"arm=$Arm home=$testHome core=$Core addon=$Addon"
& (Join-Path $Core 'install.ps1') -Platform claude -AddonSource $Addon
"exit=$LASTEXITCODE"
