param(
    [switch]$SkipSigning,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$CertificateThumbprint = $env:CODE_SIGN_CERT_SHA1,
    [string]$CertificateSubject = $env:CODE_SIGN_CERT_SUBJECT,
    [string]$PfxPath = $env:CODE_SIGN_PFX_PATH,
    [string]$PfxPassword = $env:CODE_SIGN_PFX_PASSWORD,
    [string]$SignToolPath = $env:SIGNTOOL_PATH,
    [string]$MakeNsisPath = $env:MAKENSIS_PATH
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExe = Join-Path $Root "dist\CompanionAI\CompanionAI.exe"
$NsiFile = Join-Path $Root "companion_ai_setup.nsi"
$InstallerExe = Join-Path $Root "installer_output\AI陪伴桌宠-Setup.exe"

function Resolve-CommandPath {
    param(
        [string]$ExplicitPath,
        [string]$CommandName,
        [string[]]$FallbackPaths = @()
    )

    if ($ExplicitPath) {
        if (Test-Path -LiteralPath $ExplicitPath) {
            return (Resolve-Path -LiteralPath $ExplicitPath).Path
        }
        throw "$CommandName not found at: $ExplicitPath"
    }

    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    foreach ($path in $FallbackPaths) {
        if (Test-Path -LiteralPath $path) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }

    throw "$CommandName was not found. Install it or set the related environment variable."
}

function Resolve-SignTool {
    $kitRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    $fallbacks = @()
    if (Test-Path -LiteralPath $kitRoot) {
        $fallbacks = Get-ChildItem -LiteralPath $kitRoot -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\signtool.exe" } |
            Where-Object { Test-Path -LiteralPath $_ }
    }

    Resolve-CommandPath -ExplicitPath $SignToolPath -CommandName "signtool.exe" -FallbackPaths $fallbacks
}

function Resolve-MakeNsis {
    $fallbacks = @(
        "$env:ProgramFiles\NSIS\makensis.exe",
        "${env:ProgramFiles(x86)}\NSIS\makensis.exe"
    )
    Resolve-CommandPath -ExplicitPath $MakeNsisPath -CommandName "makensis.exe" -FallbackPaths $fallbacks
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

function Sign-PortableExecutable {
    param(
        [string]$Path,
        [string]$SignTool
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "File to sign was not found: $Path"
    }

    $args = @("sign", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256")
    if ($PfxPath) {
        $args += @("/f", $PfxPath)
        if ($PfxPassword) {
            $args += @("/p", $PfxPassword)
        }
    } elseif ($CertificateThumbprint) {
        $args += @("/sha1", $CertificateThumbprint)
    } elseif ($CertificateSubject) {
        $args += @("/n", $CertificateSubject)
    } else {
        $args += "/a"
    }
    $args += $Path

    Write-Host "[release] Signing: $Path"
    Invoke-Checked -FilePath $SignTool -Arguments $args
    Invoke-Checked -FilePath $SignTool -Arguments @("verify", "/pa", "/v", $Path)
}

Push-Location $Root
try {
    Write-Host "[release] Building PyInstaller app..."
    Invoke-Checked -FilePath (Get-Command python).Source -Arguments @("build_exe.py", "--no-version-prompt")

    if (-not $SkipSigning) {
        $signTool = Resolve-SignTool
        Sign-PortableExecutable -Path $AppExe -SignTool $signTool
    } else {
        Write-Host "[release] Skipping app signing."
    }

    Write-Host "[release] Building NSIS installer..."
    $makeNsis = Resolve-MakeNsis
    Invoke-Checked -FilePath $makeNsis -Arguments @($NsiFile)

    if (-not $SkipSigning) {
        if (-not $signTool) {
            $signTool = Resolve-SignTool
        }
        Sign-PortableExecutable -Path $InstallerExe -SignTool $signTool
    } else {
        Write-Host "[release] Skipping installer signing."
    }

    Write-Host "[release] Done: $InstallerExe"
} finally {
    Pop-Location
}
