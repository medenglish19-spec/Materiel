<# 
.SYNOPSIS
    Wrapper for sync-github.ps1 that logs to file for Task Scheduler execution.

.DESCRIPTION
    Runs the sync script and writes output to a log file in the repository's logs directory.
    Prevents multiple concurrent executions using a lock file.
#>

param(
    [string]$RepoPath = "C:\Users\utilisateur\Desktop\Materiel",
    [string]$LogDir = "C:\Users\utilisateur\Desktop\Materiel\logs",
    [string]$ScriptPath = "C:\Users\utilisateur\Desktop\Materiel\sync-github.ps1"
)

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$logFile = Join-Path $LogDir "github-sync-$(Get-Date -Format 'yyyyMMdd').log"
$lockFile = Join-Path $RepoPath ".sync-lock"

function Write-LogFile {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $logFile -Value $entry
    Write-Host $entry
}

# Check for existing lock (prevent concurrent runs)
if (Test-Path $lockFile) {
    $lockTime = (Get-Item $lockFile).LastWriteTime
    $lockAge = (Get-Date) - $lockTime
    # If lock is older than 10 minutes, assume stale and remove
    if ($lockAge.TotalMinutes -gt 10) {
        Write-LogFile "Removing stale lock file (age: $($lockAge.TotalMinutes) minutes)" "WARN"
        Remove-Item -Path $lockFile -Force
    } else {
        Write-LogFile "Another sync is already running (lock file exists, age: $($lockAge.TotalMinutes) minutes). Exiting." "WARN"
        exit 0
    }
}

# Create lock file
try {
    New-Item -ItemType File -Path $lockFile -Force | Out-Null
    Write-LogFile "=== GitHub Sync Started (PID: $PID) ===" "INFO"
    Write-LogFile "Repository: $RepoPath"
    Write-LogFile "Script: $ScriptPath"

    # Run the sync script
    $result = & powershell -ExecutionPolicy Bypass -File $ScriptPath 2>&1
    $exitCode = $LASTEXITCODE

    # Log all output
    $result | ForEach-Object { Write-LogFile $_ }

    if ($exitCode -eq 0) {
        Write-LogFile "=== GitHub Sync Completed Successfully ===" "SUCCESS"
    } elseif ($exitCode -eq 1) {
        Write-LogFile "=== GitHub Sync Stopped: Conflict or Error (exit code 1) ===" "WARN"
    } else {
        Write-LogFile "=== GitHub Sync Failed with exit code $exitCode ===" "ERROR"
    }

    exit $exitCode
}
catch {
    Write-LogFile "=== GitHub Sync Failed with Exception: $_ ===" "ERROR"
    exit 1
}
finally {
    # Remove lock file
    if (Test-Path $lockFile) {
        Remove-Item -Path $lockFile -Force -ErrorAction SilentlyContinue
    }
}