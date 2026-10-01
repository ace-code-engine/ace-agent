//go:build !linux

package main

import "errors"

// applySeccompNetworkDenial 的 non-Linux stub：seccomp 是 Linux 原语。
// 只被 linux 专属的 re-exec 与测试引用，非 Linux 平台永远走不到真实逻辑。
func applySeccompNetworkDenial() error {
	return errors.New("seccomp is Linux-only")
}

// seccompSocketProbe 的 non-Linux stub：网络拒绝不可用。
func seccompSocketProbe() int {
	return 126
}
