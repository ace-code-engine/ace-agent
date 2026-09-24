# ============================================================================
# build_exe.ps1 -- build and SMOKE-TEST the ACE Windows release (PyInstaller).
#
# WHY THE SMOKE GATE EXISTS
#   A frozen build fails in ways a source run never shows: resource files that
#   were never bundled, hidden imports that only resolve at runtime, and code
#   that assumes sys.executable is a Python interpreter. Shipping an exe that
#   was never run is how you find those out from users. So this script will not
#   report success without running the packaged ace.exe through real checks.
#
# ASCII-ONLY ON PURPOSE. Windows PowerShell 5.1 reads a BOM-less script as ANSI;
#   this repository has already been bitten twice by that (see CHANGELOG
#   v3.40.2 and the REL-03 note). Keep it ASCII, comments included.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_exe.ps1
#   ... -Python C:\path\to\python.exe     pick the interpreter to freeze with
#   ... -Clean                            wipe build/ and dist/ first
#   ... -SkipSmoke                        build only (prints a loud warning)
#
# REQUIREMENTS
#   PyInstaller must be importable by the chosen interpreter:
#       <python> -m pip install pyinstaller
#   Freezing with a 3.10-3.12 interpreter is safer than 3.13 for third-party
#   wheels, but the core is pure stdlib so any 3.10+ should work.
#
# EXIT: 0 = built AND every smoke scenario passed. 1 = anything failed.
# ============================================================================
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$Clean,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Continue'
$Here  = Split-Path -Parent $PSCommandPath       # .../ace/packaging
$Repo  = Split-Path -Parent $Here                # .../ace
$Dist  = Join-Path $Repo 'dist'
$Build = Join-Path $Repo 'build'
$Spec  = Join-Path $Here 'ace.spec'

Write-Host "repo      : $Repo"
Write-Host "spec      : $Spec"

