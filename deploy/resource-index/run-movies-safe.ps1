[CmdletBinding()]
param(
    [string]$Sources = "sixv,dytt8899",
    [int]$Count = 0,
    [string]$VenvPath = "",
    [string]$OutputDir = "",
    [string]$Log = ""
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
foreach ($Source in ($Sources -split ",")) {
    $Trimmed = $Source.Trim()
    if (-not [string]::IsNullOrWhiteSpace($Trimmed)) {
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
} finally {
    Pop-Location
}
exit $Code
