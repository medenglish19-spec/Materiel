param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath
)

$ErrorActionPreference = "Stop"
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$Root = Join-Path "D:\Materiel-smoke-tests" ([guid]::NewGuid().ToString("N"))
$InstallDir = Join-Path $Root "program"
$DataDir = Join-Path $Root "user-data"
$DatabasePath = Join-Path $DataDir "fleet_assets.db"
$SplashDir = Join-Path $InstallDir "_internal\splash-screen"
$LogPath = Join-Path $Root "installer.log"
$PortListener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$PortListener.Start()
$Port = $PortListener.LocalEndpoint.Port
$PortListener.Stop()
$BaseUrl = "http://127.0.0.1:$Port"
$Process = $null
$OldEnvironment = @{}

foreach ($Name in @("MATERIEL_DATA_DIR", "APP_HOST", "APP_PORT", "MATERIEL_NO_BROWSER")) {
    $OldEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}
[Environment]::SetEnvironmentVariable("MATERIEL_DATA_DIR", $DataDir, "Process")
[Environment]::SetEnvironmentVariable("APP_HOST", "127.0.0.1", "Process")
[Environment]::SetEnvironmentVariable("APP_PORT", [string]$Port, "Process")
[Environment]::SetEnvironmentVariable("MATERIEL_NO_BROWSER", "1", "Process")

function Invoke-Installer {
    $Arguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=$InstallDir",
        "/LOG=$LogPath"
    )
    $Setup = Start-Process -FilePath $InstallerPath -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
    if ($Setup.ExitCode -ne 0) {
        throw "Installer exited with code $($Setup.ExitCode). Review $LogPath"
    }
}

function Start-PackagedApp {
    $script:Process = Start-Process -FilePath (Join-Path $InstallDir "Materiel.exe") -WorkingDirectory $InstallDir -PassThru -WindowStyle Hidden
    $Deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $Deadline) {
        if ($script:Process.HasExited) {
            throw "Packaged application exited with code $($script:Process.ExitCode). Review $(Join-Path $DataDir 'logs\app.log')"
        }
        try {
            $Response = Invoke-WebRequest -Uri "$BaseUrl/health" -TimeoutSec 2 -UseBasicParsing
            if ($Response.StatusCode -eq 200) { return }
        }
        catch { Start-Sleep -Milliseconds 400 }
    }
    throw "Packaged application did not become healthy at $BaseUrl."
}

function Stop-PackagedApp {
    if ($script:Process -and -not $script:Process.HasExited) {
        Stop-Process -Id $script:Process.Id -Force
        $script:Process.WaitForExit(10000)
    }
    $script:Process = $null
}

function Get-PackagedBranding {
    $ConfigPath = Join-Path $SplashDir "config.json"
    if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Release branding config is missing from the protected application bundle." }
    return Get-Content -LiteralPath $ConfigPath -Encoding UTF8 -Raw | ConvertFrom-Json
}

function Assert-SplashContent {
    $Branding = Get-PackagedBranding
    $Page = (Invoke-WebRequest -Uri "$BaseUrl/" -TimeoutSec 10 -UseBasicParsing).Content
    if (-not $Page.Contains($Branding.institution_name)) { throw "Packaged institution text was not rendered." }
    if (-not $Page.Contains($Branding.description)) { throw "Packaged splash description was not rendered." }
    if (-not $Page.Contains($Branding.developer_name)) { throw "Packaged developer text was not rendered." }
    if (-not $Page.Contains("الإصدار $($Branding.version)")) { throw "Packaged version text was not rendered." }

    $LogoPath = Join-Path $SplashDir $Branding.logo_file
    if (Test-Path -LiteralPath $LogoPath) {
        $ExpectedLogo = "data:image/png;base64,$([Convert]::ToBase64String([IO.File]::ReadAllBytes($LogoPath)))"
        if (-not $Page.Contains($ExpectedLogo)) { throw "Packaged splash logo was not rendered." }
    }
    if ($Page.Contains("محاولة تعديل المستخدم")) { throw "User data overrode the release branding." }
}