# -- 1. interpreter ----------------------------------------------------------
if (-not $Python) {
    $cands = @()
    if ($env:ACE_PYTHON) { $cands += $env:ACE_PYTHON }
    $cands += 'C:\aider_env\Scripts\python.exe'
    $cands += (Join-Path $Repo '.ace_env\Scripts\python.exe')
    $cands += (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    $Python = $cands | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Python -or -not (Test-Path $Python)) {
    Write-Host "FAIL: no usable interpreter. Pass -Python <path> or set ACE_PYTHON."
    exit 1
}
Write-Host "interpreter: $Python"

# -- 2. PyInstaller present? -------------------------------------------------
$pyi = (& $Python -c "import importlib.util as u; print('yes' if u.find_spec('PyInstaller') else 'no')" 2>&1) -join ''
if ($pyi.Trim() -ne 'yes') {
    Write-Host ""
    Write-Host "FAIL: PyInstaller is not importable by this interpreter."
    Write-Host "      Install it, then re-run:"
    Write-Host "        `"$Python`" -m pip install pyinstaller"
    Write-Host ""
    Write-Host "      If pip cannot reach an index, this machine is offline for PyPI and"
    Write-Host "      the build must run where the network works (or from a local wheel)."
    exit 1
}
$pyiVer = (& $Python -c "import PyInstaller; print(PyInstaller.__version__)" 2>&1) -join ''
Write-Host "PyInstaller: $($pyiVer.Trim())"

# -- 3. clean ----------------------------------------------------------------
if ($Clean) {
    foreach ($d in @($Dist, $Build)) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue; Write-Host "removed $d" }
    }
}

# -- 4. build ----------------------------------------------------------------
# --noconfirm: the spec drives the layout; we do not want an interactive prompt
# in a script. --clean: drop PyInstaller's own cache so a stale hook cannot
# silently keep a removed module in the bundle.
Write-Host ""
Write-Host "=== building (this takes a few minutes) ==="
Push-Location $Repo
try {
    & $Python -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Build $Spec 2>&1 |
        Tee-Object -Variable buildOut | Select-Object -Last 25
    $buildCode = $LASTEXITCODE
} finally { Pop-Location }
if ($buildCode -ne 0) { Write-Host "FAIL: PyInstaller exited $buildCode"; exit 1 }

$ExePath = Join-Path $Dist 'ace\ace.exe'
if (-not (Test-Path $ExePath)) { Write-Host "FAIL: expected artifact not found: $ExePath"; exit 1 }
$sizeMb = [math]::Round(((Get-ChildItem (Join-Path $Dist 'ace') -Recurse -File |
    Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host ""
Write-Host "artifact : $ExePath"
Write-Host "size     : $sizeMb MB (whole folder)"

if ($SkipSmoke) {
    Write-Host ""
    Write-Host "WARN: -SkipSmoke was passed. This build has NOT been run."
    Write-Host "      Do not publish it as working. Re-run without -SkipSmoke."
    exit 0
}

# -- 5. smoke ----------------------------------------------------------------
# Every scenario is judged on: exit code 0, no traceback, no UnicodeEncodeError,
# no wrong glyphs, and the expected user-visible text actually present. A frozen
# build can pass "it starts" while failing to find prompts/ or locales/, so the
# assertions look for CONTENT, not just for a clean exit.
$evidence = Join-Path $Repo 'packaging\_smoke'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$results = @()

function Invoke-Smoke {
    param([string]$Name, [string[]]$Args, [string]$Mark)
    $outFile = Join-Path $evidence ("{0}.txt" -f ($Name -replace '[^A-Za-z0-9]', '_'))
    if (Test-Path $outFile) { Remove-Item $outFile -Force }
    Write-Host ""
    Write-Host "[smoke] $Name"
    Write-Host "        $ExePath $($Args -join ' ')"
    $p = Start-Process -FilePath $ExePath -ArgumentList $Args -NoNewWindow -Wait -PassThru `
         -RedirectStandardOutput $outFile -RedirectStandardError "$outFile.err"
    $code = $p.ExitCode
    $raw = ''
    if (Test-Path $outFile) { $raw = Get-Content $outFile -Raw -Encoding UTF8 }
    $err = ''
    if (Test-Path "$outFile.err") { $err = Get-Content "$outFile.err" -Raw -Encoding UTF8 }
    $all = "$raw`n$err"
    $okMark   = $all -match [regex]::Escape($Mark)
    $okClean  = -not ($all -match 'Traceback \(most recent call last\)')
    $okEnc    = -not ($all -match 'UnicodeEncodeError')
    $okMojib  = -not ($all -match ([char]0xFFFD))
    $ok = ($code -eq 0) -and $okMark -and $okClean -and $okEnc -and $okMojib
    $script:results += [pscustomobject]@{
        scenario = $Name; exit = $code; mark = $okMark;
        clean = $okClean; encoding = $okEnc; verdict = $(if ($ok) { 'PASS' } else { 'FAIL' })
    }
    Write-Host ("        exit={0}  mark={1}  clean={2}  encoding={3}  -> {4}" -f `
                $code, $okMark, $okClean, $okEnc, $(if ($ok) { 'PASS' } else { 'FAIL' }))
    if (-not $ok) {
        Write-Host "        --- output tail (raw evidence: $outFile) ---"
        ($all -split "`r?`n" | Select-Object -Last 15) | ForEach-Object { Write-Host "        $_" }
    }
}

# 1) --version: proves the exe starts at all (no resource access yet).
Invoke-Smoke -Name 'version' -Args @('--version') -Mark 'v3.'

# 2) --preview: draws the landing screen. This is the one that catches MISSING
#    RESOURCES - it reads locales/ for every label and assets/ for the logo.
Invoke-Smoke -Name 'preview' -Args @('--preview', '--preview-width', '80') -Mark 'ACE'

# 3) offline end-to-end with the scripted model, a real tool round trip.
$ws = Join-Path $evidence 'agent_ws'
New-Item -ItemType Directory -Force -Path $ws | Out-Null
Invoke-Smoke -Name 'mock_turn' -Args @('--mock', '--no-tui', '--permission', 'readonly',
                                      '--project-root', $ws, '--input', 'what time is it') `
             -Mark 'Agent'

# 4) the honest 501: code_execute must SAY it is unavailable in this form,
#    instead of trying to run ace.exe as a Python interpreter.
Invoke-Smoke -Name 'code_execute_501' -Args @('--mock', '--no-tui', '--tools',
                                              '--permission', 'full',
                                              '--project-root', $ws,
                                              '--input', 'run this python code: print(1+1)') `
             -Mark 'code_execute'

Write-Host ""
Write-Host "==================== smoke summary ===================="
$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

$failed = @($results | Where-Object { $_.verdict -ne 'PASS' })
if ($failed.Count -gt 0) {
    Write-Host ("FAIL: {0}/{1} smoke scenarios failed -- do NOT publish this build" -f $failed.Count, $results.Count)
    exit 1
}
Write-Host ("OK: {0}/{0} smoke scenarios passed" -f $results.Count)
Write-Host ""
Write-Host "package to publish : $Dist\ace   (zip the folder)"
Write-Host "reminder           : code_execute is intentionally 501 in this form;"
Write-Host "                     --install-ui / --setup have no meaning when frozen."
exit 0
