#!/bin/sh
# preflight.sh - can THIS Linux host run the virtualization base (CubeSandbox / KVM microVM)?
#
# Prints a verdict, not a guess. Exit codes:
#   0 = KVM usable, go ahead   2 = not usable (with the concrete fix)   3 = unknown
set -u

ok=0
say() { printf '%s\n' "$*"; }

say "== 底座前置检查（CubeSandbox 需要 KVM）=="
say "host: $(uname -srm)"

# 1) /dev/kvm 是唯一的硬判据：没有它，KVM microVM 起不来。
if [ -e /dev/kvm ]; then
    if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
        say "  OK   /dev/kvm 存在且可读写"
    else
        say "  WARN /dev/kvm 存在但当前用户不可读写 —— 需要把用户加进 kvm 组（sudo usermod -aG kvm \$USER 后重登）"
        ok=1
    fi
else
    say "  FAIL 没有 /dev/kvm —— 这台机器不能跑 KVM microVM"
    ok=2
fi

# 2) CPU 虚拟化标志：解释"为什么没有 /dev/kvm"，并给出修法。
if grep -qE '(^flags|^Features).*(vmx|svm)' /proc/cpuinfo 2>/dev/null; then
    say "  OK   CPU 暴露了 vmx/svm（虚拟化扩展在位）"
else
    say "  FAIL CPU 没有暴露 vmx/svm —— 通常是在虚拟机里且宿主没开嵌套虚拟化"
    say "       修法：宿主打开嵌套虚拟化（VMware: vhv.enable=TRUE；KVM: 宿主 kvm_intel 的 nested=1；"
    say "             云厂商：换支持嵌套虚拟化的实例规格），或者把底座装在别处（形态 B 远程共用）"
    [ "$ok" -eq 0 ] && ok=2
fi

# 3) 内核模块（有的发行版没自动加载）
if [ "$ok" -ne 2 ] && ! lsmod 2>/dev/null | grep -q '^kvm'; then
    say "  WARN 没看到 kvm 模块 —— 可能需要 modprobe kvm_intel / kvm_amd"
fi

# 4) 容器/特权：KVM microVM 要能建 tap 设备与网络命名空间
if [ -r /proc/self/status ] && grep -qE '^CapEff:\s*0*$' /proc/self/status; then
    say "  WARN 当前进程无 capability（在受限容器里？）—— 底座需要 root 或等价权限"
fi

say ""
case "$ok" in
    0) say "判定：**可以装底座**（形态 A）。下一步：sudo bash setup-sandbox.sh" ;;
    1) say "判定：**能用，但要先修权限**（见上面 WARN）。" ;;
    2) say "判定：**这台机器不能当底座**。两条出路："
       say "  · 形态 B（推荐）：在一台裸金属 Linux 上装底座，本机只挂 MCP（配 ACE_SANDBOX_API 指向它）"
       say "  · 无 KVM 的 Linux 云 VM 还有 CubeSandbox 的 PVM 模式（自建内核，较重）："
       say "    见上游 deploy/pvm/，或 one-click 的 CUBE_PVM_ENABLE=1" ;;
    *) say "判定：未知（见上面输出）" ;;
esac
exit "$ok"
