# Registers the "SupermarketDealsBot" scheduled task: runs bot.py at logon and
# keeps it alive (long-polling filter bot for the daily digest, see ADR-006).
# Uninstall:
#   Unregister-ScheduledTask -TaskName "SupermarketDealsBot" -Confirm:$false

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$botScript = Join-Path $scriptDir "bot.py"

function Resolve-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch 'WindowsApps|System32' } |
        Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    throw "no usable python.exe found - install Python or edit this script"
}

$python = Resolve-Python
$me = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$botScript`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $me
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "SupermarketDealsBot" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Interactive store-filter bot for the deals digest" -Force | Out-Null

Write-Host "Registered scheduled task 'SupermarketDealsBot'"
Write-Host "  python:  $python"
Write-Host "  script:  $botScript"
Write-Host "  when:    at logon, restarts up to 3x (1 min apart); down while the PC is off"
