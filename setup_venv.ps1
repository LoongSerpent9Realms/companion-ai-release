# setup_venv.ps1 — Create Python virtual environment for Companion AI
# Called by NSIS installer (post-install, hidden window)
# Must be saved with UTF-8 BOM if edited manually.

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $AppDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# ---- locate Python ----
$PythonCmd = $null
foreach ($cmd in @("py -3.12", "py -3", "python")) {
    try {
        $parts = $cmd -split " "
        $testArgs = if ($parts.Count -gt 1) { $parts[1..($parts.Count-1)] + @("--version") } else { @("--version") }
        $null = & $parts[0] $testArgs 2>&1
        if ($LASTEXITCODE -eq 0) { $PythonCmd = $cmd; break }
    } catch { }
}

if (-not $PythonCmd) {
    Write-Error "Python 3.12+ not found. Cannot create virtual environment."
    exit 1
}

# ---- create venv if missing ----
if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host "Creating virtual environment at $VenvDir ..."
    $parts = $PythonCmd -split " "
    $venvArgs = if ($parts.Count -gt 1) { $parts[1..($parts.Count-1)] + @("-m", "venv", "`"$VenvDir`"") } else { @("-m", "venv", "`"$VenvDir`"") }
    & $parts[0] $venvArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment (exit code $LASTEXITCODE)."
        exit 1
    }
}

# ---- upgrade pip quietly ----
Write-Host "Upgrading pip ..."
& "$PythonExe" -m pip install --upgrade pip --quiet 2>&1 | Out-Null

# ---- write requirements marker ----
$reqFile = Join-Path $AppDir "requirements.txt"
if (-not (Test-Path -LiteralPath $reqFile)) {
    @"
# Companion AI — base requirements
# All heavy deps (torch, rapidocr) are optional and installed via Settings UI.
# This file is intentionally minimal.
"@ | Set-Content -LiteralPath $reqFile -Encoding UTF8
}

Write-Host "Virtual environment ready."
exit 0
