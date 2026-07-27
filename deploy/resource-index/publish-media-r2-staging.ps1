[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir,
    [Parameter(Mandatory = $true)]
    [string]$CurrentPath,
    [string]$Bucket = "magnetgoogo-media-m2-test",
    [string]$Prefix = "m2-test",
    [string]$PublicKey = "",
    [string]$ReceiptDir = "",
    [int]$MaxWorkers = 8,
    [string]$VenvPath = "",
    [switch]$ShallowVerify,
    [switch]$NoPointerCandidate
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

if (-not $Prefix.StartsWith("m2-test")) {
    throw "M2 staging prefix must begin with m2-test."
}
if ($MaxWorkers -lt 1 -or $MaxWorkers -gt 32) {
    throw "MaxWorkers must be between 1 and 32."
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

$ReleaseDir = Resolve-RepoPath $ReleaseDir ""
$CurrentPath = Resolve-RepoPath $CurrentPath ""
$PublicKey = Resolve-RepoPath $PublicKey "data\resource_index\.secrets\media-ed25519-public.pem"
$ReceiptDir = Resolve-RepoPath $ReceiptDir "data\resource_index\media_publish_receipts"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Runtime is not installed. Run deploy\resource-index\setup.bat first."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"

& $PythonExe -c "from importlib.metadata import version; major,minor=map(int,version('boto3').split('.')[:2]); raise SystemExit(0 if (major,minor) >= (1,42) else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Upgrading the portable runtime for R2 publishing..."
    & $PythonExe -m pip install `
        --disable-pip-version-check `
        --only-binary=:all: `
        -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "R2 publishing dependency installation failed."
    }
}

$HasEndpoint = -not [string]::IsNullOrWhiteSpace($env:R2_ENDPOINT_URL) -or `
    -not [string]::IsNullOrWhiteSpace($env:AWS_ENDPOINT_URL) -or `
    -not [string]::IsNullOrWhiteSpace($env:R2_ACCOUNT_ID)
$HasAccessId = -not [string]::IsNullOrWhiteSpace($env:R2_ACCESS_KEY_ID) -or `
    -not [string]::IsNullOrWhiteSpace($env:AWS_ACCESS_KEY_ID)
$HasAccessSecret = -not [string]::IsNullOrWhiteSpace($env:R2_SECRET_ACCESS_KEY) -or `
    -not [string]::IsNullOrWhiteSpace($env:AWS_SECRET_ACCESS_KEY)
if (-not $HasEndpoint -or -not $HasAccessId -or -not $HasAccessSecret) {
    throw "R2 S3 environment is incomplete. Set endpoint/account and scoped access credentials; values are never passed on the command line."
}

$Arguments = @(
    "-B",
    "-m", "magnet.resource_index.cli",
    "publish-media-r2-staging",
    "--release-dir", $ReleaseDir,
    "--current", $CurrentPath,
    "--public-key", $PublicKey,
    "--bucket", $Bucket,
    "--prefix", $Prefix,
    "--receipt-dir", $ReceiptDir,
    "--max-workers", $MaxWorkers,
    "--yes"
)
if ($ShallowVerify) {
    $Arguments += "--shallow-verify"
}
if ($NoPointerCandidate) {
    $Arguments += "--no-pointer-candidate"
}

Push-Location $RepoRoot
try {
    & $PythonExe @Arguments
    $Code = $LASTEXITCODE
    if ($Code -eq 0) {
        Write-Host "R2 M2 staging upload verified. Production v1/current.json was not modified."
    }
    exit $Code
} finally {
    Pop-Location
}
