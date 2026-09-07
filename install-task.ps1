# Registers the "SupermarketDeals" scheduled task: runs run.py daily at 08:00.
# Uninstall:
#   Unregister-ScheduledTask -TaskName "SupermarketDeals" -Confirm:$false

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$runScript = Join-Path $scriptDir "run.py"
$python = (Get-Command python).Source

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$runScript`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -Daily -At 08:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "SupermarketDeals" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Daily Linz supermarket deals digest" -Force | Out-Null

Write-Host "Registered scheduled task 'SupermarketDeals'"
Write-Host "  python:  $python"
Write-Host "  script:  $runScript"
Write-Host "  when:    daily at 08:00 (runs only while the PC is on)"
