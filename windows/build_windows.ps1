param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Version) {
    $Version = (Get-Content (Join-Path $PSScriptRoot "version.txt") -Raw).Trim()
}
$BrandingConfigPath = Join-Path $RepoRoot "splash-screen\config.json"
if (-not (Test-Path -LiteralPath $BrandingConfigPath)) {
    throw "Set splash-screen\config.json before building the installer."
}
$BrandingConfig = Get-Content -LiteralPath $BrandingConfigPath -Raw | ConvertFrom-Json
$LogoName = [string]$BrandingConfig.logo_file
if (-not $LogoName -or [IO.Path]::GetFileName($LogoName) -ne $LogoName) {
    throw "Set logo_file to a file name inside splash-screen\ (for example logo.png)."
}
$LogoPath = Join-Path (Join-Path $RepoRoot "splash-screen") $LogoName
if (-not (Test-Path -LiteralPath $LogoPath -PathType Leaf)) {
    throw "Add the configured logo before building: $LogoPath"
}
$Commit = (& git -C $RepoRoot rev-parse --short HEAD).Trim()
$BuildId = Get-Date -Format "yyyyMMdd-HHmmss"
$BuildRoot = Join-Path "D:\Materiel-build" "$Version-$Commit-$BuildId"
$Distribution = Join-Path $BuildRoot "dist\Materiel"
$ReleaseRoot = "D:\Materiel-release"

if (Test-Path -LiteralPath $BuildRoot) {
    throw "Build directory already exists: $BuildRoot. Keep it for review or choose a different version/build id."
}
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

$Venv = Join-Path $BuildRoot "venv"
& python -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated build environment." }
$BuildPython = Join-Path $Venv "Scripts\python.exe"
& $BuildPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not prepare pip in the build environment." }
& $BuildPython -m pip install -r (Join-Path $RepoRoot "requirements.txt") -r (Join-Path $PSScriptRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned build requirements." }

& $BuildPython -m PyInstaller --noconfirm --clean --distpath (Join-Path $BuildRoot "dist") --workpath (Join-Path $BuildRoot "work") (Join-Path $PSScriptRoot "Materiel.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$IsccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Iscc) { throw "Inno Setup 6 compiler ISCC.exe is not installed." }

$SourceDefine = "/DSourceDir=$Distribution"
$OutputDefine = "/DOutputDir=$ReleaseRoot"
$VersionDefine = "/DAppVersion=$Version"
& $Iscc $SourceDefine $OutputDefine $VersionDefine (Join-Path $PSScriptRoot "materiel.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

$SetupExe = Join-Path $ReleaseRoot "Materiel-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $SetupExe)) { throw "Installer output was not created: $SetupExe" }
Write-Output "Installer created: $SetupExe"
