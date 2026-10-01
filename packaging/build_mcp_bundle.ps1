# build_mcp_bundle.ps1 - produce the non-intrusive MCP access pack (dist/ace-mcp-<ver>.zip)
#
# ASCII only (see install-cline.ps1 for why: PS 5.1 reads .ps1 as the system codepage).
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_mcp_bundle.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build_mcp_bundle.ps1 -KeepStaging
param(
    [switch]$KeepStaging
)
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)   # repo root
$Version = (Select-String -Path (Join-Path $Root 'core\version.py') -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "cannot read __version__ from core/version.py" }

$Name = "ace-mcp-$Version"
$Dist = Join-Path $Root 'dist'
$Stage = Join-Path $Dist $Name
$Zip = Join-Path $Dist "$Name.zip"

Write-Host "building $Name" -ForegroundColor Cyan
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

# What --mcp actually needs. Deliberately NOT included: test_all.py (the test suite, 16k
# lines) / frontend/ (Ink shell) / docs/ demo/ e2e/ benchmarks/ examples/ evidence-pack/
# docker/ engine/ executor/ skills/ vendor/ (repo material, not runtime).
#
# Top-level modules are taken by GLOB rather than a hand-written list: the first version
# listed only ai_code.py + execution_layer.py and the self-check caught the omission
# (ai_code imports agent_runner at module level). A whitelist that has to be updated
# whenever someone adds a top-level module is a whitelist that will be wrong.
$TopModules = Get-ChildItem -Path $Root -File -Filter '*.py' |
    Where-Object { $_.Name -ne 'test_all.py' } |
    Select-Object -ExpandProperty Name
$PkgDirs = @('core', 'tools', 'cli', 'ui', 'tui', 'locales', 'prompts', 'assets')

foreach ($f in $TopModules) {
    Copy-Item (Join-Path $Root $f) (Join-Path $Stage $f) -Force
    Write-Host "  + $f"
}
foreach ($d in $PkgDirs) {
    $src = Join-Path $Root $d
    if (-not (Test-Path $src)) { Write-Host "  - $d (absent, skipped)" -ForegroundColor DarkGray; continue }
    Copy-Item $src (Join-Path $Stage $d) -Recurse -Force
    Write-Host "  + $d/"
}
# Pack-only files (the non-intrusive layer itself).
foreach ($f in @('README-MCP.md', 'ace-mcp.cmd', 'ace-mcp.sh', 'verify-mcp.py', 'install-cline.ps1')) {
    Copy-Item (Join-Path $Root "packaging\mcp\$f") (Join-Path $Stage $f) -Force
    Write-Host "  + $f"
}
Copy-Item (Join-Path $Root 'packaging\mcp\configs') (Join-Path $Stage 'configs') -Recurse -Force
Write-Host "  + configs/"

# License / security statement travel with the pack (they are the terms of use).
foreach ($f in @('LICENSE', 'SECURITY.md')) {
    $p = Join-Path $Root $f
    if (Test-Path $p) { Copy-Item $p (Join-Path $Stage $f) -Force; Write-Host "  + $f" }
}

# Drop bytecode caches: a stale .pyc from the build machine is worse than useless.
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
# Version stamp: the pack must say which build it is without importing anything.
Set-Content -Path (Join-Path $Stage 'VERSION') -Value $Version -Encoding ascii

if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $Zip -CompressionLevel Optimal
if (-not $KeepStaging) { Remove-Item $Stage -Recurse -Force }

$size = (Get-Item $Zip).Length
Write-Host ""
Write-Host ("zip : {0}  ({1:N1} MB)" -f $Zip, ($size / 1MB)) -ForegroundColor Green
Write-Host "zip is what ships; staging dir is removed unless -KeepStaging is passed."
