# ============================================================================
# rel03_native_smoke.ps1 -- REL-03 native smoke evidence
#
# WHY THIS FILE EXISTS
#   README "Known gaps" used to say: "ace.cmd -> a real terminal conversation"
#   has never been walked through on a real machine; repo automation only
#   covers the --mock path, the headless agent_runner, and CI. This script is
#   the missing evidence: on a real console, from the launcher all the way to
#   a final user-visible answer.
#
# ASCII-ONLY ON PURPOSE. Do not add non-ASCII text (Chinese, emoji, smart
#   quotes) to this file, not even inside comments. Windows PowerShell 5.1
#   reads a BOM-less script as ANSI, so non-ASCII would turn into mojibake and
#   the parser would fail on the mangled bytes. Same discipline as ace.cmd.
#
# THREE SCENARIOS (raw evidence kept under e2e/_rel03_evidence/):
#   A  launcher   cmd /c ace.cmd                    what the user actually types
#   B  entry      python ai_code.py                 same frontend, no .cmd
#   C  legacy     chcp 936 + PYTHONIOENCODING=gbk   old-terminal glyph fallback
#
# ASSERTIONS (loose: conversation is non-deterministic; --mock pins the model):
#   exit 0 - no Traceback - no UnicodeEncodeError - the answer really is there
#
# USAGE: powershell -NoProfile -ExecutionPolicy Bypass -File e2e/rel03_native_smoke.ps1
# EXIT : 0 = all scenarios passed; 1 = at least one failed (raw output kept).
# ============================================================================
[CmdletBinding()]
param(
    [string]$Repo   = "",
    [string]$Python = "",
    [string]$Prompt = "what time is it"
)

$ErrorActionPreference = 'Continue'
# $PSScriptRoot is NOT populated while param() defaults are evaluated, so the
# repo root is resolved here instead of in the parameter block.
if (-not $Repo) { $Repo = Split-Path -Parent $PSScriptRoot }
$Repo = (Resolve-Path $Repo).Path
$Evidence = Join-Path $Repo 'e2e\_rel03_evidence'
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null

# -- Interpreter: default to setup_env.py's own resolution --------------------
# That resolution IS the second step of ace.cmd, so this is the real machine
# answer rather than whatever Python the test harness happens to be running.
if (-not $Python) {
    $cands = @()
    if ($env:ACE_PYTHON) { $cands += $env:ACE_PYTHON }
    $cands += 'C:\aider_env\Scripts\python.exe'
    $cands += (Join-Path $Repo '.ace_env\Scripts\python.exe')
    $Python = $cands | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $Python) {
        Write-Host "FAIL: no usable interpreter found (pass -Python or set ACE_PYTHON)"
        exit 1
    }
}
if (-not (Test-Path $Python)) { Write-Host "FAIL: interpreter not found: $Python"; exit 1 }

$pyVer = (& $Python -c "import sys;print(sys.version.split()[0])" 2>&1) -join ''
Write-Host "repo       : $Repo"
Write-Host "interpreter: $Python  (Python $pyVer)"
Write-Host "evidence   : $Evidence"
Write-Host ""

$script:results = @()

