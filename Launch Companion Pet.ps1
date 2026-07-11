$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LauncherPath = Join-Path $AppDir "companion_launcher.py"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = "python" }

$running = Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like "*companion_launcher.py*" -and $_.CommandLine -like "*--pet*" -and $_.CommandLine -like "*$AppDir*" }

if (-not $running) {
    Start-Process -FilePath $PythonExe -ArgumentList @($LauncherPath, "--pet") -WorkingDirectory $AppDir -WindowStyle Hidden
}
