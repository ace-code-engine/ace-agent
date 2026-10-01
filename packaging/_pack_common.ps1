# _pack_common.ps1 - shared helpers for the two pack builders.
#
# Dot-source this file; do NOT invoke it as a script. Two reasons:
#   1. 嵌套调用子脚本时 `$MyInvocation.MyCommand.Path` 的解析不可靠（第一版就是因此让
#      "dist/ 里找不到 staging" 这种错看起来像打包逻辑坏了）；
#   2. 更早的一版还 shell out 到 `powershell`，在 Linux runner 上根本没这个可执行名。
#   用 `$PSScriptRoot` + 共享函数，两个坑一起消掉。
#
# ASCII only (PS 5.1 reads .ps1 as the system codepage without a BOM).

function Resolve-AceVersion {
    param([string]$Root)
    $m = Select-String -Path (Join-Path $Root 'core\version.py') -Pattern '__version__\s*=\s*"([^"]+)"'
    if (-not $m) { throw "cannot read __version__ from core/version.py" }
    return $m.Matches[0].Groups[1].Value
}

# Top-level modules are taken by GLOB, not a hand-written list: the first version listed only
# ai_code.py + execution_layer.py and the self-check caught the omission (ai_code imports
# agent_runner at module level). A whitelist that must be updated whenever someone adds a
# top-level module is a whitelist that will be wrong.
function Copy-AceRuntime {
    param([string]$Root, [string]$Stage)
    Get-ChildItem -Path $Root -File -Filter '*.py' |
        Where-Object { $_.Name -ne 'test_all.py' } |
        ForEach-Object {
            Copy-Item $_.FullName (Join-Path $Stage $_.Name) -Force
            Write-Host "  + $($_.Name)"
        }
    foreach ($d in @('core', 'tools', 'cli', 'ui', 'tui', 'locales', 'prompts', 'assets')) {
        $src = Join-Path $Root $d
        if (-not (Test-Path $src)) { Write-Host "  - $d (absent, skipped)" -ForegroundColor DarkGray; continue }
        Copy-Item $src (Join-Path $Stage $d) -Recurse -Force
        Write-Host "  + $d/"
    }
}

# The non-intrusive layer itself: hosts configs, launchers, installer, self-check, docs.
function Copy-AcePackFiles {
    param([string]$Root, [string]$Stage)
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
}

function Remove-PackNoise {
    param([string]$Stage)
    Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# cmd.exe misreads LF-only .cmd (the repo has a guard for exactly this).
function Set-CmdCrlf {
    param([string]$Stage)
    $cmd = Join-Path $Stage 'ace-mcp.cmd'
    if (Test-Path $cmd) {
        $t = [System.IO.File]::ReadAllText($cmd) -replace "`r`n", "`n" -replace "`n", "`r`n"
        [System.IO.File]::WriteAllText($cmd, $t, (New-Object System.Text.UTF8Encoding($false)))
    }
}

function New-PackZip {
    param([string]$Stage, [string]$Zip)
    Remove-PackNoise -Stage $Stage
    if (Test-Path $Zip) { Remove-Item $Zip -Force }
    Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $Zip -CompressionLevel Optimal
    $mb = (Get-Item $Zip).Length / 1MB
    Write-Host ""
    Write-Host ("zip : {0}  ({1:N1} MB)" -f $Zip, $mb) -ForegroundColor Green
}
