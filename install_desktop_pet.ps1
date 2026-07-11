$ErrorActionPreference = "Stop"

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DefaultInstallDir = Join-Path $env:LOCALAPPDATA "CompanionAI"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Companion AI"
$DesktopDir = [Environment]::GetFolderPath("Desktop")

Add-Type -AssemblyName System.Windows.Forms

function Write-Step($Text) {
    Write-Host "[Companion AI] $Text"
}

function New-Shortcut($Path, $Target, $Arguments, $WorkingDirectory, $Description, $IconPath = $null) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Description = $Description
    if ($IconPath) {
        $shortcut.IconLocation = "$IconPath,0"
    }
    $shortcut.Save()
}

function Select-InstallDir($DefaultPath) {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "选择 Companion AI 安装位置"
    $dialog.SelectedPath = $DefaultPath
    $dialog.ShowNewFolderButton = $true
    $result = $dialog.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dialog.SelectedPath) {
        return $dialog.SelectedPath
    }
    return $DefaultPath
}

function Ask-YesNo($Title, $Text) {
    $buttons = [System.Windows.Forms.MessageBoxButtons]::YesNo
    $icon = [System.Windows.Forms.MessageBoxIcon]::Question
    $result = [System.Windows.Forms.MessageBox]::Show($Text, $Title, $buttons, $icon)
    return $result -eq [System.Windows.Forms.DialogResult]::Yes
}

function Select-PyTorchPlatform() {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "PyTorch 安装平台"
    $form.Width = 420
    $form.Height = 260
    $form.StartPosition = "CenterScreen"

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "选择 PyTorch 计算平台。NVIDIA 新显卡通常选 CUDA 12.8；AMD/Intel Windows 显卡请选择 DirectML。"
    $label.Left = 18
    $label.Top = 18
    $label.Width = 360
    $label.Height = 48
    $form.Controls.Add($label)

    $combo = New-Object System.Windows.Forms.ComboBox
    $combo.Left = 18
    $combo.Top = 76
    $combo.Width = 360
    $combo.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
    [void]$combo.Items.Add("CUDA 12.8")
    [void]$combo.Items.Add("CUDA 12.6")
    [void]$combo.Items.Add("CUDA 11.8")
    [void]$combo.Items.Add("AMD/Intel DirectML")
    [void]$combo.Items.Add("CPU")
    $combo.SelectedIndex = 0
    $form.Controls.Add($combo)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "确定"
    $ok.Left = 218
    $ok.Top = 140
    $ok.Width = 75
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $ok
    $form.Controls.Add($ok)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "取消"
    $cancel.Left = 303
    $cancel.Top = 140
    $cancel.Width = 75
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancel
    $form.Controls.Add($cancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        return [string]$combo.SelectedItem
    }
    return "Skip"
}

function Get-PythonForVenv() {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $probe = & py -3.12 -c "import sys; print(sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @("py", "-3.12")
        }
    }
    return @("python")
}

function Install-PyTorch($InstallDir, $Platform) {
    if ($Platform -eq "Skip") {
        return
    }
    $venvDir = Join-Path $InstallDir ".venv"
    $pythonCmd = Get-PythonForVenv
    Write-Step "Creating Python virtual environment at $venvDir"
    if ($pythonCmd.Length -gt 1) {
        & $pythonCmd[0] $pythonCmd[1] -m venv $venvDir
    } else {
        & $pythonCmd[0] -m venv $venvDir
    }

    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    & $venvPython -m pip install --upgrade pip

    $indexUrl = ""
    if ($Platform -eq "AMD/Intel DirectML") {
        Write-Step "Installing PyTorch DirectML backend for AMD/Intel Windows GPU. This can take a while."
        & $venvPython -m pip uninstall -y torch torchvision torchaudio torch-directml rocm-sdk-core rocm-sdk-libraries 2>$null | Out-Null
        & $venvPython -m pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu
        & $venvPython -m pip install --upgrade --force-reinstall torch-directml
    } elseif ($Platform -eq "AMD ROCm (RX 7000/6000系列)") {
        Write-Step "Windows AMD GPU detected. Installing PyTorch CPU + torch-directml instead of ROCm."
        & $venvPython -m pip uninstall -y torch torchvision torchaudio torch-directml rocm-sdk-core rocm-sdk-libraries 2>$null | Out-Null
        & $venvPython -m pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu
        & $venvPython -m pip install --upgrade --force-reinstall torch-directml
    } else {
        if ($Platform -eq "CUDA 12.8") { $indexUrl = "https://download.pytorch.org/whl/cu128" }
        elseif ($Platform -eq "CUDA 12.6") { $indexUrl = "https://download.pytorch.org/whl/cu126" }
        elseif ($Platform -eq "CUDA 11.8") { $indexUrl = "https://download.pytorch.org/whl/cu118" }
        elseif ($Platform -eq "CPU") { $indexUrl = "https://download.pytorch.org/whl/cpu" }

        Write-Step "Installing PyTorch ($Platform). This can take a while."
        & $venvPython -m pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url $indexUrl
    }

    $verifyPy = Join-Path $InstallDir "_verify_torch.py"
    $verifyCode = @'
import torch
print(torch.__version__)
print("cuda=" + str(torch.cuda.is_available()))
try:
    import torch_directml
    print("directml=True")
    print(torch_directml.device())
except Exception as e:
    print("directml=False")
    print(e)
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0))
else:
    print("no cuda")
