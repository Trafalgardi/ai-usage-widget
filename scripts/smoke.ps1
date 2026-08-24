[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Executable)

$ErrorActionPreference = "Stop"
$ResolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$File = Get-Item -LiteralPath $ResolvedExecutable
if ($File.Length -lt 1MB) { throw "Executable is unexpectedly small: $($File.Length) bytes" }
$Version = $File.VersionInfo.ProductVersion
if (-not $Version.StartsWith("2.0.0")) { throw "Unexpected product version: $Version" }

$env:AI_CLI_CONTROL_CENTER_UI_SMOKE_TEST = "1"
$Process = Start-Process -FilePath $ResolvedExecutable -PassThru -WindowStyle Hidden
try {
    if (-not $Process.WaitForExit(15000)) { throw "Smoke process did not exit within 15 seconds" }
    if ($Process.ExitCode -ne 0) { throw "Executable exited with code $($Process.ExitCode)" }
} finally {
    if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
    Get-Process -Name $File.BaseName -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $ResolvedExecutable } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item Env:AI_CLI_CONTROL_CENTER_UI_SMOKE_TEST -ErrorAction SilentlyContinue
}
Write-Host "Smoke check passed for $ResolvedExecutable"
