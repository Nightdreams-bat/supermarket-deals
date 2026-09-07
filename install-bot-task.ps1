# Registers the "SupermarketDealsBot" scheduled task: runs bot.py at logon and
# keeps it alive (long-polling filter bot for the daily digest, see ADR-006).
# Uninstall:
#   Unregister-ScheduledTask -TaskName "SupermarketDealsBot" -Confirm:$false

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$botScript = Join-Path $scriptDir "bot.py"
$python = (Get-Command python).Source

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$botScript`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName "SupermarketDealsBot" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Interactive store-filter bot for the deals digest" -Force | Out-Null

Write-Host "Registered scheduled task 'SupermarketDealsBot'"
Write-Host "  python:  $python"
Write-Host "  script:  $botScript"
Write-Host "  when:    at logon, restarts up to 3x (1 min apart); down while the PC is off"