'@
    Set-Content -LiteralPath $verifyPy -Value $verifyCode -Encoding UTF8
    $verify = & $venvPython $verifyPy 2>&1
    Set-Content -LiteralPath (Join-Path $InstallDir "pytorch_install_log.txt") -Value ($verify -join "`n") -Encoding UTF8
    Write-Step "PyTorch verification:"
    $verify | ForEach-Object { Write-Host $_ }

    if (Ask-YesNo "数据集支持" "是否安装 HuggingFace datasets 和 ModelScope 支持？(用于加载外部训练数据集，约 200MB)") {
        Write-Step "Installing datasets and modelscope libraries..."
        & $venvPython -m pip install datasets modelscope huggingface-hub addict pyarrow pandas fsspec dill multiprocess xxhash
    }

    if (Ask-YesNo "本地 LLM 训练" "是否安装 LLM 训练依赖？(transformers/peft/accelerate，用于微调本地对话模型)") {
        Write-Step "Installing LLM training dependencies..."
        & $venvPython -m pip install transformers peft accelerate bitsandbytes
    }
}

$InstallDir = Select-InstallDir $DefaultInstallDir
if ($InstallDir -match '^[A-Za-z]:\\$') {
    $InstallDir = Join-Path $InstallDir "CompanionAI"
    Write-Step "根目录已自动改为 $InstallDir"
}
Write-Step "PyTorch / ZLUDA 可在安装后通过桌宠右键菜单 -> 设置 中安装。"

Write-Step "Installing to $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

$AppFiles = @(
    "app.py",
    "neural_companion.py",
    "dataset_loader.py",
    "train.py",
    "train_config.json",
    "llm_trainer.py",
    "llm_inference.py",
    "train_llm.py",
    "dialogue_datasets.json",
    "tiny_llm.py",
    "retrieval_chat.py",
    "hybrid_chat.py",
    "rapidocr_runner.py",
    "plugin_manager.py",
    "desktop_pet.py",
    "pet_icon.ico",
    "README.md",
    "start_desktop_pet.ps1"
)

foreach ($file in $AppFiles) {
    Copy-Item -LiteralPath (Join-Path $SourceDir $file) -Destination (Join-Path $InstallDir $file) -Force
}

$SourceData = Join-Path $SourceDir "data"
$InstallData = Join-Path $InstallDir "data"
if (-not (Test-Path -LiteralPath $InstallData)) {
    Copy-Item -LiteralPath $SourceData -Destination $InstallData -Recurse -Force
} else {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "uploads") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "models") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "live2d") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "datasets") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "neural") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "llm") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "llm" "adapters") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallData "llm" "merged") | Out-Null
}

$SourcePlugins = Join-Path $SourceDir "plugins"
$InstallPlugins = Join-Path $InstallDir "plugins"
if (-not (Test-Path -LiteralPath $InstallPlugins)) {
    if (Test-Path -LiteralPath $SourcePlugins) {
        Copy-Item -LiteralPath $SourcePlugins -Destination $InstallPlugins -Recurse -Force
    } else {
        New-Item -ItemType Directory -Force -Path $InstallPlugins | Out-Null
    }
}

$LaunchWeb = @'
$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Url = "http://127.0.0.1:59137"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = "python" }

$serverReady = $false
try {
    Invoke-WebRequest -UseBasicParsing "$Url/api/memory" -TimeoutSec 1 | Out-Null
    $serverReady = $true
} catch {
    $serverReady = $false
}

