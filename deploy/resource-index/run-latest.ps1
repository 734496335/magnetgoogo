[CmdletBinding()]
param(
    [ValidateSet("javbus", "sixv", "dytt8899")]
    [string]$Source = "javbus",
    [int]$Count = 0,
    [int]$BatchSize = 5,
    [int]$MaxAttempts = 3,
    [double]$DelaySeconds = 10.0,
    [int]$MaxBatches = 0,
    [switch]$Refresh,
    [switch]$ReparseIncomplete,
    [string]$VenvPath = "",
    [string]$OutputDir = "",
    [string]$Database = ""
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

$VenvPath = Resolve-RepoPath $VenvPath ".venv-resource-index"
$OutputDir = Resolve-RepoPath $OutputDir "data\resource_index"
if (-not [string]::IsNullOrWhiteSpace($Database)) {
    $Database = Resolve-RepoPath $Database ""
}

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Runtime is not installed. Run deploy\resource-index\setup.bat first."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"

$EffectiveCount = if ($Count -gt 0) {
    $Count
} elseif ($Source -eq "sixv") {
    50
} elseif ($Source -eq "dytt8899") {
    25
} else {
    100
}

$Arguments = @(
    "-B",
    "-m", "magnet.resource_index.cli",
    "crawl-latest",
    "--source", $Source,
    "--output-dir", $OutputDir,
    "--batch-size", $BatchSize,
    "--max-attempts", $MaxAttempts,
    "--delay", $DelaySeconds,
    "--batch-max-requests", (7 + 2 * $BatchSize),
    "--yes"
)
if ($Count -gt 0) {
    $Arguments += @("--count", $Count)
}
if (-not [string]::IsNullOrWhiteSpace($Database)) {
    $Arguments += @("--db", $Database)
}
if ($MaxBatches -gt 0) {
    $Arguments += @("--max-batches", $MaxBatches)
}
if ($Refresh) {
    $Arguments += "--refresh"
}
if ($ReparseIncomplete) {
    $Arguments += "--reparse-incomplete"
}

Push-Location $RepoRoot
try {
    & $PythonExe @Arguments
    $Code = $LASTEXITCODE
    if ($Code -eq 0 -and $Source -eq "sixv") {
        $EffectiveDatabase = if ([string]::IsNullOrWhiteSpace($Database)) {
            Join-Path $OutputDir ("sixv_latest_{0}.db" -f $EffectiveCount)
        } else {
            $Database
        }
        $FeedPath = Join-Path $OutputDir ("sixv_latest_{0}_feed.json" -f $EffectiveCount)
        $AppBundlePath = Join-Path $OutputDir "sixv_app_bundle"

        & $PythonExe -B -m magnet.resource_index.cli sync-movie-covers `
            --source sixv --db $EffectiveDatabase --delay $DelaySeconds --yes
        $CoverCode = $LASTEXITCODE
        if ($CoverCode -ne 0) {
            throw "Movie cover sync failed with exit code $CoverCode."
        }

        & $PythonExe -B -m magnet.resource_index.cli export-movie-app-bundle `
            --db $EffectiveDatabase --feed $FeedPath --output-dir $AppBundlePath
        $BundleCode = $LASTEXITCODE
        if ($BundleCode -ne 0) {
            throw "Movie App bundle export failed with exit code $BundleCode."
        }
        Write-Host "Movie App bundle ready: $AppBundlePath"
    }
} finally {
    Pop-Location
}

if ($Code -eq 2) {
    Write-Host "The durable job is incomplete. Run the same command again to resume."
}
if ($Code -eq 130) {
    Write-Host "The job was paused safely. Run the same command again to resume."
}
exit $Code
