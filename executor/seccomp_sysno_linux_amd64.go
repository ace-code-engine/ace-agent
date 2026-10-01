//go:build linux && amd64

package main

// seccomp syscall 号：amd64 = 317。Go 的 syscall 包不暴露 SYS_SECCOMP，这里补上。
// 用 build tag 而非 runtime.GOARCH：不支持的目标架构会在编译期直接失败，而不是运行时
// 静默跳过 seccomp（那正是"安全为先"最忌讳的静默降级）。
const seccompSyscallNo = 317
