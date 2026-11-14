<# 
.SYNOPSIS
    Safe bidirectional Git sync with GitHub for Materiel repository.
    
.DESCRIPTION
    This script performs a safe synchronization with the remote GitHub repository:
    1. Checks for uncommitted changes and stashes them safely
    2. Fetches latest changes from origin
    3. Attempts to merge remote changes (preserves history, no rebase)
    4. On conflict: stops, shows conflicting files, restores stash, exits
    5. If merge succeeds: pushes local commits to origin
    6. Restores any stashed uncommitted changes
    
.REQUIREMENTS
    - Git installed and in PATH
    - Repository at C:\Users\utilisateur\Desktop\Materiel
    - Remote named 'origin' configured
    - No reset --hard, no clean, no history rewriting
    
.USAGE
    .\sync-github.ps1
    
.NOTES
    - Stashed changes are restored even on error
    - Conflicts are reported but NOT auto-resolved
    - Script exits with non-zero code on conflict or error
#>

param(
    [string]$RepoPath = "C:\Users\utilisateur\Desktop\Materiel",
    [string]$BranchName = "stage3-maintenance-operations",
    [string]$RemoteName = "origin"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message"
}

function Write-ErrorLog {
    param([string]$Message)
    Write-Log $Message "ERROR"
}

function Write-WarningLog {
    param([string]$Message)
    Write-Log $Message "WARN"
}

function Write-SuccessLog {
    param([string]$Message)
    Write-Log $Message "SUCCESS"
}

# Track if we stashed changes
$stashed = $false
$stashMessage = "auto-sync-stash-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

try {
    Write-Log "Starting GitHub sync for Materiel repository"
    Write-Log "Repository: $RepoPath"
    Write-Log "Branch: $BranchName"
    Write-Log "Remote: $RemoteName"
    
    # Change to repo directory
    Set-Location -Path $RepoPath -ErrorAction Stop
    Write-Log "Changed to repository directory"
    
    # Verify we're in a git repo
    if (-not (Test-Path ".git")) {
        throw "Not a Git repository: $RepoPath"
    }
    
    # Verify current branch
    $currentBranch = git rev-parse --abbrev-ref HEAD
    if ($currentBranch -ne $BranchName) {
        Write-WarningLog "Current branch is '$currentBranch', expected '$BranchName'"
        # Continue anyway but warn
    }
    
    # Check for uncommitted changes (staged + unstaged)
    $statusOutput = git status --porcelain
    $hasUncommittedChanges = $statusOutput.Trim() -ne ""
    
    if ($hasUncommittedChanges) {
        Write-Log "Uncommitted changes detected, stashing them safely..."
        Write-Log "Changes:"
        $statusOutput | ForEach-Object { Write-Log "  $_" }
        
        # Stash with a descriptive message including untracked files
        git stash push --include-untracked --message $stashMessage
        $stashed = $true
        Write-SuccessLog "Changes stashed as: $stashMessage"
    } else {
        Write-Log "No uncommitted changes detected"
    }
    
    # Fetch latest from remote
    Write-Log "Fetching latest changes from $RemoteName..."
    git fetch $RemoteName
    Write-SuccessLog "Fetch completed"
    
    # Check if remote branch exists
    $remoteBranchExists = git ls-remote --heads $RemoteName $BranchName
    if (-not $remoteBranchExists) {
        throw "Remote branch '$RemoteName/$BranchName' does not exist"
    }
    
    # Check divergence
    $localCommits = git rev-list --count "$RemoteName/$BranchName..HEAD"
    $remoteCommits = git rev-list --count "HEAD..$RemoteName/$BranchName"
    
    Write-Log "Divergence: local ahead by $localCommits, behind by $remoteCommits"
    
    if ($remoteCommits -eq 0) {
        Write-Log "Already up to date with remote, nothing to merge"
    } else {
        Write-Log "Merging remote changes (preserving history, no rebase)..."
        
        # Try merge with no-commit first to detect conflicts early
        $mergeResult = git merge --no-commit --no-ff "$RemoteName/$BranchName" 2>&1
        $mergeExitCode = $LASTEXITCODE
        
        if ($mergeExitCode -ne 0) {
            # Check if it's a conflict
            if ($mergeResult -like "*CONFLICT*" -or $mergeResult -like "*conflict*") {
                Write-ErrorLog "MERGE CONFLICT DETECTED"
                Write-ErrorLog "The following files have conflicts:"
                
                # Show conflicted files
                $conflictedFiles = git diff --name-only --diff-filter=U
                $conflictedFiles | ForEach-Object { Write-ErrorLog "  $_" }
                
                Write-ErrorLog ""
                Write-ErrorLog "AUTOMATIC RESOLUTION IS DISABLED PER POLICY."
                Write-ErrorLog "Please resolve conflicts manually, then commit the merge."
                Write-ErrorLog "Your stashed changes are saved as: $stashMessage"
                
                # Abort the merge to leave working tree clean for manual resolution
                git merge --abort
                Write-Log "Merge aborted. Working tree restored to pre-merge state."
                
                exit 1
            } else {
                throw "Merge failed with unexpected error: $mergeResult"
            }
        }
        
        # Merge succeeded without conflicts, commit it
        git commit --no-edit -m "Merge branch '$BranchName' of $RemoteName into $BranchName"
        Write-SuccessLog "Merge committed successfully"
    }
    
    # Push local commits if any
    if ($localCommits -gt 0) {
        Write-Log "Pushing $localCommits local commit(s) to $RemoteName..."
        git push $RemoteName $BranchName
        Write-SuccessLog "Push completed successfully"
    } else {
        Write-Log "No local commits to push"
    }
    
    # Final status
    Write-Log "Sync completed successfully!"
    Write-Log "Final status:"
    git status -sb | ForEach-Object { Write-Log "  $_" }
    
}
catch {
    Write-ErrorLog "Sync failed: $_"
    throw
}
finally {
    # Always restore stashed changes if we stashed
    if ($stashed) {
        Write-Log "Restoring stashed changes..."
        try {
            git stash pop
            Write-SuccessLog "Stashed changes restored"
        }
        catch {
            Write-ErrorLog "Failed to restore stashed changes automatically!"
            Write-ErrorLog "Your changes are safe in stash: $stashMessage"
            Write-ErrorLog "Run 'git stash pop' manually to restore them."
            exit 1
        }
    }
}

exit 0