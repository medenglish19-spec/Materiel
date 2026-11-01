param(
    [string]$Version = "",
    [string]$BuildDirectory = "",
    [string]$ReleaseDirectory = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VersionPath = Join-Path $PSScriptRoot "version.txt"
$DeclaredVersion = (Get-Content -LiteralPath $VersionPath -Raw).Trim()
$Version = if ($Version) { $Version } else { $DeclaredVersion }
if ($Version -ne $DeclaredVersion) {
    throw "Requested version $Version does not match windows\version.txt ($DeclaredVersion)."
}
$BrandingConfigPath = Join-Path $RepoRoot "splash-screen\config.json"
if (-not (Test-Path -LiteralPath $BrandingConfigPath)) {
    throw "Set splash-screen\config.json before building the installer."
}
$BrandingConfig = Get-Content -LiteralPath $BrandingConfigPath -Raw | ConvertFrom-Json
if ([string]$BrandingConfig.version -ne $Version) {
    throw "splash-screen\config.json version does not match windows\version.txt ($Version)."
}
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
$ArtifactRoot = Join-Path $env:LOCALAPPDATA "Materiel"
if (-not $BuildDirectory) {
    $BuildDirectory = Join-Path $ArtifactRoot "build"
}
if (-not $ReleaseDirectory) {
    $ReleaseDirectory = Join-Path $ArtifactRoot "release"
}
$BuildRoot = Join-Path $BuildDirectory "$Version-$Commit-$BuildId"
$Distribution = Join-Path $BuildRoot "dist\Materiel"
$ReleaseRoot = $ReleaseDirectory

if (Test-Path -LiteralPath $BuildRoot) {
    throw "Build directory already exists: $BuildRoot. Keep it for review or choose a different version/build id."
}
New-Item -ItemType Directory -Path $BuildRoot, $ReleaseRoot -Force | Out-Null

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

$CompilerArguments = @(
    "/DSourceDir=$Distribution",
    "/DOutputDir=$ReleaseRoot",
    "/DAppVersion=$Version",
    (Join-Path $PSScriptRoot "materiel.iss")
)
& $Iscc @CompilerArguments
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }

$SetupExe = Join-Path $ReleaseRoot "Materiel-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $SetupExe)) { throw "Installer output was not created: $SetupExe" }
Write-Output "Installer created: $SetupExe"
