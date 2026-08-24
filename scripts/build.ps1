[CmdletBinding()]
param(
    [string]$Python = "py -3.12",
    [switch]$SkipInstall,
    [switch]$HeadlessSmoke
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepositoryRoot

$PythonParts = $Python -split " ", 2
$PythonExe = $PythonParts[0]
$PythonArgs = @()
if ($PythonParts.Count -gt 1) { $PythonArgs = $PythonParts[1] -split " " }
$BuildPython = Join-Path $RepositoryRoot ".venv-build\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $BuildPython)) {
    & $PythonExe @PythonArgs -m venv (Join-Path $RepositoryRoot ".venv-build")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create build virtual environment" }
}
if (-not $SkipInstall) {
    & $BuildPython -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
}

& $BuildPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed" }
$Version = (& $BuildPython -c "from version import __version__; print(__version__)").Trim()
if (-not $Version) { throw "Could not determine application version" }
& $BuildPython -m PyInstaller --clean --noconfirm AI-CLI-Control-Center.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$Executable = Join-Path $RepositoryRoot "dist\AI-CLI-Control-Center.exe"
if (-not (Test-Path -LiteralPath $Executable)) { throw "Build did not create $Executable" }
& (Join-Path $RepositoryRoot "scripts\smoke.ps1") -Executable $Executable -Headless:$HeadlessSmoke -ExpectedVersion $Version

$ZipPath = Join-Path $RepositoryRoot "dist\AI-CLI-Control-Center-v$Version-windows-x64.zip"
Compress-Archive -LiteralPath $Executable -DestinationPath $ZipPath -Force
Get-FileHash -Algorithm SHA256 -LiteralPath $Executable, $ZipPath |
    ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } |
    Set-Content -Encoding ascii (Join-Path $RepositoryRoot "dist\SHA256SUMS.txt")

Write-Host "Verified executable: $Executable"
