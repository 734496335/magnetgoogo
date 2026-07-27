[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir,
    [Parameter(Mandatory = $true)]
    [string]$CurrentPath,
    [string]$Prefix = "m2-test/release-r4-published",
    [string]$PublicKey = "data\resource_index\.secrets\media-ed25519-public.pem",
    [string]$ReceiptDir = "data\resource_index\media_publish_receipts",
    [int]$MaxWorkers = 8
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WorkerConfig = Join-Path $PSScriptRoot "r2-upload-worker\wrangler.jsonc"
$WorkerName = "magnetgoogo-media-m2-uploader"

if (-not $Prefix.StartsWith("m2-test/")) {
    throw "OAuth bridge prefix must remain under m2-test/."
}
if ($MaxWorkers -lt 1 -or $MaxWorkers -gt 16) {
    throw "MaxWorkers must be between 1 and 16 for the temporary Worker bridge."
}

function Resolve-RepoPath([string]$Value) {
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Value))
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

Push-Location $RepoRoot
try {
    $DeployOutput = @(& npx.cmd -y wrangler@4.114.0 deploy --config $WorkerConfig 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Temporary R2 uploader Worker deployment failed."
    }
    $WorkerDeployed = $true
    $DeployText = $DeployOutput -join "`n"
    $UrlMatch = [regex]::Match($DeployText, "https://[^\s]+\.workers\.dev")
    if (-not $UrlMatch.Success) {
        throw "Temporary Worker URL was not present in Wrangler deployment output."
    }
    $WorkerUrl = $UrlMatch.Value.TrimEnd("/")
    Write-Host "Temporary Worker URL: $WorkerUrl"

    $RouteReady = $false
    $LastRouteStatus = 0
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        Start-Sleep -Seconds 3
        try {
            Invoke-WebRequest -Uri "$WorkerUrl/health" -UseBasicParsing -TimeoutSec 10 | Out-Null
            $LastRouteStatus = 200
        } catch {
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $LastRouteStatus = [int]$_.Exception.Response.StatusCode
            } else {
                $LastRouteStatus = 0
            }
        }
        if ($LastRouteStatus -eq 401) {
            $RouteReady = $true
            break
        }
    }
    if (-not $RouteReady) {
        throw "Temporary Worker route did not become active before secret installation (last HTTP status $LastRouteStatus)."
    }

    $SecretVersionTag = "m2-upload-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $SecretVersionId = (& python -c "import os, re, subprocess, sys; p = subprocess.run(['npx.cmd', '-y', 'wrangler@4.114.0', 'versions', 'secret', 'put', 'UPLOAD_TOKEN', '--name', sys.argv[1], '--config', sys.argv[2], '--tag', sys.argv[3], '--message', 'temporary M2 R2 publisher secret'], input=os.environ['R2_UPLOAD_WORKER_TOKEN'], text=True, encoding='utf-8', errors='replace', capture_output=True); m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', (p.stdout or '') + '\n' + (p.stderr or '')); sys.stdout.write(m.group(0) if m else ''); raise SystemExit(p.returncode if p.returncode else (0 if m else 2))" $WorkerName $WorkerConfig $SecretVersionTag).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($SecretVersionId)) {
        throw "Temporary Worker secret version creation failed or returned no version ID."
    }
    & npx.cmd -y wrangler@4.114.0 versions deploy --version-id $SecretVersionId --percentage 100 --name $WorkerName --config $WorkerConfig --yes | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Temporary Worker secret version deployment failed."
    }
    $WorkerReady = $false
    $LastHealthStatus = 0
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        Start-Sleep -Seconds 3
        try {
            $HealthResponse = Invoke-WebRequest `
                -Uri "$WorkerUrl/health" `
                -Headers @{ Authorization = "Bearer $UploadToken" } `
                -UseBasicParsing `
                -TimeoutSec 10
            $LastHealthStatus = [int]$HealthResponse.StatusCode
        } catch {
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $LastHealthStatus = [int]$_.Exception.Response.StatusCode
            } else {
                $LastHealthStatus = 0
            }
        }
        if ($LastHealthStatus -eq 200) {
            $WorkerReady = $true
            break
        }
    }
    if (-not $WorkerReady) {
        throw "Temporary Worker did not become ready within 60 seconds (last HTTP status $LastHealthStatus)."
    }

    $BaseArguments = @(
        "-B", "-m", "magnet.resource_index.cli", "publish-media-r2-staging",
        "--release-dir", $ReleaseDir,
        "--current", $CurrentPath,
        "--public-key", $PublicKey,
        "--bucket", "magnetgoogo-media-m2-test",
        "--prefix", $Prefix,
        "--receipt-dir", $ReceiptDir,
        "--max-workers", $MaxWorkers,
        "--worker-bridge-url", $WorkerUrl,
        "--yes"
    )

    Write-Host "Running credentialed full R2 publication through the temporary Worker bridge..."
    & python @BaseArguments
    if ($LASTEXITCODE -ne 0) {
        throw "First full R2 publication failed."
    }

    Write-Host "Running the second publication to prove complete immutable reuse..."
    & python @BaseArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Second full R2 publication/reuse verification failed."
    }

    Write-Host "Full R2 publication and second-run reuse verification completed."
} finally {
    Remove-Item Env:R2_UPLOAD_WORKER_TOKEN -ErrorAction SilentlyContinue
    $UploadToken = $null
    [Array]::Clear($TokenBytes, 0, $TokenBytes.Length)
    if ($WorkerDeployed) {
        & npx.cmd -y wrangler@4.114.0 delete $WorkerName --config $WorkerConfig --force | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Temporary uploader Worker deletion failed; publication cannot be considered safely closed."
        }
    }
    Pop-Location
}