function Assert-SidebarInstitution {
    $Branding = Get-PackagedBranding
    $WebSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-WebRequest -Uri "$BaseUrl/login" -Method Post -Body @{ username = "admin"; password = "Admin@123" } -WebSession $WebSession -TimeoutSec 10 -UseBasicParsing | Out-Null
    $Dashboard = (Invoke-WebRequest -Uri "$BaseUrl/dashboard" -WebSession $WebSession -TimeoutSec 10 -UseBasicParsing).Content
    if (-not $Dashboard.Contains("<span class=`"app-brand-institution`">$($Branding.institution_name)</span>")) {
        throw "Packaged institution text was not rendered in the application sidebar."
    }
}

try {
    New-Item -ItemType Directory -Path $InstallDir, $DataDir -Force | Out-Null
    # The elevated installer may receive a filtered environment. Preseed its
    # sidecar so QA can never fall back to the default operational data path.
    [IO.File]::WriteAllText((Join-Path $InstallDir "materiel-data-dir.txt"), $DataDir + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Invoke-Installer

    $ExePath = Join-Path $InstallDir "Materiel.exe"
    $DataDirFile = Join-Path $InstallDir "materiel-data-dir.txt"
    if (-not (Test-Path -LiteralPath $ExePath)) { throw "Installed executable is missing." }
    if ((Get-Content -LiteralPath $DataDirFile -Raw).Trim() -ne $DataDir) { throw "Installer did not preserve the selected data directory in its sidecar." }

    $DataSplashDir = Join-Path $DataDir "splash-screen"
    New-Item -ItemType Directory -Path $DataSplashDir -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $DataSplashDir "config.json"), '{"institution_name":"محاولة تعديل المستخدم","description":"تجاوز بيانات الإصدار"}', [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllBytes((Join-Path $DataSplashDir "logo.png"), [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGO8IyfHwMDAxAAGAA4IARwNj/i7AAAAAElFTkSuQmCC"))

    $Branding = Get-PackagedBranding
    $UsersSid = [System.Security.Principal.SecurityIdentifier]::new("S-1-5-32-545")
    $WriteRights = [System.Security.AccessControl.FileSystemRights]::WriteData -bor `
        [System.Security.AccessControl.FileSystemRights]::AppendData -bor `
        [System.Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor `
        [System.Security.AccessControl.FileSystemRights]::WriteAttributes -bor `
        [System.Security.AccessControl.FileSystemRights]::Delete -bor `
        [System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor `
        [System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor `
        [System.Security.AccessControl.FileSystemRights]::TakeOwnership
    $ProtectedPaths = @($SplashDir, (Join-Path $SplashDir "config.json"), (Join-Path $SplashDir $Branding.logo_file))
    foreach ($ProtectedPath in $ProtectedPaths) {
        $UsersRules = (Get-Acl -LiteralPath $ProtectedPath).Access | Where-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -eq $UsersSid.Value }
        if (-not $UsersRules) { throw "Standard-user read access is missing: $ProtectedPath" }
        foreach ($Rule in $UsersRules) {
            if (($Rule.FileSystemRights -band $WriteRights) -ne 0) { throw "Standard users can modify release branding: $ProtectedPath" }
        }
    }

    Start-PackagedApp
    Assert-SplashContent
    Assert-SidebarInstitution
    Stop-PackagedApp

    @'
import sqlite3, sys
path = sys.argv[1]
with sqlite3.connect(path) as db:
    db.execute("CREATE TABLE IF NOT EXISTS installer_smoke_probe (marker TEXT NOT NULL)")
    db.execute("DELETE FROM installer_smoke_probe")
    db.execute("INSERT INTO installer_smoke_probe(marker) VALUES (?)", ("preserve-me-across-update",))
'@ | python - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "Could not write the isolated database preservation marker." }

    Invoke-Installer

    if (-not (Get-ChildItem (Join-Path $DataDir "backups") -Filter "fleet_assets.before-update-*.db" -ErrorAction SilentlyContinue)) { throw "Installer update did not back up the existing user database." }

    Start-PackagedApp
    Assert-SplashContent
    Assert-SidebarInstitution
    @'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    row = db.execute("SELECT marker FROM installer_smoke_probe").fetchone()
    assert row == ("preserve-me-across-update",), row
'@ | python - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "User database marker was not preserved across upgrade and startup." }

    Write-Output "PASS: installed EXE started and served /health and splash page."
    Write-Output "PASS: release welcome text, version and logo rendered from the installed application bundle."
    Write-Output "PASS: configured institution name rendered in the application sidebar."
    Write-Output "PASS: standard users cannot modify the installed branding, and user-data overrides are ignored."
    Write-Output "PASS: installer update retained release branding and user database data."
    Write-Output "PASS: user database marker survived installer update and application startup."
    Write-Output "QA installation retained for inspection: $Root"
    Write-Output "Installer log: $LogPath"
}
finally {
    Stop-PackagedApp
    foreach ($Name in $OldEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $OldEnvironment[$Name], "Process")
    }
}
