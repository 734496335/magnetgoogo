[CmdletBinding()]
param(
    [ValidateSet("javbus", "sixv", "dytt8899")]
    [string]$Source = "javbus",
    [int]$Count = 0,
    [string]$VenvPath = "",
    [string]$OutputDir = ""
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
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"

if (-not (Test-Path $VenvPath)) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & py -3 -m venv $VenvPath
    } else {
        & python -m venv $VenvPath
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create Python virtual environment. Install Python 3.10 or newer."
    }
}

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment Python not found: $PythonExe"
}

& $PythonExe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required."
}

& $PythonExe -m pip install `
    --disable-pip-version-check `
    --only-binary=:all: `
    -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Resource Index runtime dependency installation failed"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$DoctorArguments = @(
    "-B", "-m", "magnet.resource_index.cli", "doctor",
    "--source", $Source,
    "--output-dir", $OutputDir
)
if ($Count -gt 0) {
    $DoctorArguments += @("--count", $Count)
}
Push-Location $RepoRoot
try {
    & $PythonExe @DoctorArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Deployment doctor failed"
    }
} finally {
    Pop-Location
}

Write-Host "Resource Index runtime is ready."
Write-Host "Python: $PythonExe"
Write-Host "Output: $OutputDir"
Write-Host "Run: deploy\resource-index\run-latest.bat"
