# Create Windows Task Scheduler task for Materiel GitHub sync
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -File C:\Users\utilisateur\Desktop\Materiel\sync-github-wrapper.ps1' `
    -WorkingDirectory 'C:\Users\utilisateur\Desktop\Materiel'

$trigger = New-ScheduledTaskTrigger -AtLogOn -User 'utilisateur'

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId 'utilisateur' `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName 'Materiel-GitHub-Sync' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Sync Materiel repository with GitHub at user logon' `
    -Force

Write-Host "Task 'Materiel-GitHub-Sync' created successfully."