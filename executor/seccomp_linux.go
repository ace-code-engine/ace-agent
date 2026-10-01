//go:build linux

package main

import (
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

// seccomp_linux.go —— WP-8「非 URL 出网通道」的 Linux 半边：给 Go 执行器的子进程
// 施加"网络默认拒绝"。之前出网闸门只管 URL 工具（api_post/search/web_fetch），
// terminal_exec / code_execute 的子进程能直接 curl / 建 socket，绕开闸门。
// 现在与 landlock 写隔离一起在 re-exec 里施加：一个子进程既不能写工作区之外，也不能出网。
//
// 纯 syscall、零外部依赖（同 landlock）；seccomp 跨 execve 继承，所以"先施加再 exec"
// 那条路把过滤一并带进真实命令。

const (
	prSetNoNewPrivs        = 38 // PR_SET_NO_NEW_PRIVS
	seccompSetModeFilter   = 1  // SECCOMP_SET_MODE_FILTER
	seccompFilterFlagTsync = 1  // SECCOMP_FILTER_FLAG_TSYNC

	bpfLdWAbs  = 0x20 // BPF_LD | BPF_W | BPF_ABS
	bpfJmpJeqK = 0x15 // BPF_JMP | BPF_JEQ | BPF_K
	bpfRetK    = 0x06 // BPF_RET | BPF_K

	seccompRetErrno = 0x00050000
	seccompRetAllow = 0x7fff0000
)

// sockFilter 与内核 struct sock_filter 逐字节对齐（u16 code / u8 jt / u8 jf / u32 k）。
type sockFilter struct {
	Code uint16
	Jt   uint8
	Jf   uint8
	K    uint32
}

// sockFprog 与内核 struct sock_fprog 对齐。
type sockFprog struct {
	Len    uint16
	Filter *sockFilter
}

// denyNetworkFilter 造一份"socket 系 syscall 一律 EPERM、其余放行"的经典 BPF。
// syscall.SYS_SOCKET 等由 Go 标准库按目标架构给出正确编号，无需手写 arch 常量。
func denyNetworkFilter() []sockFilter {
	blocked := []uint32{
		uint32(syscall.SYS_SOCKET),
		uint32(syscall.SYS_SOCKETPAIR),
		uint32(syscall.SYS_CONNECT),
		uint32(syscall.SYS_ACCEPT),
		uint32(syscall.SYS_ACCEPT4),
		uint32(syscall.SYS_BIND),
		uint32(syscall.SYS_LISTEN),
		uint32(syscall.SYS_SENDTO),
		uint32(syscall.SYS_RECVFROM),
		uint32(syscall.SYS_SENDMSG),
		uint32(syscall.SYS_RECVMSG),
	}
	// 布局：0 = load syscall nr；1..N = JEQ（命中跳到 deny）；N+1 = allow；N+2 = deny。
	deny := 1 + len(blocked) + 1
	prog := []sockFilter{{Code: bpfLdWAbs, K: 0}}
	for i, nr := range blocked {
		idx := 1 + i
		// JEQ：命中跳 deny（jt = deny - idx - 1），未命中落到下一条（jf=0）。
		prog = append(prog, sockFilter{Code: bpfJmpJeqK, Jt: uint8(deny - idx - 1), K: nr})
	}
	prog = append(prog, sockFilter{Code: bpfRetK, K: seccompRetAllow})
	prog = append(prog, sockFilter{Code: bpfRetK, K: seccompRetErrno | 1}) // 1 = EPERM
	return prog
}

// applySeccompNetworkDenial 让**调用进程**从此无法创建/连接任何 socket。
// TSYNC 把过滤器同步到全部线程（Go 运行时是多线程的，避免 goroutine 换线程后漏过滤）。
func applySeccompNetworkDenial() error {
	if _, _, errno := syscall.Syscall(syscall.SYS_PRCTL, prSetNoNewPrivs, 1, 0); errno != 0 {
		return fmt.Errorf("prctl(NO_NEW_PRIVS): %v", errno)
	}
	prog := denyNetworkFilter()
	fprog := sockFprog{Len: uint16(len(prog)), Filter: &prog[0]}
	if _, _, errno := syscall.Syscall(seccompSyscallNo, seccompSetModeFilter,
		seccompFilterFlagTsync, uintptr(unsafe.Pointer(&fprog))); errno != 0 {
		return fmt.Errorf("seccomp(SET_MODE_FILTER): %v", errno)
	}
	return nil
}

// seccompSocketProbe 是测试 helper 的落点：施加网络拒绝后试建一个 AF_INET socket。
// 返回码：0 = 被 EPERM 拦（正确）· 1 = socket 建成（洞）· 126 = seccomp 施加失败 · 2 = 其它。
func seccompSocketProbe() int {
	if err := applySeccompNetworkDenial(); err != nil {
		fmt.Fprintln(os.Stderr, "seccomp:", err)
		return 126
	}
	fd, err := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, 0)
	if err == nil {
		_ = syscall.Close(fd)
		return 1 // socket 建成了 → 网络拒绝失效
	}
	if err == syscall.EPERM {
		return 0 // 被 EPERM 拦 → 正确
	}
	fmt.Fprintln(os.Stderr, "socket:", err)
	return 2
}
