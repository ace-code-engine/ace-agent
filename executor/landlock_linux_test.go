//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// TestLandlockWriteIsolation 在真 Linux 内核上验证写隔离：工作区内可写、工作区外被内核拒。
// 子进程走 TestMain 的 helper（ACE_HELPER_MODE=landlock），那条路先 applyLandlock 再写文件。
// 内核太旧 / 无 landlock（EOPNOTSUPP）时 helper 退出 126，测试会如实 FAIL（不是跳过）——
// 因为 CI 的 ubuntu runner 与 WSL2 都有 landlock，这条契约应该成立。
func TestLandlockWriteIsolation(t *testing.T) {
	if testing.Short() {
		t.Skip("short 模式跳过")
	}
	ws, err := os.MkdirTemp("", "ace-landlock-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(ws)
	outside := filepath.Join(os.TempDir(), fmt.Sprintf("ace-landlock-out-%d", os.Getpid()))
	defer os.Remove(outside)

	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	run := func(target string) int {
		cmd := exec.Command(self)
		cmd.Env = append(os.Environ(),
			"ACE_TEST_HELPER=1", "ACE_HELPER_MODE=landlock",
			"ACE_LANDLOCK_WS="+ws, "ACE_LANDLOCK_TARGET="+target)
		_ = cmd.Run()
		return cmd.ProcessState.ExitCode()
	}

	in := filepath.Join(ws, "in.txt")
	if code := run(in); code != 0 {
		t.Fatalf("工作区内写应成功，exit=%d", code)
	}
	if _, err := os.Stat(in); err != nil {
		t.Fatalf("工作区内写后文件应在：%v", err)
	}

	run(outside) // 退出码不重要（内核拒写），只断言文件没出现
	if _, err := os.Stat(outside); err == nil {
		t.Fatalf("工作区外写应被 landlock 拒绝，但文件出现了：%s", outside)
	}
}
