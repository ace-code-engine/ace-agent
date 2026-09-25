# ============================================================================
# build_installer.ps1 -- compile the ACE Windows installer (Inno Setup).
#
# INPUT   dist\ace\   -- produced by build_exe.ps1 (the smoke-gated PyInstaller
#                        bundle). This script does NOT build it: if the folder is
#                        missing or empty it stops and says which command to run,
#                        because an installer wrapping an unverified bundle is
#                        exactly what the smoke gate exists to prevent.
# OUTPUT  dist\ace-<version>-windows-amd64-setup.exe
#
# WHY A SEPARATE STEP FROM build_exe.ps1
#   Building and validating the payload is one job; wrapping it for installation
#   is another. Keeping them apart means the installer can be rebuilt (different
#   wording, different PATH behaviour) without re-freezing, and it keeps the
#   smoke gate meaningful: it validates the payload, not the wrapper.
#
# ASCII-ONLY ON PURPOSE. Windows PowerShell 5.1 reads a BOM-less script as ANSI;
#   this repository has broken CI three times on that alone. Keep every byte
#   ASCII, comments included. packaging/check_packaging.ps1 enforces it.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_installer.ps1
#   ... -Version 3.41.0        override the version (default: read core/version.py)
#   ... -Iscc <path>           full path to ISCC.exe
#   ... -NoZip                 skip re-creating the portable zip
#
# EXIT: 0 = installer produced. 1 = failed (reason printed).
# ============================================================================
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$Iscc = "",
    [switch]$NoZip
)

$ErrorActionPreference = 'Continue'
$Here = Split-Path -Parent $PSCommandPath
$Repo = Split-Path -Parent $Here
$Dist = Join-Path $Repo 'dist'
$Payload = Join-Path $Dist 'ace'
$Iss = Join-Path $Here 'ace.iss'

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
$payloadMb = [math]::Round(((Get-ChildItem $Payload -Recurse -File |
    Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host "payload size: $payloadMb MB"

# -- 2. version (single source) ---------------------------------------------
if (-not $Version) {
    $vf = Join-Path $Repo 'core\version.py'
    if (-not (Test-Path $vf)) { Write-Host "FAIL: core\version.py not found"; exit 1 }
    $Version = ([regex]::Match([System.IO.File]::ReadAllText($vf, [System.Text.Encoding]::UTF8),
                               '__version__ = "([^"]+)"')).Groups[1].Value
}
if (-not $Version) { Write-Host "FAIL: could not determine the version"; exit 1 }
# Prerelease suffixes must not leak into AppVersion (Inno wants x.y.z there).
$numeric = ($Version -split '-')[0]
$extra = if ($Version -ne $numeric) { '-' + ($Version.Substring($numeric.Length + 1)) } else { '' }
Write-Host "version: $Version  (AppVersion=$numeric, tag=$extra)"

# -- 3. locate ISCC ----------------------------------------------------------
if (-not $Iscc) {
    $cands = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $Iscc = $cands | Select-Object -First 1
}
if (-not $Iscc) {
    Write-Host ""
    Write-Host "FAIL: ISCC.exe (Inno Setup 6) was not found."
    Write-Host "      Install it, then re-run:"
    Write-Host "        choco install innosetup --no-progress -y    (or the official installer)"
    Write-Host "      Or point at it directly:  -Iscc 'C:\path\to\ISCC.exe'"
    exit 1
}
Write-Host "iscc   : $Iscc"

# -- 4. compile --------------------------------------------------------------
# /D passes the build inputs so the .iss never has to guess a path or a version.
$isccArgs = @(
    "/Qp",
    "/DSrcDir=$Payload",
    "/DOutDir=$Dist",
    "/DAppVersion=$numeric",
    "/DBuildTag=$extra",
    $Iss
)
Write-Host ""
Write-Host "=== compiling installer ==="
& $Iscc @isccArgs 2>&1 | ForEach-Object { Write-Host "  $_" }
$code = $LASTEXITCODE
if ($code -ne 0) { Write-Host "FAIL: ISCC exited $code"; exit 1 }

$setup = Join-Path $Dist ("ace-{0}-windows-amd64-setup.exe" -f $Version)
if (-not (Test-Path $setup)) {
    Write-Host "FAIL: ISCC reported success but $setup is missing."
    exit 1
}
$setupMb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "installer: $setup"
Write-Host "size     : $setupMb MB  (payload $payloadMb MB)"

# -- 5. portable zip (same payload, for people who prefer no installer) -------
if (-not $NoZip) {
    $zip = Join-Path $Dist ("ace-{0}-windows-amd64.zip" -f $Version)
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $Payload '*') -DestinationPath $zip -Force
    Write-Host ("zip      : {0}  ({1} MB)" -f $zip, [math]::Round((Get-Item $zip).Length / 1MB, 1))
}

Write-Host ""
Write-Host "OK: installer built. The payload itself was validated by build_exe.ps1's smoke gate,"
Write-Host "    not by this step -- this step only wraps it."
exit 0
