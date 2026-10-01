#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_pack_contents.py —— 校验一个**已解压**的包内容是否完整（发布流水线用）。

为什么不写成 workflow 里的内联 heredoc：顶格的 heredoc 会打断 YAML 的块缩进
（第一版 workflow 就是这么被 GitHub 的语法校验拒掉的），而且内联的东西本地没法单独跑。
这个脚本本地/CI 同一个入口：

    python packaging/verify_pack_contents.py <解压目录> [--with-base]

`--with-base` = 这个包是一体包，必须**确实多出**底座那一半（少了就退化成 MCP 包）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

#: 任何包都必须有的（跑 --mcp 需要的运行时 + 该包自己的东西）
REQUIRED = (
    "ai_code.py", "execution_layer.py", "agent_runner.py",
    "core", "tools", "cli", "ui", "locales", "prompts",
    "VERSION", "README-MCP.md", "ace-mcp.cmd", "ace-mcp.sh",
    "verify-mcp.py", "install-cline.ps1",
    "configs/cline_mcp_settings.json", "configs/claude_desktop_config.json",
    "configs/cursor_mcp.json", "configs/generic-mcp.json",
)
#: 一体包额外要有
BASE_EXTRA = (
    "README-ALLINONE.md", "setup-all.ps1", "setup-all.sh",
    "sandbox/preflight.sh", "sandbox/preflight.ps1",
    "sandbox/setup-sandbox.sh", "sandbox/verify-sandbox.py",
)
#: 有意**不带**的（带了说明打包口径漂了）
FORBIDDEN = ("test_all.py", "frontend", "docs", "demo", "benchmarks", "e2e", "skills")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    with_base = "--with-base" in sys.argv
    if not args:
        print("usage: verify_pack_contents.py <extracted-dir> [--with-base]")
        return 2
    root = Path(args[0])
    if not root.is_dir():
        print(f"FAIL not a directory: {root}")
        return 1

    missing = [r for r in REQUIRED if not (root / r).exists()]
    if with_base:
        missing += [r for r in BASE_EXTRA if not (root / r).exists()]
    if missing:
        print(f"FAIL missing entries: {missing}")
        return 1

    stray = [f for f in FORBIDDEN if (root / f).exists()]
    if stray:
        print(f"FAIL pack carries repo-only material: {stray}")
        return 1

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        print("FAIL VERSION is empty")
        return 1

    for name in ("cline_mcp_settings.json", "claude_desktop_config.json",
                 "cursor_mcp.json", "generic-mcp.json"):
        cfg = json.loads((root / "configs" / name).read_text(encoding="utf-8"))
        if "ace" not in (cfg.get("mcpServers") or {}):
            print(f"FAIL configs/{name} has no ace server entry")
            return 1

    kind = "all-in-one" if with_base else "mcp"
    print(f"OK   pack contents ({kind}), VERSION = {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
