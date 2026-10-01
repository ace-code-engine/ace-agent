# build_mcp_bundle.ps1 - produce the non-intrusive MCP server pack (dist/ace-mcp-server-<ver>.zip)
#
# ASCII only (PS 5.1 reads .ps1 as the system codepage without a BOM).
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_mcp_bundle.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build_mcp_bundle.ps1 -KeepStaging
param(
    [switch]$KeepStaging
)
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot          # repo root (this file lives in packaging/)
. (Join-Path $PSScriptRoot '_pack_common.ps1')

$Version = Resolve-AceVersion -Root $Root
$Name = "ace-mcp-server-$Version"
$Dist = Join-Path $Root 'dist'
$Stage = Join-Path $Dist $Name
$Zip = Join-Path $Dist "$Name.zip"

Write-Host "building $Name" -ForegroundColor Cyan
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

Copy-AceRuntime -Root $Root -Stage $Stage
Copy-AcePackFiles -Root $Root -Stage $Stage
Set-CmdCrlf -Stage $Stage
# Version stamp: the pack must say which build it is without importing anything.
Set-Content -Path (Join-Path $Stage 'VERSION') -Value $Version -Encoding ascii

New-PackZip -Stage $Stage -Zip $Zip
if (-not $KeepStaging) { Remove-Item $Stage -Recurse -Force }
Write-Host "zip is what ships; staging dir is removed unless -KeepStaging is passed."
