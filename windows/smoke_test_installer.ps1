param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$PythonExecutable,
    [string]$Root = ""
)

$ErrorActionPreference = "Stop"
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path
if ([IO.Path]::GetFileName($PythonExecutable) -ine "python.exe") {
    throw "PythonExecutable must point to the build environment's python.exe: $PythonExecutable"
}
$SmokeTestRoot = [IO.Path]::GetFullPath(
    (Join-Path $env:LOCALAPPDATA "Materiel\smoke-tests")
)
if (-not $Root) {
    $Root = Join-Path $SmokeTestRoot ([guid]::NewGuid().ToString("N"))
}
else {
    $Root = [IO.Path]::GetFullPath($Root)
    if (-not $Root.StartsWith(
        $SmokeTestRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Root must be a dedicated directory inside $SmokeTestRoot."
    }
}
$InstallDir = Join-Path $Root "program"
$DataDir = Join-Path $Root "user-data"
$DatabasePath = Join-Path $DataDir "fleet_assets.db"
$AttachmentPath = Join-Path $DataDir "uploads\installer-smoke\preserve.txt"
$SplashDir = Join-Path $InstallDir "_internal\splash-screen"
$LogPath = Join-Path $Root "installer.log"
$BaseUrl = $null
$Process = $null
$UsedPort = $null
$script:InitialAdminPassword = "SmokeTest-$([guid]::NewGuid().ToString('N'))!Aa"
$script:ReinstallAdminPassword = "Reinstall-$([guid]::NewGuid().ToString('N'))!Bb"
$OldEnvironment = @{}

foreach ($Name in @("MATERIEL_DATA_DIR", "APP_HOST", "APP_PORT", "MATERIEL_NO_BROWSER", "DATABASE_URL", "SECRET_KEY", "LOG_DIR", "APP_ENV", "DEV_DISABLE_AUTH")) {
    $OldEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}
[Environment]::SetEnvironmentVariable("MATERIEL_DATA_DIR", $DataDir, "Process")
[Environment]::SetEnvironmentVariable("APP_HOST", "127.0.0.1", "Process")
[Environment]::SetEnvironmentVariable("APP_PORT", "8000", "Process")
[Environment]::SetEnvironmentVariable("MATERIEL_NO_BROWSER", "1", "Process")
[Environment]::SetEnvironmentVariable("DATABASE_URL", $null, "Process")
[Environment]::SetEnvironmentVariable("SECRET_KEY", $null, "Process")
[Environment]::SetEnvironmentVariable("LOG_DIR", $null, "Process")
[Environment]::SetEnvironmentVariable("APP_ENV", "production", "Process")
[Environment]::SetEnvironmentVariable("DEV_DISABLE_AUTH", "false", "Process")

function Invoke-Installer {
    $Arguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=`"$InstallDir`"",
        "/LOG=`"$LogPath`""
    )
    $Setup = Start-Process -FilePath $InstallerPath -ArgumentList $Arguments -Verb RunAs -Wait -PassThru
    if ($Setup.ExitCode -ne 0) {
        throw "Installer exited with code $($Setup.ExitCode). Review $LogPath"
    }
}

function Assert-GuiExecutable {
    $ExePath = Join-Path $InstallDir "Materiel.exe"
    $Stream = [IO.File]::OpenRead($ExePath)
    $Reader = [IO.BinaryReader]::new($Stream)
    try {
        $Stream.Position = 0
        if ($Reader.ReadUInt16() -ne 0x5A4D) { throw "Installed executable has no valid DOS header." }
        $Stream.Position = 0x3c
        $PeOffset = $Reader.ReadInt32()
        $Stream.Position = $PeOffset
        if ($Reader.ReadUInt32() -ne 0x00004550) { throw "Installed executable has no valid PE header." }
        $Stream.Position = $PeOffset + 24 + 68
        $Subsystem = $Reader.ReadUInt16()
        if ($Subsystem -ne 2) {
            throw "Installed executable is not a Windows GUI executable (PE subsystem=$Subsystem)."
        }
    }
    finally {
        $Reader.Dispose()
        $Stream.Dispose()
    }
}

function Start-PackagedApp {
    Assert-GuiExecutable
    $PortFile = Join-Path $DataDir "server-Materiel.port"
    Remove-Item -LiteralPath $PortFile -Force -ErrorAction SilentlyContinue
    $PortBlocker = $null
    try {
        $PortBlocker = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
        $PortBlocker.Start()
    }
    catch [System.Net.Sockets.SocketException] {
        if ($PortBlocker) { $PortBlocker.Stop() }
        $PortBlocker = $null
        Write-Output "Port 8000 was already occupied; testing the existing conflict."
    }

    try {
        $script:Process = Start-Process -FilePath (Join-Path $InstallDir "Materiel.exe") -WorkingDirectory $InstallDir -PassThru -WindowStyle Hidden
        $Deadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $Deadline) {
            if ($script:Process.HasExited) {
                throw "Packaged application exited with code $($script:Process.ExitCode). Review $(Join-Path $DataDir 'logs\error.log')"
            }
            if (Test-Path -LiteralPath $PortFile) {
                $CandidatePort = 0
                if ([int]::TryParse((Get-Content -LiteralPath $PortFile -Raw).Trim(), [ref]$CandidatePort) -and $CandidatePort -gt 0) {
                    if ($PortBlocker -and $CandidatePort -eq 8000) {
                        throw "The packaged application claimed occupied port 8000 instead of choosing a free port."
                    }
                    $script:BaseUrl = "http://127.0.0.1:$CandidatePort"
                    try {
                        $Response = Invoke-WebRequest -Uri "$script:BaseUrl/health" -TimeoutSec 2 -UseBasicParsing
                        if ($Response.StatusCode -eq 200) {
                            $script:UsedPort = $CandidatePort
                            $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($script:Process.Id)" -ErrorAction SilentlyContinue
                            if ($Children | Where-Object { $_.Name -ieq "conhost.exe" }) {
                                throw "A console host process was created by the packaged GUI application."
                            }
                            return
                        }
                    }
                    catch [System.Net.WebException] { }
                    catch [System.Net.Http.HttpRequestException] { }
                    catch [System.Threading.Tasks.TaskCanceledException] { }
                }
            }
            Start-Sleep -Milliseconds 250
        }
        throw "Packaged application did not become healthy at its recorded local server port."
    }
    finally {
        if ($PortBlocker) { $PortBlocker.Stop() }
    }
}

function Stop-PackagedApp {
    if ($script:Process -and -not $script:Process.HasExited) {
        $Shutdown = Start-Process `
            -FilePath (Join-Path $InstallDir "Materiel.exe") `
            -ArgumentList "--shutdown" `
            -WorkingDirectory $InstallDir `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($Shutdown.ExitCode -ne 0) {
            throw "Graceful shutdown request failed with exit code $($Shutdown.ExitCode)."
        }
        if (-not $script:Process.WaitForExit(30000)) {
            throw "Packaged application did not stop after the graceful shutdown request."
        }
        if ($script:Process.ExitCode -ne 0) {
            throw "Packaged application exited with code $($script:Process.ExitCode) during shutdown."
        }
    }
    $script:Process = $null
}

function Invoke-Uninstaller {
    $UninstallerPath = Join-Path $InstallDir "unins000.exe"
    if (-not (Test-Path -LiteralPath $UninstallerPath)) { throw "Uninstaller was not installed." }
    $UninstallLog = Join-Path $Root "uninstaller.log"
    $Arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$UninstallLog`"")
    $Uninstaller = Start-Process -FilePath $UninstallerPath -ArgumentList $Arguments -Verb RunAs -Wait -PassThru
    if ($Uninstaller.ExitCode -ne 0) { throw "Uninstaller exited with code $($Uninstaller.ExitCode). Review $UninstallLog" }
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
    if (-not $Page.Contains($Branding.developer_name.Trim())) { throw "Packaged developer text was not rendered." }
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
    try {
        $UnauthenticatedDashboard = Invoke-WebRequest -Uri "$BaseUrl/dashboard" -TimeoutSec 10 -UseBasicParsing
        throw "The packaged application allowed an unauthenticated dashboard request."
    }
    catch {
        $Response = $_.Exception.Response
        if (-not $Response -or [int]$Response.StatusCode -ne 401) {
            throw "The packaged application did not reject an unauthenticated dashboard request with HTTP 401."
        }
    }
    $WebSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $SetupPage = Invoke-WebRequest -Uri "$BaseUrl/setup" -WebSession $WebSession -TimeoutSec 10 -UseBasicParsing
    if ($SetupPage.Content.Contains('action="/setup"')) {
        Invoke-WebRequest -Uri "$BaseUrl/setup" -Method Post -Body @{
            password = $script:InitialAdminPassword
            confirmation = $script:InitialAdminPassword
        } -Headers @{ Origin = $BaseUrl } -WebSession $WebSession -TimeoutSec 10 -UseBasicParsing | Out-Null
    }
    else {
        Invoke-WebRequest -Uri "$BaseUrl/login" -Method Post -Body @{
            username = "admin"
            password = $script:InitialAdminPassword
        } -WebSession $WebSession -TimeoutSec 10 -UseBasicParsing | Out-Null
    }
    $Dashboard = (Invoke-WebRequest -Uri "$BaseUrl/dashboard" -WebSession $WebSession -TimeoutSec 10 -UseBasicParsing).Content
    if (-not $Dashboard.Contains("<span class=`"app-brand-institution`">$($Branding.institution_name)</span>")) {
        throw "Packaged institution text was not rendered in the application sidebar."
    }
}

function Assert-SetupNotRequired {
    $Page = Invoke-WebRequest -Uri "$BaseUrl/setup" -TimeoutSec 10 -UseBasicParsing
    if ($Page.Content.Contains('action="/setup"')) {
        throw "The application unexpectedly required first-run setup after an update."
    }
}

function Assert-FirstRunSetupAvailable {
    $Page = Invoke-WebRequest -Uri "$BaseUrl/setup" -TimeoutSec 10 -UseBasicParsing
    if (-not $Page.Content.Contains('action="/setup"')) {
        throw "Reinstall did not present the first-run administrator setup page."
    }
}

function New-FirstRunAdmin {
    param(
        [Parameter(Mandatory = $true)][string]$Username,
        [Parameter(Mandatory = $true)][string]$Password
    )
    $Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-WebRequest -Uri "$BaseUrl/setup" -Method Post -Body @{
        username = $Username
        password = $Password
        confirmation = $Password
    } -Headers @{ Origin = $BaseUrl } -WebSession $Session -TimeoutSec 10 -UseBasicParsing | Out-Null
    $Dashboard = Invoke-WebRequest -Uri "$BaseUrl/dashboard" -WebSession $Session -TimeoutSec 10 -UseBasicParsing
    if ($Dashboard.StatusCode -ne 200) {
        throw "The newly created administrator could not open the dashboard."
    }
}

function Assert-LoginWorks {
    param(
        [Parameter(Mandatory = $true)][string]$Username,
        [Parameter(Mandatory = $true)][string]$Password
    )
    $Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-WebRequest -Uri "$BaseUrl/login" -Method Post -Body @{
        username = $Username
        password = $Password
    } -WebSession $Session -TimeoutSec 10 -UseBasicParsing | Out-Null
    $Dashboard = Invoke-WebRequest -Uri "$BaseUrl/dashboard" -WebSession $Session -TimeoutSec 10 -UseBasicParsing
    if ($Dashboard.StatusCode -ne 200) {
        throw "Login for '$Username' did not open the dashboard."
    }
}

function Assert-LoginRejected {
    param(
        [Parameter(Mandatory = $true)][string]$Username,
        [Parameter(Mandatory = $true)][string]$Password
    )
    $Rejected = $false
    try {
        Invoke-WebRequest -Uri "$BaseUrl/login" -Method Post -Body @{
            username = $Username
            password = $Password
        } -WebSession (New-Object Microsoft.PowerShell.Commands.WebRequestSession) -TimeoutSec 10 -UseBasicParsing | Out-Null
    }
    catch {
        $Response = $_.Exception.Response
        if (-not $Response) {
            throw "Old credentials did not fail with an HTTP response."
        }
        $StatusCode = [int]$Response.StatusCode
        if ($StatusCode -ne 401) {
            throw "Old credentials failed with HTTP $StatusCode instead of 401."
        }
        $Rejected = $true
    }
    if (-not $Rejected) {
        throw "Old credentials were accepted after uninstall and reinstall."
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
    Write-Output "PASS: installed GUI EXE started on port $UsedPort while the default port 8000 was reserved."
    Assert-SplashContent
    Assert-SidebarInstitution
    Stop-PackagedApp

    New-Item -ItemType Directory -Path (Split-Path -Parent $AttachmentPath) -Force | Out-Null
    [IO.File]::WriteAllText($AttachmentPath, "preserve-this-attachment")
    @'
import sqlite3, sys
path = sys.argv[1]
with sqlite3.connect(path) as db:
    db.execute("CREATE TABLE IF NOT EXISTS installer_smoke_probe (marker TEXT NOT NULL)")
    db.execute("DELETE FROM installer_smoke_probe")
    db.execute("INSERT INTO installer_smoke_probe(marker) VALUES (?)", ("preserve-me-across-update",))
'@ | & $PythonExecutable - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "Could not write the isolated database preservation marker." }

    @'
import sqlite3, sys
path = sys.argv[1]
with sqlite3.connect(path) as db:
    columns = {row[1] for row in db.execute("PRAGMA table_info(equipment)")}
    if "image_url" in columns:
        db.execute("ALTER TABLE equipment DROP COLUMN image_url")
    db.execute("UPDATE alembic_version SET version_num=?", ("20261030_driver_model",))
'@ | & $PythonExecutable - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare the isolated database as a previous release schema." }

    Invoke-Installer

    if (-not (Get-ChildItem (Join-Path $DataDir "backups") -Filter "fleet_assets.before-update-*.db" -ErrorAction SilentlyContinue)) { throw "Installer update did not back up the existing user database." }
    @'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count >= 1, count
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
'@ | & $PythonExecutable - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "The update removed user accounts or damaged the database." }
    if (-not (Test-Path -LiteralPath (Join-Path $DataDir "secret.key"))) {
        throw "The update removed the session signing key."
    }

    Start-PackagedApp
    Assert-SplashContent
    Assert-SetupNotRequired
    Assert-SidebarInstitution
    Assert-LoginWorks -Username "admin" -Password $script:InitialAdminPassword
    @'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    row = db.execute("SELECT marker FROM installer_smoke_probe").fetchone()
    assert row == ("preserve-me-across-update",), row
    stamp = db.execute("SELECT version_num FROM alembic_version").fetchone()
    assert stamp == ("20261104_spare_request_general_need",), stamp
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
'@ | & $PythonExecutable - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "User data, schema migration, or SQLite integrity did not survive the update." }
    if (-not (Test-Path -LiteralPath $AttachmentPath) -or (Get-Content -LiteralPath $AttachmentPath -Raw) -ne "preserve-this-attachment") {
        throw "An existing user attachment did not survive the update."
    }
    if (-not (Get-ChildItem (Join-Path $DataDir "backups") -Filter "fleet_assets.before-upgrade-*.db" -ErrorAction SilentlyContinue)) {
        throw "Application startup did not make a verified database backup before migration."
    }

    Stop-PackagedApp
    Invoke-Uninstaller
    if (-not (Test-Path -LiteralPath $DatabasePath)) { throw "Uninstall removed the user database." }
    if (-not (Test-Path -LiteralPath $AttachmentPath)) { throw "Uninstall removed user attachments." }
    if (-not (Get-ChildItem (Join-Path $DataDir "backups") -Filter "fleet_assets.before-*.db" -ErrorAction SilentlyContinue)) {
        throw "Uninstall removed the database backups."
    }
    if (Test-Path -LiteralPath (Join-Path $InstallDir "Materiel.exe")) { throw "Uninstall left the application executable behind." }

    @'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert users == 0, f"users remained after uninstall: {users}"
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    row = db.execute("SELECT marker FROM installer_smoke_probe").fetchone()
    assert row == ("preserve-me-across-update",), row
    assert db.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0] == 1
'@ | & $PythonExecutable - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "Uninstall did not remove user accounts safely or damaged business data." }
    if (Test-Path -LiteralPath (Join-Path $DataDir "secret.key")) {
        throw "Uninstall left the session signing key behind."
    }
    $CleanupLog = Join-Path $DataDir "uninstall-auth-cleanup.log"
    if (-not (Test-Path -LiteralPath $CleanupLog)) {
        throw "Uninstall did not write the authentication cleanup log."
    }
    $CleanupContent = Get-Content -LiteralPath $CleanupLog -Raw
    if (-not $CleanupContent.Contains('"status": "ok"')) {
        throw "Uninstall authentication cleanup did not report success: $CleanupContent"
    }
    if ($CleanupContent -notmatch '"users_deleted": [1-9]') {
        throw "Uninstall authentication cleanup did not report a deleted account: $CleanupContent"
    }

    Invoke-Installer
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "Materiel.exe"))) { throw "Reinstall did not restore the application executable." }
    Start-PackagedApp
    Assert-SplashContent
    Assert-FirstRunSetupAvailable
    New-FirstRunAdmin -Username "admin-new" -Password $script:ReinstallAdminPassword
    Assert-LoginRejected -Username "admin" -Password $script:InitialAdminPassword
    Assert-LoginWorks -Username "admin-new" -Password $script:ReinstallAdminPassword
    @'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    users = db.execute("SELECT username, role FROM users ORDER BY id").fetchall()
    assert users == [("admin-new", "admin")], users
    row = db.execute("SELECT marker FROM installer_smoke_probe").fetchone()
    assert row == ("preserve-me-across-update",), row
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
'@ | & $PythonExecutable - $DatabasePath
    if ($LASTEXITCODE -ne 0) { throw "Reinstall did not create a fresh administrator or lost business data." }
    if (-not (Test-Path -LiteralPath $AttachmentPath)) { throw "Reinstall removed the preserved user attachment." }
    Stop-PackagedApp

    Write-Output "PASS: installed GUI EXE started without a console host and served /health on a fallback port."
    Write-Output "PASS: release welcome text, version and logo rendered from the installed application bundle."
    Write-Output "PASS: configured institution name rendered in the application sidebar."
    Write-Output "PASS: standard users cannot modify the installed branding, and user-data overrides are ignored."
    Write-Output "PASS: installer update and application migration preserved the database, backup, attachment and user accounts."
    Write-Output "PASS: uninstall removed users and the session signing key while preserving the database, business rows, uploads and backups."
    Write-Output "PASS: reinstall presented first-run setup, rejected old credentials, accepted the new administrator and kept business data."
    Write-Output "QA installation retained for inspection: $Root"
    Write-Output "Installer log: $LogPath"
}
finally {
    Stop-PackagedApp
    foreach ($Name in $OldEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $OldEnvironment[$Name], "Process")
    }
}
