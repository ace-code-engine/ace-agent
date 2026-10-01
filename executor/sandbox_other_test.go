//go:build !windows

package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

// TestProcessGroupKill 在真 POSIX 内核上验证 Tier-0 的整树回收：prepare（Setpgid）+
// killTree（kill(-pgid, SIGKILL)）必须连孙进程一起杀掉 —— 旧实现 Process.Kill 只杀
// 直接子进程，孙进程会成孤儿。CI 的 ubuntu job 会跑它；本机靠 WSL2 真内核也能跑。
func TestProcessGroupKill(t *testing.T) {
	if testing.Short() {
		t.Skip("short 模式跳过进程树测试")
	}
	dir, err := os.MkdirTemp("", "ace-pgkill-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)
	cpidPath := filepath.Join(dir, "cpid")
	gpidPath := filepath.Join(dir, "gpid")

	// sh 当组长（Setpgid），后台起一个 sleep 当孙进程：两者同一进程组。这样 killTree
	// 对整组发 SIGKILL 时，孙进程必须一起死 —— 这正是旧 Process.Kill 会漏掉的那一半。
	cmd := exec.Command("sh", "-c",
		"echo $$ > '"+cpidPath+"'; sleep 60 & echo $! > '"+gpidPath+"'; wait")
	cmd.Dir = dir
	// 只测进程组整树回收：直接 setProcessGroup，不走 processConfinement.prepare 里的
	// landlock/seccomp re-exec（那条 re-exec 与 sh -c 内联命令的 pid 文件写入有交互，
	// 会让本测试的前提——孙进程 pid 文件落盘——在 5s 内不成立）。re-exec 本身另有
	// TestLandlockWriteIsolation / TestSeccompNetworkDenial 覆盖。
	setProcessGroup(cmd)
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	// 失败兜底：别留一个 runaway 的 sleep 60（测试红了也不能给机器留孤儿）。
	defer func() {
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		_ = cmd.Wait()
	}()

	gpid := waitForPidFile(t, gpidPath)
	cpid := cmd.Process.Pid
	if gpid <= 0 || gpid == cpid {
		t.Fatalf("孙进程 pid 异常：gpid=%d cpid=%d", gpid, cpid)
	}
	if err := syscall.Kill(gpid, 0); err != nil {
		t.Fatalf("测试前提不成立：孙进程没活着（%v）", err)
	}

	method, err := killProcessTree(cmd)
	if err != nil {
		t.Fatalf("killTree 失败：%v", err)
	}
	if method != "SIGKILL(-pgid)" {
		t.Fatalf("kill_method = %q，非 Windows Tier-0 应为 SIGKILL(-pgid)", method)
	}
	_ = cmd.Wait()

	// 孙进程必须已被整树回收。kill(pid,0) 在 zombie 尚未被 init 收尸时仍返回 0，
	// 所以轮询到 ESRCH（孤儿被收尸通常是毫秒级）。
	deadline := time.Now().Add(3 * time.Second)
	for {
		if err := syscall.Kill(gpid, 0); err == syscall.ESRCH {
			return // 成功：孙进程没了
		}
		if time.Now().After(deadline) {
			t.Fatalf("孙进程 %d 在 killTree 后仍存活（整树回收失败，成了孤儿）", gpid)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

// waitForPidFile 有界地等 pid 文件出现并解析（测试前提：孙进程真的起来了）。
func waitForPidFile(t *testing.T, path string) int {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for {
		b, err := os.ReadFile(path)
		if err == nil {
			if pid, err := strconv.Atoi(strings.TrimSpace(string(b))); err == nil && pid > 0 {
				return pid
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("pid 文件 %s 没在 5s 内出现", path)
		}
		time.Sleep(20 * time.Millisecond)
	}
}
