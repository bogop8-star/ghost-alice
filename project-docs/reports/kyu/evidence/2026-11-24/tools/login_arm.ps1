# Open an interactive Claude Code in an isolated test home so the user can log in once.
# Usage (PowerShell, in a NEW window): & .\login_arm.ps1 -Arm a   (then: /login, finish in the browser, then /exit)
# The variable changes below apply only to this PowerShell window. Close it afterwards.
param(
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Arm,
    # Folder for test homes (default: ~/ga-test, or $env:GA_TEST_ROOT).
    [string]$Root = $(if ($env:GA_TEST_ROOT) { $env:GA_TEST_ROOT } else { Join-Path $HOME 'ga-test' })
)
$testHome = Join-Path $Root "home-$Arm"
New-Item -ItemType Directory -Force $testHome, (Join-Path $testHome '.claude') | Out-Null
Get-ChildItem Env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC|GHOST_ALICE|LANGFUSE)' } |
    ForEach-Object { Remove-Item "Env:$($_.Name)" }
$env:HOME = $testHome
$env:USERPROFILE = $testHome
$env:CLAUDE_CONFIG_DIR = Join-Path $testHome '.claude'
$env:GHOST_ALICE_GHOST_ROOT = Join-Path $testHome '.ghost-alice'
Set-Location $testHome
Write-Host "Test home: $testHome  (type /login, finish in the browser, then /exit)"
claude
