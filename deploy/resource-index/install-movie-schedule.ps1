[CmdletBinding()]
param(
    [string]$TaskName = "MagnetGoogo Movie Sources Safe Crawl",
    [ValidateRange(6, 24)]
    [int]$IntervalHours = 6,
    [string]$Sources = "sixv,dytt8899,sixv-series,meijumi",
    [string]$VenvPath = "",
    [string]$OutputDir = "",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Resolve-RepoPath([string]$Value, [string]$DefaultRelative) {
    $Selected = if ([string]::IsNullOrWhiteSpace($Value)) { $DefaultRelative } else { $Value }
    if ([System.IO.Path]::IsPathRooted($Selected)) {
        return [System.IO.Path]::GetFullPath($Selected)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Selected))
}

if ($Remove) {
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $Existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task: $TaskName"
    } else {
        Write-Host "Scheduled task does not exist: $TaskName"
    }
    exit 0
}

$VenvPath = Resolve-RepoPath $VenvPath ".venv-resource-index"
$OutputDir = Resolve-RepoPath $OutputDir "data\resource_index"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$Runner = Join-Path $PSScriptRoot "run-movies-safe.ps1"
if (-not (Test-Path $PythonExe)) {
    throw "Runtime is not installed. Run deploy\resource-index\setup.bat first."
}
if (-not (Test-Path $Runner)) {
    throw "Safe movie runner not found: $Runner"
}

$PowerShellArguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $Runner),
    "-Sources", ('"{0}"' -f $Sources),
    "-VenvPath", ('"{0}"' -f $VenvPath),
    "-OutputDir", ('"{0}"' -f $OutputDir)
) -join " "

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $PowerShellArguments `
    -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours)
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Low-frequency, resumable movie-source checks with per-source budgets."
Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null

Write-Host "Scheduled task installed: $TaskName"
Write-Host "Trigger interval: every $IntervalHours hours"
Write-Host "Sources: $Sources"
Write-Host "The crawler still enforces its internal 12-hour source gate and daily budgets."