if (-not $serverReady) {
    Start-Process -FilePath $PythonExe -ArgumentList @((Join-Path $AppDir "app.py")) -WorkingDirectory $AppDir -WindowStyle Hidden
    Start-Sleep -Seconds 1
}

Start-Process $Url
'@

$LaunchPet = @'
$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PetPath = Join-Path $AppDir "desktop_pet.py"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = "python" }
$running = Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like "*desktop_pet.py*" -and $_.CommandLine -like "*CompanionAI*" }
if (-not $running) {
    Start-Process -FilePath $PythonExe -ArgumentList @($PetPath) -WorkingDirectory $AppDir -WindowStyle Hidden
}
'@

$StopAll = @'
$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like "*CompanionAI*" -and ($_.CommandLine -like "*app.py*" -or $_.CommandLine -like "*desktop_pet.py*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
'@

$Uninstall = @'
$ErrorActionPreference = "SilentlyContinue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Companion AI"
$CommonStartMenuDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Companion AI"
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$CommonDesktopDir = [Environment]::GetFolderPath("CommonDesktopDirectory")

Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like "*CompanionAI*" -and ($_.CommandLine -like "*app.py*" -or $_.CommandLine -like "*desktop_pet.py*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

foreach ($dir in @($DesktopDir, $CommonDesktopDir)) {
    if (-not $dir) { continue }
    foreach ($name in @("AI陪伴桌宠 - 桌宠.lnk", "AI陪伴桌宠.lnk", "Companion AI.lnk", "Companion Pet.lnk")) {
        Remove-Item -LiteralPath (Join-Path $dir $name) -Force
    }
}
foreach ($dir in @($StartMenuDir, $CommonStartMenuDir)) {
    Remove-Item -LiteralPath $dir -Recurse -Force
}
Start-Sleep -Milliseconds 300
Remove-Item -LiteralPath $AppDir -Recurse -Force
'@

Set-Content -LiteralPath (Join-Path $InstallDir "Launch Companion AI.ps1") -Value $LaunchWeb -Encoding UTF8
Set-Content -LiteralPath (Join-Path $InstallDir "Launch Companion Pet.ps1") -Value $LaunchPet -Encoding UTF8
Set-Content -LiteralPath (Join-Path $InstallDir "Stop Companion AI.ps1") -Value $StopAll -Encoding UTF8
Set-Content -LiteralPath (Join-Path $InstallDir "Uninstall Companion AI.ps1") -Value $Uninstall -Encoding UTF8

$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$PetIcon = Join-Path $InstallDir "pet_icon.ico"
New-Shortcut -Path (Join-Path $DesktopDir "AI陪伴桌宠 - 桌宠.lnk") -Target $PowerShellExe -Arguments "-ExecutionPolicy Bypass -File `"$InstallDir\Launch Companion Pet.ps1`"" -WorkingDirectory $InstallDir -Description "Start Companion desktop pet" -IconPath $PetIcon
New-Shortcut -Path (Join-Path $StartMenuDir "Companion AI.lnk") -Target $PowerShellExe -Arguments "-ExecutionPolicy Bypass -File `"$InstallDir\Launch Companion AI.ps1`"" -WorkingDirectory $InstallDir -Description "Open Companion AI" -IconPath $PetIcon
New-Shortcut -Path (Join-Path $StartMenuDir "Companion Pet.lnk") -Target $PowerShellExe -Arguments "-ExecutionPolicy Bypass -File `"$InstallDir\Launch Companion Pet.ps1`"" -WorkingDirectory $InstallDir -Description "Start Companion desktop pet" -IconPath $PetIcon
New-Shortcut -Path (Join-Path $StartMenuDir "Stop Companion AI.lnk") -Target $PowerShellExe -Arguments "-ExecutionPolicy Bypass -File `"$InstallDir\Stop Companion AI.ps1`"" -WorkingDirectory $InstallDir -Description "Stop Companion AI processes" -IconPath $PetIcon
New-Shortcut -Path (Join-Path $StartMenuDir "Uninstall Companion AI.lnk") -Target $PowerShellExe -Arguments "-ExecutionPolicy Bypass -File `"$InstallDir\Uninstall Companion AI.ps1`"" -WorkingDirectory $InstallDir -Description "Uninstall Companion AI" -IconPath $PetIcon

Write-Step "Installed shortcuts on Desktop and Start Menu."
Write-Step "Starting desktop pet..."
& (Join-Path $InstallDir "Launch Companion Pet.ps1")
Write-Step "Done."
