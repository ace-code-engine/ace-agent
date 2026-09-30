#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_commits.py —— 汇总一段 git 历史，给写发布说明用（只读）。

技能 `release-notes` 的取证脚本：**只读**（只跑 `git log` / `git diff --stat`），
不改仓库、不联网。用法（在仓库根跑）：

    python <技能目录>/scripts/collect_commits.py [range]
    # range 例：v3.6.0..HEAD、HEAD~20..HEAD；省略 = 最近 30 条

输出三段：commit 清单 / 改动文件统计 / 疑似破坏性变更（关键字命中，需人工确认）。
"""

from __future__ import annotations

import subprocess
import sys

BREAKING_HINTS = ("BREAKING", "!:", "remove", "rename", "deprecat", "不再", "移除", "改名")
MAX_COMMITS = 200


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return f"<git 调用失败: {type(e).__name__}: {e}>"
    return (out.stdout or out.stderr or "").strip()


def main(argv) -> int:
    rng = argv[0] if argv else "HEAD~30..HEAD"
    print(f"范围: {rng}\n")
    log = _git("log", "--no-merges", "--pretty=format:%h %ad %s", "--date=short", rng)
    lines = [ln for ln in log.splitlines() if ln.strip()]
    print(f"== commit（{len(lines)} 条，最多显示 {MAX_COMMITS}）==")
    for ln in lines[:MAX_COMMITS]:
        print("  " + ln)
    print("\n== 改动文件统计 ==")
    print(_git("diff", "--stat", rng) or "<没有差异>")
    print("\n== 疑似破坏性变更（关键字命中，**需人工确认**）==")
    hits = 0
    for ln in lines:
        low = ln.lower()
        if any(h.lower() in low for h in BREAKING_HINTS):
            print("  ! " + ln)
            hits += 1
    if not hits:
        print("  （没有命中；这不代表没有破坏性变更 —— 还要看 diff）")
    print("\n提示: commit message 会写错/夸大，分类时以 diff 为准（references/style.md）")
    print(f"关键字: {', '.join(BREAKING_HINTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
