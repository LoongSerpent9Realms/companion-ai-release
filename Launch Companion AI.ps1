$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Url = "http://127.0.0.1:59137"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = "python" }

# Kill any existing app.py instances from this install directory
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like "*app.py*" -and $_.CommandLine -like "*$AppDir*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Sleep -Milliseconds 300
Start-Process -FilePath $PythonExe -ArgumentList @((Join-Path $AppDir "app.py")) -WorkingDirectory $AppDir -WindowStyle Hidden
Start-Sleep -Seconds 1
Start-Process $Url
