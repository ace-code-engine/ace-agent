# build_allinone_bundle.ps1 - the all-in-one pack: virtualization base + MCP server.
#
#   dist/hooh-sandbox-bundle-<ver>.zip = hooh-mcp-server-<ver> contents + sandbox/ (base bootstrap)
#                                     + setup-all.ps1 / setup-all.sh + README-ALLINONE.md
#
# Why one zip instead of two downloads: the two halves are useless apart (a base with no
# decision layer runs untrusted code with no policy; a decision layer with no base can only
# refuse). One unpack, one README, and the user picks the shape (same box / remote base /
# mount only) from sandbox/preflight.
#
# ASCII only (see _pack_common.ps1) - every non-ASCII string lives in the .md files.
param()
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot          # repo root (this file lives in packaging/)
. (Join-Path $PSScriptRoot '_pack_common.ps1')

$Version = Resolve-AceVersion -Root $Root
$Name = "hooh-sandbox-bundle-$Version"
$Dist = Join-Path $Root 'dist'
$Stage = Join-Path $Dist $Name
$Zip = Join-Path $Dist "$Name.zip"

Write-Host "building $Name" -ForegroundColor Cyan
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

# Same runtime + host configs as the MCP pack (one source of truth: _pack_common.ps1).
Copy-AceRuntime -Root $Root -Stage $Stage
Copy-AcePackFiles -Root $Root -Stage $Stage

# The base half + the single entry points.
Copy-Item (Join-Path $Root 'packaging\allinone\sandbox') (Join-Path $Stage 'sandbox') -Recurse -Force
Write-Host "  + sandbox/"
foreach ($f in @('README-ALLINONE.md', 'setup-all.ps1', 'setup-all.sh')) {
    Copy-Item (Join-Path $Root "packaging\allinone\$f") (Join-Path $Stage $f) -Force
    Write-Host "  + $f"
}

Set-CmdCrlf -Stage $Stage
Set-Content -Path (Join-Path $Stage 'VERSION') -Value $Version -Encoding ascii

New-PackZip -Stage $Stage -Zip $Zip
Remove-Item $Stage -Recurse -Force
