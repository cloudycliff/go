# Registers (or replaces) the daily Windows task that runs scripts\update.cmd at 2:00.
#   powershell -ExecutionPolicy Bypass -File scripts\schedule.ps1
# Remove it with: Unregister-ScheduledTask -TaskName go-review-update
#
# - Runs as the current user while logged on (no password stored; git push uses this user's credentials).
# - Wakes the computer from sleep for it, and runs at the next start if the computer was off at 2:00.
# - Stopped after 3 hours, so a hung run cannot block the next day.

param([string]$At = "02:00")

$name = "go-review-update"
$script = Join-Path $PSScriptRoot "update.cmd"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$script`"" -WorkingDirectory (Split-Path $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "go-review: fetch new Fox games, analyse with KataGo and publish the review site" -Force | Out-Null
Get-ScheduledTask -TaskName $name | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
