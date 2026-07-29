# Verify 6 config/sources endpoints are aligned (size + version hash)
# Usage: .\scripts\verify_endpoints.ps1

$ErrorActionPreference = "Continue"
$ver = "0.2.2"

$endpoints = @(
    "https://cn.magnetgoogo.com/config.json",
    "https://magnetgoogo.com/config.json",
    "https://cdn.jsdelivr.net/gh/734496335/mg-data@main/config.json",
    "https://raw.githubusercontent.com/734496335/mg-data/main/config.json",
    "https://api.naoshiquan.com/config.json",
    "https://maggoogo-gateway.734496335lp.workers.dev/config.json"
)

$srcEndpoints = @(
    "https://cn.magnetgoogo.com/sources.enc.json",
    "https://magnetgoogo.com/sources.enc.json",
    "https://cdn.jsdelivr.net/gh/734496335/mg-data@main/sources.enc.json",
    "https://raw.githubusercontent.com/734496335/mg-data/main/sources.enc.json",
    "https://api.naoshiquan.com/sources.enc.json",
    "https://maggoogo-gateway.734496335lp.workers.dev/sources.enc.json"
)

function Test-Url($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
        $len = $r.RawContentLength
        $verMatch = $r.Content -match '"latest_version"\s*:\s*"([^"]+)"'
        $remoteVer = if ($Matches) { $Matches[1] } else { "?" }
        [PSCustomObject]@{ Url = $url; OK = $true; Bytes = $len; Version = $remoteVer }
    } catch {
        [PSCustomObject]@{ Url = $url; OK = $false; Bytes = 0; Version = $_.Exception.Message }
    }
}

Write-Host "=== config.json (expect $ver) ===" -ForegroundColor Cyan
$cfg = $endpoints | ForEach-Object { Test-Url $_ }
$cfg | Format-Table -AutoSize
$cfgBytes = ($cfg | Where-Object OK | Select-Object -ExpandProperty Bytes -Unique)
if ($cfgBytes.Count -gt 1) { Write-Host "WARN: config sizes differ across endpoints" -ForegroundColor Yellow }

Write-Host "`n=== sources.enc.json (bytes should match) ===" -ForegroundColor Cyan
$src = $srcEndpoints | ForEach-Object { Test-Url $_ }
$src | Format-Table -AutoSize
$srcBytes = ($src | Where-Object OK | Select-Object -ExpandProperty Bytes -Unique)
Write-Host "Unique source sizes: $($srcBytes -join ', ')"

$localEnc = "d:\lpproduct\magnet\mg-data\sources.enc.json"
if (Test-Path $localEnc) {
    $localLen = (Get-Item $localEnc).Length
    Write-Host "Local mg-data sources.enc.json: $localLen bytes"
}
