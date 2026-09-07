# Registers the "SupermarketDeals" scheduled task: runs run.py daily at 08:00.
# Uninstall:
#   Unregister-ScheduledTask -TaskName "SupermarketDeals" -Confirm:$false

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$runScript = Join-Path $scriptDir "run.py"

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

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$runScript`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -Daily -At 08:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "SupermarketDeals" -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Daily Linz supermarket deals digest" -Force | Out-Null

Write-Host "Registered scheduled task 'SupermarketDeals'"
Write-Host "  python:  $python"
Write-Host "  script:  $runScript"
Write-Host "  when:    daily at 08:00 (runs only while the PC is on)"
