[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir,
    [Parameter(Mandatory = $true)]
    [string]$CurrentPath,
    [string]$PublicKey = "data\resource_index\.secrets\media-ed25519-public.pem",
    [string]$Server = "admin@47.103.155.154",
    [string]$RemoteRoot = "/var/www/magnetgoogo-site/media",
    [string]$ReceiptDir = "data\resource_index\media_publish_receipts"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Resolve-RepoPath([string]$Value) {
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Value))
}

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

$ReleaseDir = Resolve-RepoPath $ReleaseDir
$CurrentPath = Resolve-RepoPath $CurrentPath
$PublicKey = Resolve-RepoPath $PublicKey
$ReceiptDir = Resolve-RepoPath $ReceiptDir
$Verifier = Resolve-RepoPath "deploy\resource-index\verify-static-mirror.py"
$Installer = Resolve-RepoPath "deploy\resource-index\install-nginx-media-include.py"
$NginxSnippet = Resolve-RepoPath "deploy\resource-index\nginx-media-locations.conf"
$HttpVerifier = Resolve-RepoPath "deploy\resource-index\verify-media-http.mjs"

if (-not (Test-Path (Join-Path $ReleaseDir "v1"))) {
    throw "ReleaseDir does not contain the v1 release tree."
}
if (-not (Test-Path $CurrentPath)) {
    throw "Signed pointer candidate is missing."
}

$RunId = [Guid]::NewGuid().ToString("N")
$WorkDir = Join-Path $RepoRoot "data\resource_index\.aliyun-media-$RunId"
$PayloadDir = Join-Path $WorkDir "payload"
$PlanPath = Join-Path $WorkDir "publish-plan.json"
$ArchivePath = Join-Path $RepoRoot "data\resource_index\aliyun-media-$RunId.tar.gz"
$RemoteArchive = "/tmp/aliyun-media-$RunId.tar.gz"
$RemoteStage = "/tmp/aliyun-media-$RunId"
$ReceiptPath = Join-Path $ReceiptDir "aliyun-media-$RunId.json"

New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReceiptDir | Out-Null

try {
    Copy-Item -Recurse -Force (Join-Path $ReleaseDir "v1") $PayloadDir

    $PlanArguments = @(
        "-B", "-m", "magnet.resource_index.cli", "publish-media-r2-staging",
        "--release-dir", $ReleaseDir,
        "--current", $CurrentPath,
        "--public-key", $PublicKey,
        "--bucket", "magnetgoogo-media",
        "--prefix=",
        "--production-root",
        "--no-pointer-candidate",
        "--dry-run",
        "--plan-output", $PlanPath
    )
    Invoke-Checked "Local mirror plan generation" { python @PlanArguments | Out-Host }
    Invoke-Checked "Local mirror package verification" {
        python $Verifier --root $PayloadDir --plan $PlanPath --exact | Out-Host
    }

    Copy-Item -Force $Verifier (Join-Path $WorkDir "verify-static-mirror.py")
    Copy-Item -Force $Installer (Join-Path $WorkDir "install-nginx-media-include.py")
    Copy-Item -Force $NginxSnippet (Join-Path $WorkDir "nginx-media-locations.conf")

    $WindowsTar = Join-Path $env:SystemRoot "System32\tar.exe"
    if (-not (Test-Path $WindowsTar)) {
        throw "Windows system tar.exe is unavailable."
    }
    Invoke-Checked "Media mirror archive creation" {
        & $WindowsTar -czf $ArchivePath -C $WorkDir .
    }
    Invoke-Checked "Media mirror archive upload" {
        scp -q -o LogLevel=ERROR $ArchivePath "$Server`:$RemoteArchive"
    }

    $RemoteCommand = @"
set -euo pipefail
rm -rf '$RemoteStage'
mkdir -p '$RemoteStage'
tar -xzf '$RemoteArchive' -C '$RemoteStage'
python3 '$RemoteStage/verify-static-mirror.py' --root '$RemoteStage/payload' --plan '$RemoteStage/publish-plan.json' --exact
sudo -n python3 '$RemoteStage/verify-static-mirror.py' --root '$RemoteStage/payload' --plan '$RemoteStage/publish-plan.json' --promote-to '$RemoteRoot'
sudo -n python3 '$RemoteStage/verify-static-mirror.py' --root '$RemoteStage/payload' --plan '$RemoteStage/publish-plan.json' --promote-to '$RemoteRoot'
sudo -n python3 '$RemoteStage/install-nginx-media-include.py' --config /etc/nginx/conf.d/magnetgoogo.conf --snippet-source '$RemoteStage/nginx-media-locations.conf' --snippet-target /etc/nginx/snippets/magnetgoogo-media.conf
sudo -n nginx -t 2>&1
sudo -n systemctl reload nginx
sudo -n rm -rf '$RemoteRoot/staging'
rm -rf '$RemoteStage' '$RemoteArchive'
"@
    $RemoteCommand = $RemoteCommand.Replace("`r`n", "`n")
    $RemoteOutput = @(& ssh -o BatchMode=yes -o LogLevel=ERROR $Server $RemoteCommand 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $RemoteOutput | Out-Host
        throw "Aliyun remote mirror verification or promotion failed."
    }
    $RemoteOutput | Out-Host

    $Plan = Get-Content -Raw -Encoding UTF8 $PlanPath | ConvertFrom-Json
    $HttpReportPath = Join-Path $WorkDir "aliyun-http-report.json"
    Invoke-Checked "Aliyun public endpoint verification" {
        node $HttpVerifier `
            --base "https://cn.magnetgoogo.com/media" `
            --plan $PlanPath `
            --expected-current-status 404 | Tee-Object -FilePath $HttpReportPath | Out-Host
    }
    $HttpReport = Get-Content -Raw -Encoding UTF8 $HttpReportPath | ConvertFrom-Json

    $Receipt = [ordered]@{
        schema_version = "media-aliyun-receipt/1"
        status = "success"
        release_id = $Plan.release_id
        pointer_revision = $Plan.pointer_revision
        target = "https://cn.magnetgoogo.com/media"
        remote_root = $RemoteRoot
        total_file_count = $Plan.total_file_count
        total_bytes = $Plan.total_bytes
        endpoint_checks = $HttpReport.checks
        current_http_status = [int]$HttpReport.current_status
        current_promoted = $false
        completed_at = [DateTimeOffset]::UtcNow.ToString("o")
    }
    $Receipt | ConvertTo-Json -Depth 8 -Compress | Set-Content -Encoding UTF8 $ReceiptPath
    Write-Host "Aliyun immutable media mirror verified. current.json remains unpublished."
    Write-Host "Receipt: $ReceiptPath"
} finally {
    Remove-Item -Recurse -Force $WorkDir -ErrorAction SilentlyContinue
    Remove-Item -Force $ArchivePath -ErrorAction SilentlyContinue
}
