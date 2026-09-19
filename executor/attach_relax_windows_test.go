//go:build windows

package main

// attach_relax_windows_test.go —— 附加失败后的重试判据（2026-09-19 实测后新增）。
//
// 为什么单独一条测试：这两个函数决定了"什么时候值得放弃零竞态窗口重试一次"。
// 判宽了会在 TERMINATE/SET_QUOTA 也被拒的机器上白花一次进程创建、并把错误
// 掩盖成两次同样的失败；判窄了就退回"Tier-1 在受限令牌宿主里完全不可用"。
// 它是一条纯判定，值得被钉住 —— 与 ace_execpolicy 那条"判定与执行解耦"同一个理由。

import (
	"strings"
	"testing"
)

func TestCanAssignWithoutSuspend(t *testing.T) {
	cases := []struct {
		name    string
		missing []string
		want    bool
	}{
		{"只被拒 SUSPEND_RESUME → 放弃挂起启动值得重试",
			[]string{"PROCESS_SUSPEND_RESUME"}, true},
		{"TERMINATE 也被拒 → Assign 本身做不成，重试没意义",
			[]string{"PROCESS_SUSPEND_RESUME", "PROCESS_TERMINATE"}, false},
		{"SET_QUOTA 也被拒 → 同上",
			[]string{"PROCESS_SET_QUOTA"}, false},
		{"一个都没缺 → 根本不该走到这条重试路径",
			nil, false},
	}
	for _, c := range cases {
		if got := canAssignWithoutSuspend(&attachError{missing: c.missing}); got != c.want {
			t.Errorf("%s: got %v want %v", c.name, got, c.want)
		}
	}
}

func TestAttachErrorNamesDeniedRights(t *testing.T) {
	// 一次 OpenProcess 里的多个位是"与"语义：只说 "Access is denied" 的话，
	// 宿主会以为整个 Job Object 不可用 —— 实测就是把排查引向了完全错误的方向。
	e := &attachError{
		msg:     "OpenProcess failed: Access is denied.",
		denied:  true,
		missing: []string{"PROCESS_SUSPEND_RESUME"},
	}
	if !strings.Contains(e.Error(), "PROCESS_SUSPEND_RESUME") {
		t.Fatalf("错误信息必须点名被拒的访问位，否则宿主只能看到 Access is denied: %s", e.Error())
	}
	// 没有可报的访问位时不许伪造一个出来。
	plain := &attachError{msg: "OpenProcess failed: some other failure"}
	if strings.Contains(plain.Error(), "被拒的访问位") {
		t.Fatalf("没有实测到被拒的位时不该编一条出来: %s", plain.Error())
	}
}
