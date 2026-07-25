[CmdletBinding()]
param(
    [ValidateSet("javbus", "sixv")]
    [string]$Source = "javbus",
    [int]$Count = 100,
    [string]$VenvPath = "",
    [string]$OutputDir = "",
    [string]$Database = ""
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
if (-not [string]::IsNullOrWhiteSpace($Database)) {
    $Database = Resolve-RepoPath $Database ""
}

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Runtime is not installed. Run deploy\resource-index\setup.bat first."
}

$Arguments = @(
    "-B",
    "-m", "magnet.resource_index.cli",
    "doctor",
    "--source", $Source,
    "--count", $Count,
    "--output-dir", $OutputDir
)
if (-not [string]::IsNullOrWhiteSpace($Database)) {
    $Arguments += @("--db", $Database)
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
