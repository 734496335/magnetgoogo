[CmdletBinding()]
param(
    [int]$PointerRevision = 1,
    [string]$MinAppVersion = "0.2.1",
    [int]$PageSize = 50,
    [int]$MaxObjectBytes = 524288,
    [string]$VenvPath = "",
    [string]$MovieFeed = "",
    [string]$SeriesFeed = "",
    [string]$MovieCoverBundle = "",
    [string]$SeriesCoverBundle = "",
    [string]$OutputDir = "",
    [string]$PrivateKey = "",
    [string]$PublicKey = "",
    [string]$PreviousManifest = "",
    [string]$AllowRegression = "",
    [switch]$VerifyOnly,
    [string]$ReleaseDir = "",
    [string]$CurrentPath = ""
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

if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $StandardVenv = Resolve-RepoPath "" ".venv-resource-index"
    $PortableVenv = Resolve-RepoPath "" "data\resource_index\.one-click-venv"
    if (Test-Path (Join-Path $StandardVenv "Scripts\python.exe")) {
        $VenvPath = $StandardVenv
    } elseif (Test-Path (Join-Path $PortableVenv "Scripts\python.exe")) {
        $VenvPath = $PortableVenv
    } else {
        $VenvPath = $StandardVenv
    }
} else {
    $VenvPath = Resolve-RepoPath $VenvPath ".venv-resource-index"
}
$MovieFeed = Resolve-RepoPath $MovieFeed "data\resource_index\movies_latest_100_feed.json"
$SeriesFeed = Resolve-RepoPath $SeriesFeed "data\resource_index\series_latest_100_feed.json"
$MovieCoverBundle = Resolve-RepoPath $MovieCoverBundle "data\resource_index\movie_app_bundle"
$SeriesCoverBundle = Resolve-RepoPath $SeriesCoverBundle "data\resource_index\series_app_bundle"
$OutputDir = Resolve-RepoPath $OutputDir "data\resource_index\media_releases"
$PrivateKey = Resolve-RepoPath $PrivateKey "data\resource_index\.secrets\media-ed25519-private.pem"
$PublicKey = Resolve-RepoPath $PublicKey "data\resource_index\.secrets\media-ed25519-public.pem"
if (-not [string]::IsNullOrWhiteSpace($PreviousManifest)) {
    $PreviousManifest = Resolve-RepoPath $PreviousManifest ""
}
if (-not [string]::IsNullOrWhiteSpace($ReleaseDir)) {
    $ReleaseDir = Resolve-RepoPath $ReleaseDir ""
}
if (-not [string]::IsNullOrWhiteSpace($CurrentPath)) {
    $CurrentPath = Resolve-RepoPath $CurrentPath ""
}

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Runtime is not installed. Run deploy\resource-index\setup.bat first."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"

& $PythonExe -c "from importlib.metadata import version; major=int(version('cryptography').split('.')[0]); raise SystemExit(0 if 45 <= major < 49 else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Upgrading the portable runtime for signed media releases..."
    & $PythonExe -m pip install `
        --disable-pip-version-check `
        --only-binary=:all: `
        -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Media release dependency installation failed."
    }
}

Push-Location $RepoRoot
try {
    if ($VerifyOnly) {
        if ([string]::IsNullOrWhiteSpace($ReleaseDir) -or [string]::IsNullOrWhiteSpace($CurrentPath)) {
            throw "-VerifyOnly requires both -ReleaseDir and -CurrentPath."
        }
        & $PythonExe -B -m magnet.resource_index.cli verify-media-release `
            --release-dir $ReleaseDir --current $CurrentPath --public-key $PublicKey
        exit $LASTEXITCODE
    }

    Write-Host "Checking the local Ed25519 media signing keypair..."
    & $PythonExe -B -m magnet.resource_index.cli init-media-signing-key `
        --private-key $PrivateKey --public-key $PublicKey
    if ($LASTEXITCODE -ne 0) {
        throw "Media signing key initialization failed with exit code $LASTEXITCODE."
    }

    $Arguments = @(
        "-B",
        "-m", "magnet.resource_index.cli",
        "build-media-release",
        "--movie-feed", $MovieFeed,
        "--series-feed", $SeriesFeed,
        "--movie-cover-bundle", $MovieCoverBundle,
        "--series-cover-bundle", $SeriesCoverBundle,
        "--output-dir", $OutputDir,
        "--private-key", $PrivateKey,
        "--public-key", $PublicKey,
        "--pointer-revision", $PointerRevision,
        "--min-app-version", $MinAppVersion,
        "--page-size", $PageSize,
        "--max-object-bytes", $MaxObjectBytes
    )
    if (-not [string]::IsNullOrWhiteSpace($PreviousManifest)) {
        $Arguments += @("--previous-manifest", $PreviousManifest)
    }
    if (-not [string]::IsNullOrWhiteSpace($AllowRegression)) {
        $Arguments += @("--allow-regression", $AllowRegression)
    }

    & $PythonExe @Arguments
    $Code = $LASTEXITCODE
    if ($Code -eq 0) {
        Write-Host "Local signed media release is ready. No network endpoint was modified."
    }
    exit $Code
} finally {
    Pop-Location
}
