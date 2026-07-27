[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir,
    [Parameter(Mandatory = $true)]
    [string]$CurrentPath,
    [string]$PublicKey = "data\resource_index\.secrets\media-ed25519-public.pem",
    [string]$ReceiptDir = "data\resource_index\media_publish_receipts",
    [int]$MaxWorkers = 12
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WorkerConfig = Join-Path $PSScriptRoot "r2-production-upload-worker\wrangler.jsonc"
$WorkerName = "magnetgoogo-media-production-uploader"

if ($MaxWorkers -lt 1 -or $MaxWorkers -gt 16) {
    throw "MaxWorkers must be between 1 and 16 for the production data Worker bridge."
}

function Resolve-RepoPath([string]$Value) {
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Value))
}

function Wait-WorkerStatus(
    [string]$Url,
    [int[]]$ExpectedStatuses,
    [string]$BearerToken = ""
) {
    $LastStatus = 0
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        Start-Sleep -Seconds 3
        try {
            $Headers = @{}
            if (-not [string]::IsNullOrWhiteSpace($BearerToken)) {
                $Headers.Authorization = "Bearer $BearerToken"
            }
            $Response = Invoke-WebRequest `
                -Uri "$Url/health" `
                -Headers $Headers `
                -UseBasicParsing `
                -TimeoutSec 10
            $LastStatus = [int]$Response.StatusCode
        } catch {
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $LastStatus = [int]$_.Exception.Response.StatusCode
            } else {
                $LastStatus = 0
            }
        }
        if ($ExpectedStatuses -contains $LastStatus) {
            return $LastStatus
        }
    }
    return $LastStatus
}

$ReleaseDir = Resolve-RepoPath $ReleaseDir
$CurrentPath = Resolve-RepoPath $CurrentPath
$PublicKey = Resolve-RepoPath $PublicKey
$ReceiptDir = Resolve-RepoPath $ReceiptDir

$TokenBytes = New-Object byte[] 32
$Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $Rng.GetBytes($TokenBytes)
} finally {
    $Rng.Dispose()
}
$UploadToken = ([System.BitConverter]::ToString($TokenBytes)).Replace("-", "").ToLowerInvariant()
$env:R2_UPLOAD_WORKER_TOKEN = $UploadToken
$WorkerDeployed = $false
$DeleteFailed = $false

Push-Location $RepoRoot
try {
    $DeployOutput = @(& npx.cmd -y wrangler@4.114.0 deploy --config $WorkerConfig 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Production data uploader Worker deployment failed."
    }
    $WorkerDeployed = $true
    $DeployText = $DeployOutput -join "`n"
    $UrlMatch = [regex]::Match($DeployText, "https://[^\s]+\.workers\.dev")
    if (-not $UrlMatch.Success) {
        throw "Production data Worker URL was not present in Wrangler deployment output."
    }
    $WorkerUrl = $UrlMatch.Value.TrimEnd("/")
    Write-Host "Temporary production-data Worker URL: $WorkerUrl"

    $SecretVersionTag = "media-production-data-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $SecretVersionId = (& python -c "import os, re, subprocess, sys; p = subprocess.run(['npx.cmd', '-y', 'wrangler@4.114.0', 'versions', 'secret', 'put', 'UPLOAD_TOKEN', '--name', sys.argv[1], '--config', sys.argv[2], '--tag', sys.argv[3], '--message', 'temporary production media data publisher'], input=os.environ['R2_UPLOAD_WORKER_TOKEN'], text=True, encoding='utf-8', errors='replace', capture_output=True); m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', (p.stdout or '') + '\n' + (p.stderr or '')); sys.stdout.write(m.group(0) if m else ''); raise SystemExit(p.returncode if p.returncode else (0 if m else 2))" $WorkerName $WorkerConfig $SecretVersionTag).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($SecretVersionId)) {
        throw "Production data Worker secret version creation failed or returned no version ID."
    }
    & npx.cmd -y wrangler@4.114.0 versions deploy `
        --version-id $SecretVersionId `
        --percentage 100 `
        --name $WorkerName `
        --config $WorkerConfig `
        --yes | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Production data Worker secret version deployment failed."
    }

    $ReadyStatus = 0
    for ($Window = 1; $Window -le 2; $Window++) {
        $ReadyStatus = Wait-WorkerStatus -Url $WorkerUrl -ExpectedStatuses @(200) -BearerToken $UploadToken
        if ($ReadyStatus -eq 200) {
            break
        }
    }
    if ($ReadyStatus -ne 200) {
        throw "Production data Worker did not become ready within 120 seconds (last HTTP status $ReadyStatus)."
    }

    $BaseArguments = @(
        "-B", "-m", "magnet.resource_index.cli", "publish-media-r2-staging",
        "--release-dir", $ReleaseDir,
        "--current", $CurrentPath,
        "--public-key", $PublicKey,
        "--bucket", "magnetgoogo-media",
        "--prefix=",
        "--production-root",
        "--receipt-dir", $ReceiptDir,
        "--max-workers", $MaxWorkers,
        "--worker-bridge-url", $WorkerUrl,
        "--no-pointer-candidate",
        "--yes"
    )

    Write-Host "Publishing immutable media data to production R2 root..."
    & python @BaseArguments
    if ($LASTEXITCODE -ne 0) {
        throw "First production R2 data publication failed."
    }

    Write-Host "Repeating production data publication to prove complete reuse..."
    & python @BaseArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Second production R2 data publication/reuse verification failed."
    }

    Write-Host "Production R2 immutable data and staging pointer candidate are verified. current.json remains unpublished."
} finally {
    Remove-Item Env:R2_UPLOAD_WORKER_TOKEN -ErrorAction SilentlyContinue
    $UploadToken = $null
    [Array]::Clear($TokenBytes, 0, $TokenBytes.Length)
    if ($WorkerDeployed) {
        & npx.cmd -y wrangler@4.114.0 delete $WorkerName --config $WorkerConfig --force | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $DeleteFailed = $true
        }
    }
    Pop-Location
    if ($DeleteFailed) {
        throw "Temporary production data uploader Worker deletion failed; remove $WorkerName immediately."
    }
}
