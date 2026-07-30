[CmdletBinding()]
param(
    [switch]$Refresh,
    [string]$VenvPath = "",
    [string]$OutputDir = "",
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

function Resolve-SourceDatabase(
    [string]$Source,
    [int]$Count,
    [int]$LegacyCount,
    [string]$Root
) {
    $Exact = Join-Path $Root ("{0}_latest_{1}.db" -f $Source, $Count)
    $Arguments = @(
        "-B", "-m", "magnet.resource_index.cli", "select-latest-database",
        "--source", $Source,
        "--count", $Count,
        "--candidate", $Exact,
        "--path-only"
    )
    if ($LegacyCount -gt 0) {
        $Legacy = Join-Path $Root ("{0}_latest_{1}.db" -f $Source, $LegacyCount)
        $Arguments += @("--candidate", $Legacy)
    }
    $Selected = (& $PythonExe @Arguments | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Selected)) {
        throw ("Unable to select a durable database for {0} target {1}." -f $Source, $Count)
    }
    $Resolved = [System.IO.Path]::GetFullPath($Selected.Trim())
    Write-Host ("Selected durable database for {0}: {1}" -f $Source, $Resolved)
    return $Resolved
}

$VenvPath = Resolve-RepoPath $VenvPath ".venv-resource-index"
$OutputDir = Resolve-RepoPath $OutputDir "data\resource_index"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Resource Index runtime is missing; installing it now."
    & (Join-Path $PSScriptRoot "setup.ps1") `
        -Source sixv -Count 100 -VenvPath $VenvPath -OutputDir $OutputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Resource Index runtime setup failed."
    }
}
if (-not (Test-Path $PythonExe)) {
    throw "Runtime Python not found after setup: $PythonExe"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"

$Sources = @(
    @{
        Source = "sixv"; Count = 100; LegacyCount = 50; Delay = 10.0;
        SnapshotRequests = 12; BatchRequests = 12; ListingPages = 4
    },
    @{
        Source = "dytt8899"; Count = 250; LegacyCount = 25; Delay = 15.0;
        SnapshotRequests = 12; BatchRequests = 12; ListingPages = 10
    },
    @{
        Source = "sixv-series"; Count = 100; LegacyCount = 0; Delay = 10.0;
        SnapshotRequests = 8; BatchRequests = 12; ListingPages = 8
    },
    @{
        Source = "meijumi"; Count = 100; LegacyCount = 50; Delay = 12.0;
        SnapshotRequests = 2; BatchRequests = 12; ListingPages = 1
    }
)

$MovieOutput = Join-Path $OutputDir "movies_latest_100_feed.json"
$SeriesOutput = Join-Path $OutputDir "series_latest_100_feed.json"
$MediaOutput = Join-Path $OutputDir "media_latest_200_feed.json"
$CompatibleOutput = Join-Path $OutputDir "media_latest_feed.json"
$QuarantineOutput = Join-Path $OutputDir "media_resource_quarantine.json"
$QualityOutput = Join-Path $OutputDir "media_quality_report.json"
$MovieBundle = Join-Path $OutputDir "movie_app_bundle"
$SeriesBundle = Join-Path $OutputDir "series_app_bundle"

Push-Location $RepoRoot
try {
    foreach ($Spec in $Sources) {
        $Source = [string]$Spec.Source
        $Count = [int]$Spec.Count
        $Database = Resolve-SourceDatabase `
            -Source $Source -Count $Count -LegacyCount ([int]$Spec.LegacyCount) -Root $OutputDir
        $Arguments = @(
            "-B", "-m", "magnet.resource_index.cli", "crawl-latest",
            "--source", $Source,
            "--count", $Count,
            "--output-dir", $OutputDir,
            "--db", $Database,
            "--batch-size", "5",
            "--max-attempts", "3",
            "--delay", ([double]$Spec.Delay),
            "--snapshot-max-requests", ([int]$Spec.SnapshotRequests),
            "--batch-max-requests", ([int]$Spec.BatchRequests),
            "--max-listing-pages", ([int]$Spec.ListingPages),
            "--log", (Join-Path $OutputDir ("{0}_latest_{1}.log" -f $Source, $Count)),
            "--yes"
        )
        if ($Refresh) {
            $Arguments += "--refresh"
        }
        Write-Host ("Running {0} latest {1}..." -f $Source, $Count)
        & $PythonExe @Arguments
        $SourceCode = $LASTEXITCODE
        if ($SourceCode -eq 2) {
            throw ("{0} stopped in a resumable state. Run this same one-click command again; do not delete its database or snapshot." -f $Source)
        }
        if ($SourceCode -ne 0) {
            throw ("{0} failed with exit code {1}. Existing completed data was preserved." -f $Source, $SourceCode)
        }
    }

    $FeedArguments = @(
        "--feed", (Join-Path $OutputDir "sixv_latest_100_feed.json"),
        "--feed", (Join-Path $OutputDir "dytt8899_latest_250_feed.json"),
        "--feed", (Join-Path $OutputDir "sixv-series_latest_100_feed.json"),
        "--feed", (Join-Path $OutputDir "meijumi_latest_100_feed.json")
    )

    & $PythonExe -B -m magnet.resource_index.cli aggregate-media-feeds `
        @FeedArguments `
        --output $CompatibleOutput `
        --limit 300
    if ($LASTEXITCODE -ne 0) {
        throw "Compatible media Feed aggregation failed."
    }

    & $PythonExe -B -m magnet.resource_index.cli aggregate-media-feeds `
        @FeedArguments `
        --output $MediaOutput `
        --movie-output $MovieOutput `
        --series-output $SeriesOutput `
        --quarantine-output $QuarantineOutput `
        --quality-output $QualityOutput `
        --movie-limit 100 `
        --series-limit 100 `
        --strict-kind-limits `
        --limit 200
    if ($LASTEXITCODE -ne 0) {
        throw "Strict movie 100 / series 100 aggregation or quality gate failed."
    }

    & $PythonExe -B -m magnet.resource_index.cli build-media-app-bundle `
        --feed $CompatibleOutput --output-dir $MovieBundle `
        --content-kind movie --expected-count 100 `
        --delay $CoverDelaySeconds --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Movie offline bundle build failed."
    }

    & $PythonExe -B -m magnet.resource_index.cli build-media-app-bundle `
        --feed $CompatibleOutput --output-dir $SeriesBundle `
        --content-kind series --expected-count 100 `
        --delay $CoverDelaySeconds --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Series offline bundle build failed."
    }

    & $PythonExe -B -m magnet.resource_index.cli audit-media-app-bundle `
        --bundle-dir $MovieBundle --content-kind movie --expected-count 100
    if ($LASTEXITCODE -ne 0) {
        throw "Movie offline bundle audit failed."
    }

    & $PythonExe -B -m magnet.resource_index.cli audit-media-app-bundle `
        --bundle-dir $SeriesBundle --content-kind series --expected-count 100
    if ($LASTEXITCODE -ne 0) {
        throw "Series offline bundle audit failed."
    }
} finally {
    Pop-Location
}

Write-Host "Offline media data is ready. No LLM was used in the runtime path."
Write-Host "Movie bundle: $MovieBundle"
Write-Host "Series bundle: $SeriesBundle"
Write-Host "Quality report: $QualityOutput"
Write-Host "Quarantine: $QuarantineOutput"
exit 0
