//go:build !windows

package main

// sandbox_other.go —— 非 Windows 平台的 Tier-1 占位 + Tier-0 进程组终止。
//
// sandboxInventory 已经把 tier1_job_object 列入 unavailable，正常路径不会走到这里；
// 保留这个实现只是为了让 resolveConfinement 在所有平台都能编译。
// Linux/macOS 的强隔离（seccomp / seatbelt）按 ADR-002 属于后续档位，不在此文件冒充。

import (
	"os/exec"
	"syscall"
)

func newJobConfinement(lim execLimits) (confinement, string) {
	return nil, "job objects are a Windows-only primitive"
}

// setProcessGroup 把子进程放进它自己的进程组（Setpgid）：这样 killTree 能对整个
// 进程组发 SIGKILL，把 Tier-0 的"只杀直接子进程"提升成整树回收 —— 与 Windows Job
// Object 的整树口径对齐。超时/取消时孙进程不再成孤儿，长驻会话不再累积
// 「逃出去的孙进程攥着 stdout 句柄」导致的 goroutine/管道泄漏（见 run.go reapAfterKill）。
// 这只改变**终止**语义，不提供任何文件系统/网络边界（那些要等 tier2）。
func setProcessGroup(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

// killProcessTree 对子进程所在进程组发 SIGKILL。子进程已被 Setpgid 设为组长，
// 组 id == 它的 pid，所以 -pid 精确指向这一棵。
func killProcessTree(cmd *exec.Cmd) (string, error) {
	return "SIGKILL(-pgid)", syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
}

// selfIntegrityLevel 在非 Windows 上返回空串。
//
// 不返回 "n/a" 之类的占位文本：`integrity_level` 是 omitempty 字段，空串等于
// "这个平台没有这个概念，别拿它做判断"，而一个占位字符串会让宿主的日志和告警
// 规则去解析一个没有意义的值。
func selfIntegrityLevel() string { return "" }
