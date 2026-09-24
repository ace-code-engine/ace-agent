# ============================================================================
# check_packaging.ps1 -- every constraint the packaging script must satisfy,
# checked in one shot BEFORE handing anything to CI.
#
# WHY THIS EXISTS
#   packaging/build_exe.ps1 has now broken CI three times, all on the same axis:
#   it is run by Windows PowerShell 5.1 on the runner (via `powershell -File`)
#   while test_all.py runs it with pwsh on the dev machine. 5.1 reads a BOM-less
#   script as ANSI, so a single non-ASCII byte in that file turns into mojibake,
#   breaks quoting, and the whole script fails to PARSE -- a failure that is
#   invisible locally. Checking ASCII purity and parsing the file with 5.1 is
#   therefore not optional; it is the difference between "works here" and
#   "works on the runner".
#
# ASCII-ONLY ITSELF, for the same reason.
#
# USAGE: powershell -NoProfile -ExecutionPolicy Bypass -File packaging/check_packaging.ps1
# EXIT : 0 = all checks passed. 1 = at least one failed.
# ============================================================================
[CmdletBinding()]
param(
    [string]$Script = ""
)

$ErrorActionPreference = 'Continue'
$Here = Split-Path -Parent $PSCommandPath
$Repo = Split-Path -Parent $Here
if (-not $Script) { $Script = Join-Path $Here 'build_exe.ps1' }

$failures = @()
function Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
    if ($Ok) {
        Write-Host ("  PASS  " + $Name)
    } else {
        Write-Host ("  FAIL  " + $Name + $(if ($Detail) { "  -- " + $Detail } else { "" }))
        $script:failures += $Name
    }
}

Write-Host "checking: $Script"
Write-Host ""

# -- 1. ASCII purity --------------------------------------------------------
# The one that keeps biting. A single byte > 127 breaks the CI parse.
$bytes = [System.IO.File]::ReadAllBytes($Script)
$nonAscii = ($bytes | Where-Object { $_ -gt 127 } | Measure-Object).Count
$detail = ""
if ($nonAscii -gt 0) {
    # Name the offending lines so the fix is obvious.
    $lines = [System.IO.File]::ReadAllLines($Script, [System.Text.Encoding]::UTF8)
    $bad = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].ToCharArray() | Where-Object { [int]$_ -gt 127 }) {
            $bad += ("L{0}" -f ($i + 1))
        }
    }
    $detail = ("non-ASCII bytes={0} on lines {1}" -f $nonAscii, ($bad -join ', '))
}
Check "build_exe.ps1 is pure ASCII (PowerShell 5.1 reads BOM-less as ANSI)" ($nonAscii -eq 0) $detail

# A BOM would also be a problem to reason about, even though 5.1 honours it.
$hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
Check "build_exe.ps1 has no BOM (one rule, no special cases)" (-not $hasBom)

# -- 2. parses under Windows PowerShell 5.1 ---------------------------------
# The check that would actually have caught all three CI failures.
$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$null, [ref]$errs)
$msg = ""
if ($errs -and $errs.Count) { $msg = (($errs | Select-Object -First 3 | ForEach-Object { $_.Message }) -join ' | ') }
Check "build_exe.ps1 parses under the current PowerShell" (-not ($errs -and $errs.Count)) $msg

# -- 3. the reserved-name trap ---------------------------------------------
# $Args / $Input / $Matches are automatic variables; using them as parameter
# names silently yields empty values (that was CI failure #2).
$src = [System.IO.File]::ReadAllText($Script, [System.Text.Encoding]::UTF8)
$reserved = @('$Args', '$Input', '$Matches', '$Error', '$Host', '$PWD')
$hits = @()
foreach ($r in $reserved) {
    if ($src -match ("param\([^)]*\[[^\]]+\]" + [regex]::Escape($r) + "\b")) { $hits += $r }
}
Check "no automatic variable used as a parameter name" ($hits.Count -eq 0) ($hits -join ', ')

# -- 4. no Start-Process for the smoke runs ---------------------------------
# Start-Process -ArgumentList joins with C-runtime quoting rules, which splits
# any argument containing spaces (that was CI failure #3).
Check "smoke runs use the call operator, not Start-Process" (-not ($src -match 'Start-Process\s+-FilePath\s+\$ExePath'))

# -- 5. every mark is text the scenario really produces ---------------------
# Assertions about text that never appears cannot pass, however correct the
# package is (that was CI failure #4: a mark for a tool the scripted mock model
# never calls). Each mark below is verified against a real source run.
Write-Host ""
Write-Host "  -- verifying smoke marks against a real source run --"
Write-Host "    (the exe is run on CI; here we check the TEXT each scenario emits)"

$py = $null
foreach ($c in @($env:ACE_PYTHON, 'C:\aider_env\Scripts\python.exe',
                 (Join-Path $Repo '.ace_env\Scripts\python.exe'), 'python')) {
    if (-not $c) { continue }
    $cand = if (Test-Path -LiteralPath $c -PathType Leaf) { $c } else {
        (Get-Command $c -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -eq 'Application' } | Select-Object -First 1).Source
    }
    if ($cand -and (Test-Path $cand)) { $py = $cand; break }
}
if (-not $py) {
    Write-Host "  SKIP  no interpreter available for mark verification"
} else {
    $ws = Join-Path $Repo '.test_tmp\_harness\markcheck'
    New-Item -ItemType Directory -Force -Path $ws | Out-Null
    # Built from code points so this file stays ASCII, same as in build_exe.ps1.
    $currentTime = [string]([char]0x5F53 + [char]0x524D + [char]0x65F6 + [char]0x95F4)

    $cases = @(
        @{ n = 'version';      a = @('--version');                           m = 'ACE ' },
        @{ n = 'preview';      a = @('--preview', '--preview-width', '80');  m = 'ACE ' },
        @{ n = 'mock_turn';    a = @('--mock', '--no-tui', '--permission', 'readonly',
                                     '--project-root', $ws, '--input', 'what time is it'); m = $currentTime },
        @{ n = 'native_tools'; a = @('--mock', '--no-tui', '--tools', '--permission', 'full',
                                     '--project-root', $ws, '--input', 'what time is it');  m = $currentTime }
    )
    foreach ($c in $cases) {
        $argv = @((Join-Path $Repo 'ai_code.py')) + $c.a
        $out = (& $py @argv 2>&1 | Out-String)
        Check ("mark for '{0}' actually appears in the output" -f $c.n) ($out -match [regex]::Escape($c.m))
    }
}

Write-Host ""
if ($failures.Count -gt 0) {
    Write-Host ("FAIL: {0} check(s) failed -- do not hand this to CI" -f $failures.Count)
    exit 1
}
Write-Host "OK: all packaging checks passed"
exit 0
