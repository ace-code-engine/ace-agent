package main

// landlock.go —— Linux 内核 5.13+（unprivileged）的**写隔离**档：子进程对工作区之外的
// 文件系统只有读/执行，没有任何写。这是"安全为先"从 Windows（Job Object）扩展到 Linux
// 的第一档：纯 syscall、零外部依赖、WSL2（真内核）可验。
//
// 本文件放**平台无关**的部分（常量 / 结构体 / re-exec 改写）。真正碰 syscall 的
// `applyLandlockWriteIsolation` 与 re-exec 落点 `landlockApplyEntry` 在
// landlock_linux.go / landlock_other.go 里 —— 因为 Windows 的 `syscall.Syscall` 签名
// 与 Unix 不同（多一个 nargs），放同一个文件编译不过。

import (
	"os"
	"os/exec"
	"runtime"
)

// x86_64 / arm64 的 Linux syscall 编号。
const (
	landlockCreateRuleset = 444
	landlockAddRule       = 445
	landlockRestrictSelf  = 446

	landlockRulePathBeneath = 1
)

// Landlock 文件访问权位（ABI v1 就有的子集）。
const (
	landlockAccessFSExecute    = 1 << 0
	landlockAccessFSWriteFile  = 1 << 1
	landlockAccessFSReadFile   = 1 << 2
	landlockAccessFSReadDir    = 1 << 3
	landlockAccessFSRemoveDir  = 1 << 4
	landlockAccessFSRemoveFile = 1 << 5
	landlockAccessFSMakeChar   = 1 << 6
	landlockAccessFSMakeDir    = 1 << 7
	landlockAccessFSMakeReg    = 1 << 8
	landlockAccessFSMakeSock   = 1 << 9
	landlockAccessFSMakeFifo   = 1 << 10
	landlockAccessFSMakeBlock  = 1 << 11
	landlockAccessFSMakeSym    = 1 << 12
	landlockAccessFSRefer      = 1 << 13
	landlockAccessFSTruncate   = 1 << 14
)

// 我们只**限制写**这一类。读/执行不放进 handled_access_fs，所以不受限制 ——
// 这样 python/git 照常能读系统库、能 exec，只有"写工作区之外"被内核直接拒掉。
// 最小、且诚实：这不是完备沙箱，是"写隔离"。
const landlockWriteRights = landlockAccessFSWriteFile |
	landlockAccessFSRemoveDir | landlockAccessFSRemoveFile |
	landlockAccessFSMakeChar | landlockAccessFSMakeDir |
	landlockAccessFSMakeReg | landlockAccessFSMakeSock |
	landlockAccessFSMakeFifo | landlockAccessFSMakeBlock |
	landlockAccessFSMakeSym | landlockAccessFSRefer | landlockAccessFSTruncate

type landlockRulesetAttr struct {
	handledAccessFS uint64
}

type landlockPathBeneathAttr struct {
	allowedAccess uint64
	parentFd      int32
}

// landlockWrap 把子进程改写成"先重入自己应用 landlock（写隔离）+ seccomp（网络默认拒绝），
// 再 exec 真实命令"。restrict_self 与 seccomp 都只作用于调用者，父进程代劳不了，所以走 re-exec：
// `/proc/self/exe --landlock-apply <workspace> -- <真实 argv>`。Setpgid 由 prepare 先设好，
// re-exec 之后再 syscall.Exec 同 PID、同进程组，整树回收不受影响。
// 只在 Linux 生效；其它平台 = no-op（如实不做，不装）。workspace 定不出时空串也照 re-exec：
// 那样只施 seccomp、跳过 landlock（网络拒绝不依赖工作区）。
func landlockWrap(cmd *exec.Cmd) {
	if runtime.GOOS != "linux" {
		return
	}
	// 内核不支持 landlock（如 ubuntu CI runner）时不 re-exec —— 否则每个命令都因
	// re-exec 里的 landlock 失败而 exit 126，把整个执行器拖垮。这里如实 no-op。
	if !landlockAvailable() {
		return
	}
	ws := cmd.Dir
	if ws == "" {
		if wd, err := os.Getwd(); err == nil {
			ws = wd
		}
	}
	self, err := os.Executable()
	if err != nil {
		return
	}
	real := cmd.Args
	cmd.Path = self
	cmd.Args = append([]string{self, "--landlock-apply", ws, "--"}, real...)
	cmd.Env = append(cmd.Env, "ACE_LANDLOCK_APPLY=1")
}
