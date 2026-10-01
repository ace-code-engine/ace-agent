//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"
	"unsafe"
)

// applyLandlockWriteIsolation 让**调用进程自己**从此只能在工作区内写。必须在子进程里调
// （restrict_self 只作用于调用者），所以它只能由 re-exec 那条路进来。
func applyLandlockWriteIsolation(workspace string) error {
	var attr landlockRulesetAttr
	attr.handledAccessFS = landlockWriteRights
	fd, _, errno := syscall.Syscall(landlockCreateRuleset,
		uintptr(unsafe.Pointer(&attr)), uintptr(unsafe.Sizeof(attr)), 0)
	if errno != 0 {
		return fmt.Errorf("landlock_create_ruleset: %v", errno)
	}
	defer syscall.Close(int(fd))

	wd, err := os.Open(workspace)
	if err != nil {
		return fmt.Errorf("open workspace %q: %w", workspace, err)
	}
	defer wd.Close()
	var rule landlockPathBeneathAttr
	rule.allowedAccess = landlockWriteRights
	rule.parentFd = int32(wd.Fd())
	_, _, errno = syscall.Syscall6(landlockAddRule,
		fd, landlockRulePathBeneath, uintptr(unsafe.Pointer(&rule)), 0, 0, 0)
	if errno != 0 {
		return fmt.Errorf("landlock_add_rule: %v", errno)
	}

	_, _, errno = syscall.Syscall(landlockRestrictSelf, fd, 0, 0)
	if errno != 0 {
		return fmt.Errorf("landlock_restrict_self: %v", errno)
	}
	return nil
}

// landlockApplyEntry 是 re-exec 的落点（main.go 在最前面调它）。返回 true 表示"这是
// landlock 重入，已经 apply + exec，main 不该继续往下走"。
func landlockApplyEntry() bool {
	if len(os.Args) < 5 || os.Args[1] != "--landlock-apply" || os.Args[3] != "--" {
		return false
	}
	ws := os.Args[2]
	rest := os.Args[4:]
	if err := applyLandlockWriteIsolation(ws); err != nil {
		fmt.Fprintln(os.Stderr, "landlock apply failed:", err)
		os.Exit(126)
	}
	// syscall.Exec 不搜 PATH（只收绝对/相对路径），得先用 exec.LookPath 解析。
	bin, err := exec.LookPath(rest[0])
	if err != nil {
		fmt.Fprintln(os.Stderr, "landlock lookpath failed:", err)
		os.Exit(127)
	}
	if err := syscall.Exec(bin, rest, os.Environ()); err != nil {
		fmt.Fprintln(os.Stderr, "landlock exec failed:", err)
		os.Exit(127)
	}
	return true
}
