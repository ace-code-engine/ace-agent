# install-cline.ps1 - write ACE into Cline's MCP config (backup first, safe to re-run).
#
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as the system codepage unless
# the file has a BOM, and a mangled quote turns a security-adjacent installer into a
# parse error.
#
#   powershell -ExecutionPolicy Bypass -File install-cline.ps1
#   powershell -ExecutionPolicy Bypass -File install-cline.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File install-cline.ps1 -Permission write
#   powershell -ExecutionPolicy Bypass -File install-cline.ps1 -StoreRoot D:\tmp\store
#
# SAFETY: this file MERGES into the existing config - never replaces it. The first version
# used "ConvertFrom-Json -AsHashtable" (PowerShell 7+ only); on 5.1 that throws, which the
# catch treated as "config is invalid" and would have silently dropped every OTHER MCP
# server the user had. Parsing is 5.1-compatible now, and there is a merge test.
param(
    [switch]$DryRun,
    [ValidateSet('readonly', 'write', 'full')][string]$Permission = 'readonly',
    [string]$Python = '',
    [string]$StoreRoot = '',
    [string]$SandboxApi = '',
    [string]$SandboxKey = ''
)
$ErrorActionPreference = 'Stop'

$PackDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Entry = Join-Path $PackDir 'ai_code.py'
if (-not (Test-Path $Entry)) { throw "ai_code.py not found next to this script: $Entry" }

if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "python not found in PATH. Install Python 3.10+, or pass -Python <path>." }
    $Python = $cmd.Source
}

# Sandbox base is OPTIONAL: without it ace_sandbox_exec refuses (Tier 0) by design.
$envMap = [ordered]@{ PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8' }
if ($SandboxApi) { $envMap['ACE_SANDBOX_API'] = $SandboxApi }
if ($SandboxKey) { $envMap['ACE_SANDBOX_KEY'] = $SandboxKey }

$server = [pscustomobject][ordered]@{
    command = $Python
    args    = @($Entry, '--mcp', '--permission', $Permission)
    env     = $envMap
}

if ($StoreRoot) {
    $stores = @($StoreRoot)
} else {
    # Both the upstream extension and the Chinese fork keep their own globalStorage.
    $stores = @(
        (Join-Path $env:APPDATA 'Code\User\globalStorage\saoudrizwan.claude-dev'),
        (Join-Path $env:APPDATA 'Code\User\globalStorage\hybridtalentcomputing.cline-chinese'),
        (Join-Path $env:APPDATA 'Code\User\globalStorage\saoudrizwan.claude-dev-insiders')
    ) | Where-Object { Test-Path $_ }

    if (-not $stores) {
        Write-Host "No Cline globalStorage found under $env:APPDATA\Code\User\globalStorage" -ForegroundColor Yellow
        Write-Host "Open VSCode once with Cline installed, then re-run this script." -ForegroundColor Yellow
    }
}

foreach ($store in $stores) {
    $dir = Join-Path $store 'settings'
    $cfg = Join-Path $dir 'cline_mcp_settings.json'
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    # --- load + merge (5.1-compatible; unknown keys are preserved) ---
    $obj = $null
    if (Test-Path $cfg) {
        $raw = Get-Content $cfg -Raw -Encoding UTF8
        if ($raw -and $raw.Trim()) {
            try { $obj = $raw | ConvertFrom-Json } catch {
                Write-Host "  WARN existing config is not valid JSON, starting from scratch: $cfg" -ForegroundColor Yellow
            }
        }
    }
    if (-not $obj) { $obj = New-Object psobject }

    $hadServers = [bool]$obj.PSObject.Properties['mcpServers']
    $kept = 0
    if ($hadServers -and $obj.mcpServers) { $kept = @($obj.mcpServers.PSObject.Properties).Count }
    if (-not $hadServers) {
        $obj | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object psobject)
    }
    if (-not $obj.mcpServers) { $obj.mcpServers = New-Object psobject }
    $obj.mcpServers | Add-Member -NotePropertyName ace -NotePropertyValue $server -Force

    $json = $obj | ConvertTo-Json -Depth 12
    if ($DryRun) {
        Write-Host "  DRY-RUN would write: $cfg  (existing mcpServers kept: $kept)"
    } else {
        if (Test-Path $cfg) {
            $backup = "$cfg.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            Copy-Item $cfg $backup -Force
            Write-Host "  backup: $backup"
        }
        # UTF-8 without BOM: JSON.parse on the extension side is happier without it.
        [System.IO.File]::WriteAllText($cfg, $json, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  written: $cfg  (permission=$Permission, other servers kept: $kept)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Next: reload the VSCode window, then in Cline ask:" -ForegroundColor Cyan
Write-Host "  'use ace to read the first line of README.md'"
Write-Host "Self-check without the host:  python `"$PackDir\verify-mcp.py`""
