[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CurrentPath,
    [Parameter(Mandatory = $true)]
    [string]$ReleaseDir,
    [string]$PublicKey = "data\resource_index\.secrets\media-ed25519-public.pem",
    [string]$R2Base = "https://media.magnetgoogo.com",
    [string]$AliyunBase = "https://cn.magnetgoogo.com/media",
    [string]$AliyunServer = "admin@47.103.155.154",
    [string]$AliyunRoot = "/var/www/magnetgoogo-site/media",
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

$CurrentPath = Resolve-RepoPath $CurrentPath
$ReleaseDir = Resolve-RepoPath $ReleaseDir
$PublicKey = Resolve-RepoPath $PublicKey
$ReceiptDir = Resolve-RepoPath $ReceiptDir
$Verifier = Resolve-RepoPath "deploy\resource-index\verify-media-control.py"
$Fetcher = Resolve-RepoPath "deploy\resource-index\fetch-media-file.mjs"
$HttpVerifier = Resolve-RepoPath "deploy\resource-index\verify-media-http.mjs"
$Pointer = Get-Content -Raw -Encoding UTF8 $CurrentPath | ConvertFrom-Json
$ManifestRelative = $Pointer.manifest_path.TrimStart("/").Replace("/", "\")
$ManifestPath = Join-Path $ReleaseDir $ManifestRelative
$RunId = [Guid]::NewGuid().ToString("N")
$WorkDir = Join-Path $RepoRoot "data\resource_index\.current-promotion-$RunId"
$ReceiptPath = Join-Path $ReceiptDir "media-current-$RunId.json"
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReceiptDir | Out-Null

try {
    $CandidateReportPath = Join-Path $WorkDir "candidate-report.json"
    Invoke-Checked "Signed current candidate verification" {
        python $Verifier --pointer $CurrentPath --public-key $PublicKey --manifest $ManifestPath | Tee-Object -FilePath $CandidateReportPath | Out-Host
    }
    $CandidateReport = Get-Content -Raw -Encoding UTF8 $CandidateReportPath | ConvertFrom-Json
    $ControlPlanPath = Join-Path $WorkDir "control-plan.json"
    Invoke-Checked "Control-plane data plan verification" {
        python -B -m magnet.resource_index.cli publish-media-r2-staging `
            --release-dir $ReleaseDir `
            --current $CurrentPath `
            --public-key $PublicKey `
            --bucket magnetgoogo-media `
            --prefix= `
            --production-root `
            --no-pointer-candidate `
            --dry-run `
            --plan-output $ControlPlanPath | Out-Host
    }

    $EndpointEvidence = @()
    foreach ($Base in @($R2Base, $AliyunBase)) {
        $ManifestDownload = Join-Path $WorkDir (([Guid]::NewGuid().ToString("N")) + ".manifest.json")
        $ManifestReportPath = Join-Path $WorkDir (([Guid]::NewGuid().ToString("N")) + ".manifest-report.json")
        $ManifestUrl = $Base.TrimEnd("/") + $Pointer.manifest_path
        Invoke-Checked "Data-plane Manifest download" {
            node $Fetcher --url $ManifestUrl --output $ManifestDownload --report $ManifestReportPath
        }
        $ManifestReport = Get-Content -Raw -Encoding UTF8 $ManifestReportPath | ConvertFrom-Json
        if ([int]$ManifestReport.status -ne 200) {
            throw "Data-plane Manifest returned HTTP $($ManifestReport.status) at $Base."
        }
        $ManifestHash = [string]$ManifestReport.sha256
        if ($ManifestHash -ne $CandidateReport.manifest_sha256) {
            throw "Data-plane Manifest hash mismatch at $Base."
        }

        $ExistingDownload = Join-Path $WorkDir (([Guid]::NewGuid().ToString("N")) + ".current.json")
        $ExistingReportPath = Join-Path $WorkDir (([Guid]::NewGuid().ToString("N")) + ".current-report.json")
        $CurrentUrl = $Base.TrimEnd("/") + "/v1/current.json"
        Invoke-Checked "Existing current request" {
            node $Fetcher --url $CurrentUrl --output $ExistingDownload --report $ExistingReportPath
        }
        $ExistingStatus = [int](Get-Content -Raw -Encoding UTF8 $ExistingReportPath | ConvertFrom-Json).status
        $ExistingState = "absent"
        if ($ExistingStatus -eq 200) {
            $ExistingReportPath = Join-Path $WorkDir (([Guid]::NewGuid().ToString("N")) + ".existing-report.json")
            Invoke-Checked "Existing signed current verification" {
                python $Verifier --pointer $CurrentPath --public-key $PublicKey --existing $ExistingDownload | Tee-Object -FilePath $ExistingReportPath | Out-Host
            }
            $ExistingState = (Get-Content -Raw -Encoding UTF8 $ExistingReportPath | ConvertFrom-Json).existing_state
        } elseif ($ExistingStatus -ne 404) {
            throw "Unexpected current.json HTTP status $ExistingStatus from $Base."
        }
        $EndpointEvidence += [ordered]@{
            base = $Base
            manifest_sha256 = $ManifestHash
            existing_current_status = $ExistingStatus
            existing_state = $ExistingState
        }
    }

    Invoke-Checked "R2 current pointer upload" {
        npx.cmd -y wrangler@4.114.0 r2 object put `
            "magnetgoogo-media/v1/current.json" `
            --file $CurrentPath `
            --content-type "application/json; charset=utf-8" `
            --cache-control "public, max-age=60, must-revalidate" `
            --remote `
            --force | Out-Host
    }

    $RemoteTemp = "/tmp/media-current-$RunId.json"
    Invoke-Checked "Aliyun current pointer upload" {
        scp -q -o LogLevel=ERROR $CurrentPath "$AliyunServer`:$RemoteTemp"
    }
    $RemoteCommand = "set -e; sudo -n mkdir -p '$AliyunRoot/v1'; sudo -n install -m 0644 '$RemoteTemp' '$AliyunRoot/v1/.current-$RunId.tmp'; sudo -n mv -f '$AliyunRoot/v1/.current-$RunId.tmp' '$AliyunRoot/v1/current.json'; rm -f '$RemoteTemp'"
    Invoke-Checked "Aliyun atomic current pointer promotion" {
        ssh -o BatchMode=yes -o LogLevel=ERROR $AliyunServer $RemoteCommand
    }

    $PointerHash = $CandidateReport.pointer_sha256
    $PromotedEvidence = @()
    foreach ($Base in @($R2Base, $AliyunBase)) {
        $EndpointReportPath = Join-Path $WorkDir (([Guid]::NewGuid().ToString("N")) + ".promoted-report.json")
        Invoke-Checked "Promoted endpoint verification" {
            node $HttpVerifier `
                --base $Base `
                --plan $ControlPlanPath `
                --expected-current-status 200 `
                --expected-current-sha256 $PointerHash | Tee-Object -FilePath $EndpointReportPath | Out-Host
        }
        $EndpointReport = Get-Content -Raw -Encoding UTF8 $EndpointReportPath | ConvertFrom-Json
        $PromotedEvidence += [ordered]@{
            base = $Base
            pointer_sha256 = $EndpointReport.current_sha256
            match = $true
        }
    }

    $Receipt = [ordered]@{
        schema_version = "media-current-promotion-receipt/1"
        status = "success"
        release_id = $CandidateReport.release_id
        pointer_revision = $CandidateReport.pointer_revision
        pointer_sha256 = $CandidateReport.pointer_sha256
        manifest_sha256 = $CandidateReport.manifest_sha256
        preflight = $EndpointEvidence
        promoted = $PromotedEvidence
        completed_at = [DateTimeOffset]::UtcNow.ToString("o")
    }
    $Receipt | ConvertTo-Json -Depth 8 -Compress | Set-Content -Encoding UTF8 $ReceiptPath
    Write-Host "Signed media current pointer promoted to both data planes."
    Write-Host "Receipt: $ReceiptPath"
} finally {
    Remove-Item -Recurse -Force $WorkDir -ErrorAction SilentlyContinue
}
