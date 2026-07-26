[CmdletBinding()]
param(
    [string]$Sources = "sixv,dytt8899,sixv-series,meijumi",
    [int]$Count = 0,
    [string]$VenvPath = "",
    [string]$OutputDir = "",
    [string]$Log = "",
    [string]$AggregateOutput = ""
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
$Log = Resolve-RepoPath $Log "data\resource_index\movie_sources_safe.log"
$AggregateOutput = Resolve-RepoPath $AggregateOutput "data\resource_index\media_latest_feed.json"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Runtime is not installed. Run deploy\resource-index\setup.bat first."
}

$Arguments = @(
    "-B", "-m", "magnet.resource_index.cli", "crawl-movies-safe",
    "--output-dir", $OutputDir,
    "--log", $Log,
    "--yes"
)
$SourceList = @()
foreach ($Source in ($Sources -split ",")) {
    $Trimmed = $Source.Trim()
    if (-not [string]::IsNullOrWhiteSpace($Trimmed)) {
        $SourceList += $Trimmed
        $Arguments += @("--source", $Trimmed)
    }
}
if ($Count -gt 0) {
    $Arguments += @("--count", $Count)
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
Push-Location $RepoRoot
try {
    & $PythonExe @Arguments
    $Code = $LASTEXITCODE

    $AggregateArguments = @(
        "-B", "-m", "magnet.resource_index.cli", "aggregate-media-feeds",
        "--output", $AggregateOutput,
        "--limit", "300"
    )
    $FeedCount = 0
    $AggregateSources = @("sixv", "dytt8899", "sixv-series", "meijumi")
    foreach ($Source in $AggregateSources) {
        $EffectiveCount = if ($Count -gt 0) {
            $Count
        } elseif ($Source -eq "sixv") {
            50
        } elseif ($Source -eq "dytt8899") {
            25
        } elseif ($Source -eq "sixv-series") {
            50
        } elseif ($Source -eq "meijumi") {
            50
        } else {
            50
        }
        $FeedPath = Join-Path $OutputDir ("{0}_latest_{1}_feed.json" -f $Source, $EffectiveCount)
        if (Test-Path $FeedPath) {
            $AggregateArguments += @("--feed", $FeedPath)
            $FeedCount += 1
        }
    }
    if ($FeedCount -gt 0) {
        & $PythonExe @AggregateArguments
        $AggregateCode = $LASTEXITCODE
        if ($Code -eq 0 -and $AggregateCode -ne 0) {
            $Code = $AggregateCode
        }
        if ($AggregateCode -eq 0) {
            Write-Host "Aggregated media feed ready: $AggregateOutput"
        }
    }
} finally {
    Pop-Location
}
exit $Code
