$task = Get-ScheduledTask -TaskName 'Materiel-GitHub-Sync'
Write-Host "=== Actions ==="
$task.Actions | Format-List *
Write-Host "=== Triggers ==="
$task.Triggers | Format-List *
Write-Host "=== Principal ==="
$task.Principal | Format-List *
Write-Host "=== Settings ==="
$task.Settings | Format-List *