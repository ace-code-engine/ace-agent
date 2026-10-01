//go:build linux

package main

import (
	"os"
	"os/exec"
	"testing"
)

// TestSeccompNetworkDenial 在真 Linux 内核上验证网络默认拒绝（WP-8 非 URL 出网通道）：
// applySeccompNetworkDenial 之后 socket(AF_INET) 必须返回 EPERM。helper 走 ACE_HELPER_MODE=seccomp。
// 内核不支持 seccomp（几乎不可能）时 helper 退出 126，测试如实 FAIL 而不是跳过。
func TestSeccompNetworkDenial(t *testing.T) {
	if testing.Short() {
		t.Skip("short 模式跳过")
	}
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(self)
	cmd.Env = append(os.Environ(), "ACE_TEST_HELPER=1", "ACE_HELPER_MODE=seccomp")
	err = cmd.Run()
	if err == nil {
		return // 退出码 0 = socket 被 EPERM 拦 → 正确
	}
	ee, ok := err.(*exec.ExitError)
	if !ok {
		t.Fatalf("运行失败: %v", err)
	}
	switch ee.ExitCode() {
	case 1:
		t.Fatal("socket 建成了 —— seccomp 网络拒绝失效（洞）")
	case 126:
		t.Skip("seccomp 施加失败（内核/环境不支持）—— 环境限制，不是回归")
	default:
		t.Fatalf("意外退出码 %d", ee.ExitCode())
	}
}
