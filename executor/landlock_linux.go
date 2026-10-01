//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
	"sync"
	"syscall"
	"unsafe"
)

// landlockAvailable 探测一次：内核是否支持我们用到的 landlock 写权限位。
// ubuntu CI runner 上 landlock 可能被禁 / ABI 不同，此时 landlockWrap 应 no-op、
// 测试应跳过，而不是让每个命令都 re-exec 失败（那会连 TestProcessGroupKill 一起拖垮）。
var _landlockOnce sync.Once
var _landlockOK bool

func landlockAvailable() bool {
	_landlockOnce.Do(func() {
		var attr landlockRulesetAttr
		attr.handledAccessFS = landlockWriteRights
		fd, _, errno := syscall.Syscall(landlockCreateRuleset,
			uintptr(unsafe.Pointer(&attr)), uintptr(unsafe.Sizeof(attr)), 0)
		if errno != 0 {
			_landlockOK = false
			return
		}
		defer syscall.Close(int(fd))
		// 也试 add_rule（用 /tmp 当 parent）：create_ruleset 成功不代表 add_rule 也成功。
		// restrict_self 不可逆，这里不做，靠真实应用路径去验证。
		wd, err := os.Open(os.TempDir())
		if err != nil {
			_landlockOK = false
			return
		}
		defer wd.Close()
		var rule landlockPathBeneathAttr
		rule.allowedAccess = landlockWriteRights
		rule.parentFd = int32(wd.Fd())
		_, _, errno = syscall.Syscall6(landlockAddRule,
			fd, landlockRulePathBeneath, uintptr(unsafe.Pointer(&rule)), 0, 0, 0)
		_landlockOK = errno == 0
	})
	return _landlockOK
}

// applyLandlockWriteIsolation 让**调用进程自己**从此只能在工作区内写。必须在子进程里调
// （restrict_self 只作用于调用者），所以它只能由 re-exec 那条路进来。
func applyLandlockWriteIsolation(workspace string) error {
	// landlock_restrict_self 要求 NO_NEW_PRIVS（否则 EPERM）。WSL2 内核宽松放过了，
	// ubuntu runner 严格 → 这里显式设上（幂等，re-exec 路径里 seccomp 已设过也没关系）。
	if _, _, errno := syscall.Syscall(syscall.SYS_PRCTL, prSetNoNewPrivs, 1, 0); errno != 0 {
		return fmt.Errorf("prctl(NO_NEW_PRIVS): %v", errno)
	}
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
	// 网络默认拒绝（WP-8 非 URL 出网通道）—— 与 landlock 一起在 re-exec 里施加。
	if err := applySeccompNetworkDenial(); err != nil {
		fmt.Fprintln(os.Stderr, "seccomp apply failed:", err)
		os.Exit(126)
	}
	if ws != "" {
		if err := applyLandlockWriteIsolation(ws); err != nil {
			fmt.Fprintln(os.Stderr, "landlock apply failed:", err)
			os.Exit(126)
		}
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
