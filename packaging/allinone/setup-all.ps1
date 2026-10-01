# setup-all.ps1 - one command for Windows: mount ACE into Cline + report the base verdict.
#
# ASCII only (PS 5.1 reads .ps1 as the system codepage without a BOM).
#
#   powershell -ExecutionPolicy Bypass -File setup-all.ps1
#   powershell -ExecutionPolicy Bypass -File setup-all.ps1 -Permission write
#   powershell -ExecutionPolicy Bypass -File setup-all.ps1 -SandboxApi http://10.0.0.5:3000
#   powershell -ExecutionPolicy Bypass -File setup-all.ps1 -DryRun
#
# What this does NOT do: install the virtualization base. Windows cannot host it (see
# sandbox/preflight.ps1) - the base lives on a Linux box and this machine points at it.
param(
    [switch]$DryRun,
    [ValidateSet('readonly', 'write', 'full')][string]$Permission = 'readonly',
    [string]$Python = '',
    [string]$SandboxApi = '',
    [string]$SandboxKey = ''
)
$ErrorActionPreference = 'Continue'
$PackDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Windows PowerShell ships as `powershell`, newer/other platforms as `pwsh` - do not assume
# either one exists (the pack builder died on exactly that assumption: green locally, red on
# the Linux runner).
$psExe = if (Get-Command powershell -ErrorAction SilentlyContinue) { 'powershell' } else { 'pwsh' }
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " ACE all-in-one: base verdict + MCP mount" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. base preflight (tells the truth about THIS machine) ----
$pre = Join-Path $PackDir 'sandbox\preflight.ps1'
if (Test-Path $pre) {
    & $psExe -NoProfile -ExecutionPolicy Bypass -File $pre
} else {
    Write-Host "sandbox\preflight.ps1 missing from this pack" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "----------------------------------------------" -ForegroundColor Cyan
Write-Host " Mounting ACE as an MCP server into your host" -ForegroundColor Cyan
Write-Host "----------------------------------------------" -ForegroundColor Cyan

# ---- 2. write the host MCP config (merge + backup; see install-cline.ps1) ----
$installer = Join-Path $PackDir 'install-cline.ps1'
if (-not (Test-Path $installer)) {
    Write-Host "install-cline.ps1 missing from this pack" -ForegroundColor Red
    exit 1
}
$psArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $installer,
            '-Permission', $Permission)
if ($DryRun)     { $psArgs += '-DryRun' }
if ($Python)     { $psArgs += @('-Python', $Python) }
if ($SandboxApi) { $psArgs += @('-SandboxApi', $SandboxApi) }
if ($SandboxKey) { $psArgs += @('-SandboxKey', $SandboxKey) }
& $psExe @psArgs

Write-Host ""
Write-Host "----------------------------------------------" -ForegroundColor Cyan
Write-Host " Verify (do not trust 'it looks connected')" -ForegroundColor Cyan
Write-Host "----------------------------------------------" -ForegroundColor Cyan
Write-Host "  python `"$PackDir\verify-mcp.py`"                 # MCP layer"
Write-Host "  python `"$PackDir\sandbox\verify-sandbox.py`"      # base layer (needs ACE_SANDBOX_API)"
if (-not $SandboxApi) {
    Write-Host ""
    Write-Host "No -SandboxApi given: ace_sandbox_exec will REFUSE (Tier 0) until a base is reachable." -ForegroundColor Yellow
    Write-Host "That is by design - it never falls back to running untrusted code on this machine." -ForegroundColor Yellow
    Write-Host "Get a base address from a Linux box:  sudo bash sandbox/setup-sandbox.sh" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Then reload the VSCode window and ask Cline: 'use ace to read the first line of README.md'" -ForegroundColor Green