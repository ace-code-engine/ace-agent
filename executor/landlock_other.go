//go:build !linux

package main

import "fmt"

// landlock_other.go —— 非 Linux 平台的 re-exec 落点占位：永远不是 landlock 重入。
// 真正的实现在 landlock_linux.go；这里只是让 main.go 的 `landlockApplyEntry()` 与
// executor_test.go 的 helper case 在所有平台都能编译。landlockWrap 在 landlock.go
// 里已经用 runtime.GOOS 守卫成 no-op 了。
func landlockApplyEntry() bool { return false }

func applyLandlockWriteIsolation(workspace string) error {
	return fmt.Errorf("landlock is Linux-only")
}

// landlockAvailable 的 non-Linux stub：永远不可用（landlock 是 Linux 原语）。
func landlockAvailable() bool { return false }
