#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""count_todos.py —— 数一遍仓库里的 TODO/FIXME 及其分布（只读）。

技能 `repo-audit` 的取证脚本：**只读、不联网、不改任何文件**。
用法（在仓库根跑）：

    python <技能目录>/scripts/count_todos.py [目录] [--pattern TODO|FIXME]

输出每个目录的命中数（降序）+ 总数；-v 时逐条打印 `路径:行号: 原文`。
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

MARKERS = ("TODO", "FIXME", "HACK", "XXX")
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
             "dist", "build", ".mypy_cache", ".pytest_cache", ".ace_sessions"}
MAX_FILES = 20000
MAX_HITS = 500


def scan(root: Path, markers, verbose: bool) -> int:
    by_dir: Counter = Counter()
    hits = 0
    files = 0
    for p in root.rglob("*"):
        if files >= MAX_FILES or hits >= MAX_HITS:
            break
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".md",
                                    ".java", ".rb", ".sh", ".ps1", ".c", ".h", ".cpp"):
            continue
        files += 1
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if any(m in line for m in markers):
                hits += 1
                by_dir[str(p.parent.relative_to(root)) or "."] += 1
                if verbose:
                    print(f"{p.relative_to(root)}:{i}: {line.strip()[:120]}")
                if hits >= MAX_HITS:
                    break
    print(f"\n扫了 {files} 个文件，命中 {hits} 条"
          + (f"（已达上限 {MAX_HITS}，结果不完整）" if hits >= MAX_HITS else ""))
    for d, n in by_dir.most_common(15):
        print(f"  {n:5d}  {d}")
    return 0


def main(argv) -> int:
    verbose = "-v" in argv
    args = [a for a in argv if not a.startswith("-")]
    root = Path(args[0]).expanduser().resolve() if args else Path.cwd()
    marker_arg = None
    for a in argv:
        if a.startswith("--pattern"):
            marker_arg = a.split("=", 1)[1] if "=" in a else None
    markers = tuple(marker_arg.split("|")) if marker_arg else MARKERS
    if not root.is_dir():
        print(f"不是目录: {root}", file=sys.stderr)
        return 2
    print(f"根目录: {root}\n标记: {', '.join(markers)}")
    return scan(root, markers, verbose)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