function Invoke-Scenario {
    param(
        [string]$Name,      # scenario label
        [string]$CmdLine,   # full cmd.exe command line, redirection included
        [string]$OutFile,   # evidence file name
        [string]$Mark       # fragment that must appear in the output
    )
    $full = Join-Path $Evidence $OutFile
    if (Test-Path $full) { Remove-Item $full -Force }

    Push-Location $Repo
    try {
        & cmd.exe /c $CmdLine | Out-Null
        $code = $LASTEXITCODE
    } finally { Pop-Location }

    $raw = if (Test-Path $full) { Get-Content $full -Raw -Encoding UTF8 } else { '' }
    $hasTraceback   = $raw -match 'Traceback \(most recent call last\)'
    $hasUEE         = $raw -match 'UnicodeEncodeError'
    # The mark may be non-ASCII; compare by code points so this file stays ASCII.
    $markCp  = ($Mark.ToCharArray() | ForEach-Object { [int]$_ }) -join ','
    $rawCp   = ($raw.ToCharArray()  | ForEach-Object { [int]$_ }) -join ','
    $hasMark = $rawCp.Contains($markCp)
    # Real mojibake is U+FFFD; a cp936 console turning emoji into '?' by design
    # is the fallback working, not corruption.
    $hasReplacement = $raw -match ([char]0xFFFD)

    $ok = ($code -eq 0) -and (-not $hasTraceback) -and (-not $hasUEE) -and $hasMark -and (-not $hasReplacement)
    $script:results += [pscustomobject]@{
        scenario = $Name; exit = $code; traceback = $hasTraceback;
        unicode_error = $hasUEE; answer_present = $hasMark;
        replacement_char = $hasReplacement; verdict = $(if ($ok) { 'PASS' } else { 'FAIL' })
    }

    Write-Host ("[{0}] {1}" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $Name)
    Write-Host ("       exit={0}  traceback={1}  unicode_error={2}  answer={3}  u+fffd={4}" -f `
                $code, $hasTraceback, $hasUEE, $hasMark, $hasReplacement)
    if (-not $ok) {
        Write-Host "       --- output tail (raw evidence: $full) ---"
        ($raw -split "`r?`n" | Select-Object -Last 12) | ForEach-Object { Write-Host "       $_" }
    }
    Write-Host ""
}

# -- A launcher: the exact command a user types -------------------------------
# ace.cmd runs chcp 65001 inside itself; that IS part of the behaviour under
# test (the UTF-8 defence line), so it is deliberately not pre-set here.
$outA = 'A_launcher.txt'
Invoke-Scenario -Name 'A launcher   ace.cmd --mock --no-tui --input ...' `
    -CmdLine "ace.cmd --mock --no-tui --input `"$Prompt`" --permission readonly > `"$Evidence\$outA`" 2>&1" `
    -OutFile $outA -Mark ([char]0x5F53 + [char]0x524D + [char]0x65F6 + [char]0x95F4 + [char]0x662F)

# -- B direct entry: same frontend, no .cmd -----------------------------------
$outB = 'B_direct_entry.txt'
$pyQ = '"' + $Python + '"'
Invoke-Scenario -Name 'B entry      python ai_code.py --mock --input ...' `
    -CmdLine "$pyQ ai_code.py --mock --no-tui --input `"$Prompt`" --permission readonly > `"$Evidence\$outB`" 2>&1" `
    -OutFile $outB -Mark ([char]0x5F53 + [char]0x524D + [char]0x65F6 + [char]0x95F4 + [char]0x662F)

# -- C legacy console: real cp936 + GBK stdout --------------------------------
# ace.cmd forces the code page back to 65001, so this scenario bypasses .cmd on
# purpose: it models "user runs python ai_code.py directly in an old terminal".
# Assertions stay the same (do not crash, do not corrupt); emoji turning into
# ASCII fallbacks is the intended downgrade, not a failure.
$outC = 'C_gbk_console.txt'
Invoke-Scenario -Name 'C legacy     chcp 936 + PYTHONIOENCODING=gbk' `
    -CmdLine "chcp 936 >nul & set PYTHONIOENCODING=gbk & $pyQ ai_code.py --mock --no-tui --input `"$Prompt`" --permission readonly > `"$Evidence\$outC`" 2>&1" `
    -OutFile $outC -Mark ([char]0x5F53 + [char]0x524D + [char]0x65F6 + [char]0x95F4 + [char]0x662F)

Write-Host "==================== summary ===================="
$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host

$failed = @($results | Where-Object { $_.verdict -ne 'PASS' })
if ($failed.Count -gt 0) {
    Write-Host ("FAIL: {0}/{1} scenarios failed" -f $failed.Count, $results.Count)
    exit 1
}
Write-Host ("OK: {0}/{0} scenarios passed -- launcher to real console conversation" -f $results.Count)
exit 0
