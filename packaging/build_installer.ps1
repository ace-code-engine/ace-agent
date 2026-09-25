# ============================================================================
# build_installer.ps1 -- build the ACE Windows installer (an MSI, via WiX).
#
# WHY WiX AND NOT INNO SETUP
#   Both produce a self-contained, double-click installer. WiX wins on one hard
#   point: a usable WiX toolchain exists on this machine, so the thing is ACTUALLY
#   COMPILED AND CHECKED before it is handed to CI. The Inno Setup version could
#   not be -- and "cannot be verified locally" is the exact pattern that turned CI
#   red five times in a row on this release ($Args collision, Start-Process
#   quoting, non-ASCII in a PS 5.1 script, a version check missing its "v", and a
#   smoke function called with no arguments). Anything that can be run locally
#   beats anything that can only be trusted.
#
# INPUT   dist\ace\   -- the smoke-gated PyInstaller bundle from build_exe.ps1.
#                        NOT built here: wrapping an unverified payload is exactly
#                        what the smoke gate exists to prevent, so a missing
#                        payload is a hard stop with the command to run.
# OUTPUT  dist\ace-<version>-windows-amd64.msi   (+ the portable .zip)
#
# ASCII-ONLY ON PURPOSE. Windows PowerShell 5.1 reads a BOM-less script as ANSI;
#   every byte here must be ASCII, comments included. packaging/check_packaging.ps1
#   enforces it for every packaging script, not just the newest one.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_installer.ps1
#   ... -Version 3.41.0     override the version (default: core/version.py)
#   ... -Python <exe>       interpreter for the generator (default: detected)
#   ... -NoZip              skip the portable zip
#
# EXIT: 0 = MSI produced and self-checked. 1 = failed (reason printed).
# ============================================================================
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$Python = "",
    [switch]$NoZip
)

$ErrorActionPreference = 'Continue'
$Here = Split-Path -Parent $PSCommandPath
$Repo = Split-Path -Parent $Here
$Dist = Join-Path $Repo 'dist'
$Payload = Join-Path $Dist 'ace'
$Generator = Join-Path $Here 'make_wix.py'

Write-Host "repo   : $Repo"
Write-Host "payload: $Payload"

# -- 1. payload present? -----------------------------------------------------
if (-not (Test-Path $Payload)) {
    Write-Host ""
    Write-Host "FAIL: the payload folder does not exist: $Payload"
    Write-Host "      Build (and smoke-test) it first:"
    Write-Host "        powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_exe.ps1 -Python python"
    exit 1
}
if (-not (Test-Path (Join-Path $Payload 'ace.exe'))) {
    Write-Host "FAIL: $Payload\ace.exe is missing -- the bundle is incomplete."
    exit 1
}
$sizeMb = [math]::Round(((Get-ChildItem $Payload -Recurse -File |
    Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host "payload size: $sizeMb MB"

# -- 2. interpreter (path OR command name, must actually run) ----------------
function Resolve-PythonPath([string]$Candidate) {
    if (-not $Candidate) { return $null }
    $paths = @()
    if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
        $paths += (Resolve-Path -LiteralPath $Candidate).Path
    } else {
        $paths += (Get-Command $Candidate -ErrorAction SilentlyContinue |
                   Where-Object { $_.CommandType -eq 'Application' } |
                   ForEach-Object { $_.Source })
    }
    foreach ($p in $paths) {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { continue }
        try { $out = & $p -c "print('ok')" 2>$null } catch { continue }
        # A file can exist and still not run: the Store ships a zero-byte
        # python.exe stub that Test-Path accepts and the shell rejects (9009).
        if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq 'ok') { return $p }
    }
    return $null
}

if ($Python) {
    $Python = Resolve-PythonPath $Python
    if (-not $Python) { Write-Host "FAIL: -Python '$($PSBoundParameters.Python)' is not a runnable interpreter."; exit 1 }
} else {
    foreach ($c in @($env:ACE_PYTHON, 'C:\aider_env\Scripts\python.exe',
                     (Join-Path $Repo '.ace_env\Scripts\python.exe'), 'python', 'python3', 'py')) {
        $Python = Resolve-PythonPath $c
        if ($Python) { break }
    }
}
if (-not $Python) { Write-Host "FAIL: no usable interpreter. Pass -Python <path or command>."; exit 1 }
Write-Host "python : $Python"

# -- 3. locate the WiX toolchain --------------------------------------------
# The generator knows how to find a bundled toolchain; here we only need to tell
# the user what to install if there is none at all.
function Find-Wix([string]$Name) {
    $cands = @()
    $envs = @($env:WIX, "$env:ProgramFiles(x86)\WiX Toolset v3.14", "$env:ProgramFiles\WiX Toolset v3.14",
              "$env:ProgramFiles(x86)\WiX Toolset v3.11", "$env:ProgramFiles\WiX Toolset v3.11",
              "$env:ProgramFiles(x86)\WiX Toolset v3.10", "$env:ProgramFiles\WiX Toolset v3.10")
    foreach ($e in $envs) { if ($e) { $cands += (Join-Path $e $Name) } }
    $cands += (Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
    return ($cands | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1)
}
$candle = Find-Wix 'candle.exe'
$light = Find-Wix 'light.exe'
if ($candle -and $light) {
    Write-Host "wix    : $candle"
} else {
    Write-Host ""
    Write-Host "NOTE: candle.exe/light.exe are not on PATH or in the usual install dirs."
    Write-Host "      The generator also looks for a bundled toolchain (electron-winstaller"
    Write-Host "      ships one); if it finds none the build stops with that message."
    Write-Host "      To install the toolchain:  choco install wixtoolset --no-progress -y"
    Write-Host "      (WiX v3 -- the generator targets the v3 schema.)"
}

# -- 4. generate + compile ---------------------------------------------------
$argv = @($Generator, '--build', '--payload', $Payload, '--out', $Dist)
if ($Version) { $argv += @('--version', $Version) }
if ($candle) { $argv += @('--candle', $candle) }
if ($light) { $argv += @('--light', $light) }

Write-Host ""
Write-Host "=== generating .wxs and compiling the MSI ==="
& $Python @argv
$code = $LASTEXITCODE
if ($code -ne 0) { Write-Host "FAIL: generator/compiler exited $code"; exit 1 }

# -- 5. name check + portable zip -------------------------------------------
$ver = $Version
if (-not $ver) {
    $ver = ([regex]::Match([System.IO.File]::ReadAllText((Join-Path $Repo 'core\version.py'),
                             [System.Text.Encoding]::UTF8), '__version__ = "([^"]+)"')).Groups[1].Value
}
$msi = Join-Path $Dist ("ace-{0}-windows-amd64.msi" -f $ver)
if (-not (Test-Path $msi)) { Write-Host "FAIL: expected artifact not found: $msi"; exit 1 }
Write-Host ("installer: {0}  ({1} MB)" -f $msi, [math]::Round((Get-Item $msi).Length / 1MB, 1))

if (-not $NoZip) {
    $zip = Join-Path $Dist ("ace-{0}-windows-amd64.zip" -f $ver)
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $Payload '*') -DestinationPath $zip -Force
    Write-Host ("zip      : {0}  ({1} MB)" -f $zip, [math]::Round((Get-Item $zip).Length / 1MB, 1))
}

Write-Host ""
Write-Host "OK: installer built and self-checked (the MSI is read back to confirm ace.exe is inside)."
Write-Host "    The payload itself was validated by build_exe.ps1's smoke gate, not by this step."
exit 0
