# start_desktop_pet.ps1 — Launch the Companion desktop pet
# Called from Start Menu shortcut or manually.
# Must be saved with UTF-8 BOM if edited manually.

$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LauncherPath = Join-Path $AppDir "companion_launcher.py"

# Prefer venv Python, fall back to system Python.
# Keep executable and arguments separate: Start-Process cannot run "py -3.12"
# when that whole string is passed as FilePath.
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$PythonArgs = @()
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = $null
    foreach ($candidate in @(
        @{ Exe = "py"; Args = @("-3.12") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )) {
        try {
            $versionArgs = @($candidate.Args) + @("--version")
            $null = & $candidate.Exe @versionArgs 2>&1
            if ($LASTEXITCODE -eq 0) {
                $PythonExe = $candidate.Exe
                $PythonArgs = @($candidate.Args)
                break
            }
        } catch { }
    }
}

if (-not $PythonExe) {
    exit 1
}

# Check if the pet manager is already running. The tray menu can open more pet instances.
$running = Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like "*companion_launcher.py*" -and $_.CommandLine -like "*--pet*" -and $_.CommandLine -like "*$AppDir*" }

if ($running) {
    exit 0
}

Start-Process -FilePath $PythonExe -ArgumentList (@($PythonArgs) + @("`"$LauncherPath`"", "--pet")) -WorkingDirectory $AppDir -WindowStyle Hidden
