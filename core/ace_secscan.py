#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_secscan —— 路径级静态安全扫描（WP-11：MCP 安全子层的"体检"工具）

判据**全部复用既有名单，不另立**（rung 2，也是 H-11"名单只剩一份"的延伸）：
- 凭据 / 敏感目标：`core/sensitive.py`（`sensitive_target` / `is_credential_file`）
- 可执行后缀（ShellExecute 会**运行**它）：`tools/base._OS_HANDOFF_BLOCKED_SUFFIXES`
- 网络路径（UNC = 出站连接）：`tools/base.network_path_reason`

SEC-022：第一版**只判文件名/路径，不读文件内容**。报告必须自带这个范围声明 ——
"扫过了"不等于"安全了"，把这个区别写进**输出**而不是留在文档里（写文档防不住
主 agent 把报告当成安全证明）。

与工具闸门的差别（为什么扫描可以比闸门严）：`.env` 对工具是"正常开发对象"（SEC-014
的刻意取舍，写它不可回滚），但对**扫描**是发现 —— 观察不拦截，所以可以更全。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from core import sensitive as _sens
from tools.base import ToolExecutorBase, network_path_reason

__all__ = ["SCOPE_STATEMENT", "MAX_FILES", "scan_dir", "render_report"]

SCOPE_STATEMENT = ("路径级静态扫描（WP-11）：只判文件名/路径，不读文件内容。"
                   "报告干净**不等于**安全 —— 内容级检查（硬编码密钥、注入面）"
                   "需要另做。")

#: 不追进的运行时产物目录：它们不是"可疑"，是噪声（vendor/缓存/agent 自留地）。
_SKIP_DIRS = frozenset({
    ".git", ".guardian", ".ace_sessions", ".agent_flywheel", ".poc_reports",
    "__pycache__", "node_modules", ".venv", "venv", ".test_tmp",
})

#: 扫描文件数上限：**如实说**，而不是装"全扫完了"。
MAX_FILES = 20_000


def _classify(path: Path) -> Dict[str, str]:
    """一条路径的可疑类别。返回空 dict = 没发现。判据逐条走既有名单。"""
    text = str(path)
    net = network_path_reason(text)
    if net:
        return {"category": "network_path", "reason": net}
    sens = _sens.sensitive_target(text)
    if sens:
        return {"category": "sensitive", "reason": sens}
    if _sens.is_credential_file(text):
        # 比工具闸门更全的那一档：`.env` 在这里**是**发现（扫描只观察，不拦截）。
        return {"category": "credential",
                "reason": "文件名形态即凭据（SEC-014 同一份清单；内容未读）"}
    suffix = path.suffix.lower()
    if suffix in ToolExecutorBase._OS_HANDOFF_BLOCKED_SUFFIXES:
        return {"category": "executable_handoff",
                "reason": (f"后缀 {suffix} 交给系统打开时会**被执行**（ShellExecute），"
                           "不是只读预览")}
    return {}


def scan_dir(path: "str | Path") -> Dict[str, Any]:
    """扫一个目录。

    返回 `{"scope": 范围声明, "scanned": 文件数, "findings": [{path, category, reason}]}`。
    目录不存在 / 不是目录也返回**结构一致**的结果（一条 target 类发现），调用方不用分两条路。
    """
    root = Path(os.path.expanduser(str(path)))
    if not root.is_dir():
        return {"scope": SCOPE_STATEMENT, "scanned": 0,
                "findings": [{"path": str(root), "category": "target",
                              "reason": f"目录不存在或不是目录: {root}"}]}
    findings: List[Dict[str, str]] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for d in dirnames:
            hit = _classify(Path(dirpath) / d)
            if hit:
                findings.append({"path": str(Path(dirpath) / d), **hit})
        for fn in filenames:
            scanned += 1
            p = Path(dirpath) / fn
            if scanned > MAX_FILES:
                findings.append({"path": str(p), "category": "limit",
                                 "reason": f"已扫 {MAX_FILES} 个文件，其余未扫（如实说，不装扫完）"})
                continue
            hit = _classify(p)
            if hit:
                findings.append({"path": str(p), **hit})
    return {"scope": SCOPE_STATEMENT, "scanned": scanned, "findings": findings}


def render_report(report: Dict[str, Any]) -> str:
    """把 scan_dir 的结果翻成给主 agent 看的文本。范围声明放**第一行**。"""
    lines: List[str] = [str(report.get("scope") or ""), ""]
    findings = report.get("findings") or []
    lines.append(f"扫描 {report.get('scanned', 0)} 个文件，发现 {len(findings)} 条：")
    for f in findings:
        lines.append(f"  [{f.get('category', '?')}] {f.get('path')} —— {f.get('reason')}")
    if not findings:
        lines.append("  （没有发现。上面的范围声明仍然成立。）")
    return "\n".join(lines)
