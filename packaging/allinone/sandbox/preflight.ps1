# preflight.ps1 - can THIS Windows host run the virtualization base (CubeSandbox / KVM microVM)?
#
# ASCII only (PS 5.1 reads .ps1 as the system codepage without a BOM).
# Prints a verdict instead of letting the user find out by a broken install.
$ErrorActionPreference = 'Continue'

Write-Host "== Base preflight (CubeSandbox needs KVM = a Linux kernel feature) ==" -ForegroundColor Cyan

$verdict = 'remote'
$cs = Get-CimInstance Win32_ComputerSystem
Write-Host ("  host : {0} / {1}" -f $cs.Manufacturer, $cs.Model)

$hyper = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
Write-Host ("  hypervisor present (this OS is itself a guest when True): {0}" -f $hyper)

$cpu = Get-CimInstance Win32_Processor
$fw = $cpu.VirtualizationFirmwareEnabled
$slat = $cpu.SecondLevelAddressTranslationExtensions
Write-Host ("  CPU virtualization exposed to this OS: {0}   SLAT: {1}" -f $fw, $slat)

$wsl = ''
try { $wsl = (wsl -l -v 2>&1 | Out-String) } catch { $wsl = '' }
if ($wsl -match 'Ubuntu|Debian|kali|alpine') {
    Write-Host "  WSL2 distro found - a base inside WSL2 also needs NESTED virtualization from the outer host."
} elseif ($wsl) {
    Write-Host "  WSL2 present, but only Docker Desktop's own distro - not a usable Linux for the base."
}

Write-Host ""
if ($fw -eq $true) {
    Write-Host "VERDICT: this box may be able to run the base inside WSL2 (nested virtualization looks available)." -ForegroundColor Green
    Write-Host "         Install a Linux distro (wsl --install -d Ubuntu), then: sudo bash sandbox/preflight.sh"
    $verdict = 'maybe'
} else {
    Write-Host "VERDICT: this box CANNOT run the base (no virtualization extensions exposed to Windows)." -ForegroundColor Yellow
    Write-Host "         KVM microVMs need bare-metal Linux or a host with nested virtualization switched on."
    Write-Host ""
    Write-Host "Two ways forward:" -ForegroundColor Cyan
    Write-Host "  A) Put the base on a bare-metal Linux box and point this machine at it (shape B, recommended):"
    Write-Host "     on the Linux box:  sudo bash sandbox/preflight.sh && bash sandbox/setup-sandbox.sh"
    Write-Host "     it prints ACE_SANDBOX_API=http://<host>:3000 - put that in your host MCP config env."
    Write-Host "  B) Skip the base for now: the MCP layer still gives permission/audit/scan; only"
    Write-Host "     ace_sandbox_exec stays refused (Tier 0) until a base is reachable."
}

Write-Host ""
Write-Host "Nothing here changes your machine. Next: powershell -File setup-all.ps1"
exit 0
