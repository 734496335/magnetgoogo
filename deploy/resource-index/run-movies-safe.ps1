[CmdletBinding()]
param(
    [string]$Sources = "sixv,dytt8899,sixv-series,meijumi",
    [int]$Count = 0,
    [string]$VenvPath = "",
    [string]$OutputDir = "",
    [string]$Log = "",
    [string]$AggregateOutput = "",
    [string]$FormalAggregateOutput = "",
    [string]$MovieOutput = "",
    [string]$SeriesOutput = "",
    [string]$QuarantineOutput = "",
    [string]$QualityOutput = "",
    [string]$MovieBundleOutput = "",
    [string]$SeriesBundleOutput = "",
    [int]$MovieLimit = 100,
    [int]$SeriesLimit = 100,
    [double]$CoverDelaySeconds = 1.5
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
$FormalAggregateOutput = Resolve-RepoPath $FormalAggregateOutput "data\resource_index\media_latest_200_feed.json"
$MovieOutput = Resolve-RepoPath $MovieOutput "data\resource_index\movies_latest_100_feed.json"
$SeriesOutput = Resolve-RepoPath $SeriesOutput "data\resource_index\series_latest_100_feed.json"
$QuarantineOutput = Resolve-RepoPath $QuarantineOutput "data\resource_index\media_resource_quarantine.json"
$QualityOutput = Resolve-RepoPath $QualityOutput "data\resource_index\media_quality_report.json"
$MovieBundleOutput = Resolve-RepoPath $MovieBundleOutput "data\resource_index\movie_app_bundle"
$SeriesBundleOutput = Resolve-RepoPath $SeriesBundleOutput "data\resource_index\series_app_bundle"
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
$DefaultCounts = @{
    "sixv" = 100
    "dytt8899" = 250
    "sixv-series" = 100
    "meijumi" = 100
}
foreach ($Source in ($Sources -split ",")) {
    $Trimmed = $Source.Trim()
    if (-not [string]::IsNullOrWhiteSpace($Trimmed)) {
        $SourceList += $Trimmed
        $EffectiveSourceCount = if ($Count -gt 0) {
            $Count
        } elseif ($DefaultCounts.ContainsKey($Trimmed)) {
            $DefaultCounts[$Trimmed]
        } else {
            50
        }
        $Arguments += @("--source", $Trimmed, "--source-count", ("{0}={1}" -f $Trimmed, $EffectiveSourceCount))
    }
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
Push-Location $RepoRoot
try {
    & $PythonExe @Arguments
    $Code = $LASTEXITCODE

    $FeedArguments = @()
    $FeedCount = 0
    $AggregateSources = @("sixv", "dytt8899", "sixv-series", "meijumi")
    foreach ($Source in $AggregateSources) {
        $EffectiveCount = if ($Count -gt 0) {
            $Count
        } elseif ($DefaultCounts.ContainsKey($Source)) {
            $DefaultCounts[$Source]
        } else {
            50
        }
        $FeedPath = Join-Path $OutputDir ("{0}_latest_{1}_feed.json" -f $Source, $EffectiveCount)
        if (Test-Path $FeedPath) {
            $FeedArguments += @("--feed", $FeedPath)
            $FeedCount += 1
        }
    }
    if ($FeedCount -gt 0) {
        $PartialArguments = @(
            "-B", "-m", "magnet.resource_index.cli", "aggregate-media-feeds",
            "--output", $AggregateOutput,
            "--limit", "300"
        ) + $FeedArguments
        & $PythonExe @PartialArguments
        $PartialCode = $LASTEXITCODE
        if ($Code -eq 0 -and $PartialCode -ne 0) {
            $Code = $PartialCode
        }
        if ($PartialCode -eq 0) {
            Write-Host "Partial-compatible media feed ready: $AggregateOutput"
        }

        $StrictArguments = @(
            "-B", "-m", "magnet.resource_index.cli", "aggregate-media-feeds",
            "--output", $FormalAggregateOutput,
            "--movie-output", $MovieOutput,
            "--series-output", $SeriesOutput,
            "--quarantine-output", $QuarantineOutput,
            "--quality-output", $QualityOutput,
            "--movie-limit", $MovieLimit,
            "--series-limit", $SeriesLimit,
            "--strict-kind-limits",
            "--limit", ($MovieLimit + $SeriesLimit)
        ) + $FeedArguments
        & $PythonExe @StrictArguments
        $StrictCode = $LASTEXITCODE
        if ($StrictCode -eq 0) {
            Write-Host "Formal media feed ready: $FormalAggregateOutput"
            Write-Host "Movie catalog ready: $MovieOutput"
            Write-Host "Series catalog ready: $SeriesOutput"
            Write-Host "Resource quarantine ready: $QuarantineOutput"
            Write-Host "Quality report ready: $QualityOutput"

            & $PythonExe -B -m magnet.resource_index.cli build-media-app-bundle `
                --feed $AggregateOutput --output-dir $MovieBundleOutput `
                --content-kind movie --expected-count $MovieLimit `
                --delay $CoverDelaySeconds --yes
            $MovieBundleCode = $LASTEXITCODE
            & $PythonExe -B -m magnet.resource_index.cli build-media-app-bundle `
                --feed $AggregateOutput --output-dir $SeriesBundleOutput `
                --content-kind series --expected-count $SeriesLimit `
                --delay $CoverDelaySeconds --yes
            $SeriesBundleCode = $LASTEXITCODE
            if ($MovieBundleCode -eq 0) {
                & $PythonExe -B -m magnet.resource_index.cli audit-media-app-bundle `
                    --bundle-dir $MovieBundleOutput --content-kind movie --expected-count $MovieLimit
                $MovieAuditCode = $LASTEXITCODE
            } else {
                $MovieAuditCode = $MovieBundleCode
            }
            if ($SeriesBundleCode -eq 0) {
                & $PythonExe -B -m magnet.resource_index.cli audit-media-app-bundle `
                    --bundle-dir $SeriesBundleOutput --content-kind series --expected-count $SeriesLimit
                $SeriesAuditCode = $LASTEXITCODE
            } else {
                $SeriesAuditCode = $SeriesBundleCode
            }
            foreach ($BundleCode in @($MovieBundleCode, $SeriesBundleCode, $MovieAuditCode, $SeriesAuditCode)) {
                if ($Code -eq 0 -and $BundleCode -ne 0) {
                    $Code = $BundleCode
                }
            }
            if ($MovieAuditCode -eq 0 -and $SeriesAuditCode -eq 0) {
                Write-Host "Movie offline bundle ready: $MovieBundleOutput"
                Write-Host "Series offline bundle ready: $SeriesBundleOutput"
            }
        } else {
            Write-Warning "Formal movie/series quotas are not satisfied; previous complete catalogs were not overwritten."
        }
    }
} finally {
    Pop-Location
}
exit $Code
