# Run the Autopilot test suite on Windows with the same command as POSIX CI.
#
# Usage (PowerShell, from any folder):
#   .\scripts\run_windows_tests.ps1                      # whole suite
#   .\scripts\run_windows_tests.ps1 tests\test_claim_evidence.py -q
#
# Environment:
#   GHOST_ALICE_CORE_ROOT  Ghost-ALICE Core checkout. Default: $HOME\ghost-alice
#   PYTHON                 Python 3.11+ executable with pytest installed.
#                          Default: python on PATH. The script stops with a
#                          message when Python or pytest is missing; it does
#                          not install packages.
#
# Windows-only differences handled here or in tests\conftest.py:
#   - PYTHONUTF8=1 so file reads use UTF-8 instead of the cp949/ANSI code page.
#   - tests\conftest.py supplies home-directory and symlink fallbacks.
#   - .gitattributes keeps LF bytes so fixture digests match CI.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

if (-not $env:GHOST_ALICE_CORE_ROOT) { $env:GHOST_ALICE_CORE_ROOT = Join-Path $HOME 'ghost-alice' }
if (-not (Test-Path (Join-Path $env:GHOST_ALICE_CORE_ROOT 'skill-catalog'))) {
    throw "Ghost-ALICE Core checkout not found: $env:GHOST_ALICE_CORE_ROOT (set GHOST_ALICE_CORE_ROOT)"
}
$env:GHOST_ALICE_CORE_REPO = $env:GHOST_ALICE_CORE_ROOT
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Autopilot emits POSIX-style recovery commands (`env KEY=VALUE python ...`).
# Claude Code runs them through Git Bash on Windows, so expose Git's POSIX
# tools (env.exe) to the tests the same way.
if (-not (Get-Command env -CommandType Application -ErrorAction SilentlyContinue)) {
    # git.exe can appear more than once on PATH (Git\cmd, Git\mingw64\bin).
    $gitUsrBin = Get-Command git -CommandType Application -All -ErrorAction SilentlyContinue |
        ForEach-Object {
            $dir = Split-Path $_.Source
            while ($dir -and -not (Test-Path (Join-Path $dir 'usr\bin\env.exe'))) { $dir = Split-Path $dir }
            if ($dir) { Join-Path $dir 'usr\bin' }
        } | Select-Object -First 1
    if ($gitUsrBin) {
        $env:PATH = "$gitUsrBin;$env:PATH"
    } else {
        Write-Warning 'env.exe not found. Install Git for Windows; recovery-command tests will fail.'
    }
}

$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$pytestArgs = if ($args.Count -gt 0) { $args } else { @('tests', '-q') }

# Probe Python and pytest in one child that never writes to stderr. Under
# Windows PowerShell 5, $ErrorActionPreference='Stop' turns any native stderr
# line into a terminating error, so `python -m pytest --version` on a Python
# without pytest stopped the script before it could report what was missing.
# The code uses only single quotes: Windows PowerShell 5 drops embedded double
# quotes when it passes an argument to a native program.
$probe = 'import importlib.util, sys; print(''%d.%d %s'' % (sys.version_info[0], sys.version_info[1], ''yes'' if importlib.util.find_spec(''pytest'') else ''no''))'
try {
    $probeResult = & $python -c $probe
} catch {
    throw "Python not found: $python (set PYTHON to a Python 3.11+ executable)"
}
if ($LASTEXITCODE -ne 0 -or -not $probeResult) {
    throw "Python probe failed: $python (set PYTHON to a Python 3.11+ executable)"
}
$version, $hasPytest = "$probeResult".Trim().Split(' ')
if ([version]$version -lt [version]'3.11') {
    throw "Python $version is too old: $python (set PYTHON to a Python 3.11+ executable)"
}
if ($hasPytest -ne 'yes') {
    throw "pytest is not installed for $python. Install it with '$python -m pip install pytest' or set PYTHON to a Python that has pytest."
}

Push-Location $repo
try {
    & $python scripts\run_project_tests.py @pytestArgs -p no:cacheprovider
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
