# build_allinone_bundle.ps1 - the all-in-one pack: virtualization base + MCP mount.
#
#   dist/ace-secbox-<ver>.zip = ace-mcp-<ver> contents  +  sandbox/ (base bootstrap)
#                             +  setup-all.ps1 / setup-all.sh  +  README-ALLINONE.md
#
# Why one zip instead of two downloads: the two halves are useless apart (a base with no
# decision layer runs untrusted code with no policy; a decision layer with no base can only
# refuse). One unpack, one README, and the user picks the shape (same box / remote base /
# mount only) from sandbox/preflight.
#
# ASCII only (see install-cline.ps1 for why) - every non-ASCII string lives in the .md files.
param()
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)   # repo root
$Version = (Select-String -Path (Join-Path $Root 'core\version.py') -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "cannot read __version__ from core/version.py" }

$Name = "ace-secbox-$Version"
$Dist = Join-Path $Root 'dist'
$Stage = Join-Path $Dist $Name
$Zip = Join-Path $Dist "$Name.zip"

Write-Host "building $Name" -ForegroundColor Cyan

# 1) Start from the MCP pack: one source of truth for the runtime set + host configs.
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'packaging\build_mcp_bundle.ps1') -KeepStaging | Out-Null
$McpStage = Join-Path $Dist "ace-mcp-$Version"
if (-not (Test-Path $McpStage)) { throw "mcp staging missing: $McpStage" }

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
Move-Item $McpStage $Stage

# 2) Add the base half + the single entry points.
Copy-Item (Join-Path $Root 'packaging\allinone\sandbox') (Join-Path $Stage 'sandbox') -Recurse -Force
foreach ($f in @('README-ALLINONE.md', 'setup-all.ps1', 'setup-all.sh')) {
    Copy-Item (Join-Path $Root "packaging\allinone\$f") (Join-Path $Stage $f) -Force
}
# The MCP pack's own README stays (it is the how-to for the mount half).
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

# 3) CRLF for the batch file: cmd.exe misreads LF-only .cmd (the repo has a guard for this).
$cmd = Join-Path $Stage 'ace-mcp.cmd'
if (Test-Path $cmd) {
    $t = [System.IO.File]::ReadAllText($cmd) -replace "`r`n", "`n" -replace "`n", "`r`n"
    [System.IO.File]::WriteAllText($cmd, $t, (New-Object System.Text.UTF8Encoding($false)))
}

if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $Zip -CompressionLevel Optimal
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Remove-Item $Stage -Recurse -Force

Write-Host ""
Write-Host ("zip : {0}  ({1:N1} MB)" -f $Zip, ((Get-Item $Zip).Length / 1MB)) -ForegroundColor Green
