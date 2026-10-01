#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_secscan —— 路径级 + 内容级静态安全扫描（WP-11：MCP 安全子层的"体检"工具）

判据**全部复用既有名单，不另立**（rung 2，也是 H-11"名单只剩一份"的延伸）：
- 凭据 / 敏感目标：`core/sensitive.py`（`sensitive_target` / `is_credential_file`）
- 可执行后缀（ShellExecute 会**运行**它）：`tools/base._OS_HANDOFF_BLOCKED_SUFFIXES`
- 网络路径（UNC = 出站连接）：`tools/base.network_path_reason`

SEC-022：默认**只判文件名/路径，不读文件内容**。报告必须自带这个范围声明 ——
"扫过了"不等于"安全了"，把这个区别写进**输出**而不是留在文档里（写文档防不住
主 agent 把报告当成安全证明）。

v2（`read_content=True`，MCP 面叫 `deep`）：**只读"文件名已命中凭据"的那批文件**
（不另立一份"哪些文件该读"的名单 —— 文件名名单就是选择器），高精度规则、宁可漏不可
误报（误报会让主 agent 对后续真发现脱敏）。三道上限：≤64 KB/文件、≤200 个文件、
单行 ≤4 KiB，超了**如实说 skipped**，不装查过。

与工具闸门的差别（为什么扫描可以比闸门严）：`.env` 对工具是"正常开发对象"（SEC-014
的刻意取舍，写它不可回滚），但对**扫描**是发现 —— 观察不拦截，所以可以更全。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

from core import sensitive as _sens
from tools.base import ToolExecutorBase, network_path_reason

__all__ = ["SCOPE_STATEMENT", "CONTENT_SCOPE_STATEMENT", "MAX_FILES",
           "CONTENT_MAX_BYTES", "CONTENT_MAX_FILES", "scan_dir", "render_report"]

SCOPE_STATEMENT = ("路径级静态扫描（WP-11）：只判文件名/路径，不读文件内容。"
                   "报告干净**不等于**安全 —— 内容级检查（硬编码密钥、注入面）"
                   "需要另做（`deep: true` 只查名字已命中的那批）。")

CONTENT_SCOPE_STATEMENT = ("内容级静态扫描（WP-11 v2）：只读**文件名已命中凭据**的文件，"
                           "且 ≤64 KB/文件、≤200 个；高精度规则，宁可漏不可误报。"
                           "其余文件仍然**没有**读内容 —— 报告干净仍不等于安全。")

#: 不追进的运行时产物目录：它们不是"可疑"，是噪声（vendor/缓存/agent 自留地）。
_SKIP_DIRS = frozenset({
    ".git", ".guardian", ".ace_sessions", ".agent_flywheel", ".poc_reports",
    "__pycache__", "node_modules", ".venv", "venv", ".test_tmp",
})

#: 扫描文件数上限：**如实说**，而不是装"全扫完了"。
MAX_FILES = 20_000

#: 内容级三道上限（v2）。
CONTENT_MAX_BYTES = 64 * 1024
CONTENT_MAX_FILES = 200

# —— v2 内容级判据（高精度：命中就该是真的，占位符显式排除）——
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_AKIA_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_KV_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret[_-]?key|secret|token|auth[_-]?token"
    r"|api[_-]?key|access[_-]?key|private[_-]?key)"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9+/_.\-]{16,})")
#: 占位符形态：样例/模板里的 `your_...`、`changeme`、`${...}` 是**文档**，不是泄露。
_PLACEHOLDER_MARKERS = ("your_", "example", "changeme", "placeholder", "dummy",
                        "test", "xxx", "sk-xxxx", "${", "...", "key_here", "api_key",
                        "password_here", "secret_here")


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


def _placeholder(value: str) -> bool:
    """值是不是占位符形态（样例/模板，不是泄露）。"""
    low = value.lower()
    return any(m in low for m in _PLACEHOLDER_MARKERS)


def _content_findings(path: Path) -> List[Dict[str, Any]]:
    """内容级判据（v2）：只对**名字已命中凭据**的文件跑。返回发现列表（可能含 skipped）。"""
    try:
        size = path.stat().st_size
    except OSError:
        return [{"path": str(path), "category": "content_unreadable",
                 "reason": "名字已命中凭据但读不了（权限/已删）—— 内容未检"}]
    if size > CONTENT_MAX_BYTES:
        return [{"path": str(path), "category": "content_skipped",
                 "reason": f"文件 {size} 字节 > {CONTENT_MAX_BYTES} 上限，内容未检（如实说）"}]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [{"path": str(path), "category": "content_unreadable",
                 "reason": f"读不了（{type(e).__name__}: {e}）—— 内容未检"}]
    if "\x00" in text[:1024]:
        return [{"path": str(path), "category": "content_skipped",
                 "reason": "疑似二进制，内容未检"}]
    out: List[Dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 4096:
            continue
        if _PEM_RE.search(line):
            out.append({"path": str(path), "category": "content_secret", "line": lineno,
                        "reason": f"第 {lineno} 行含 PEM 私钥头（真私钥，不是占位符）"})
            continue
        if _AKIA_RE.search(line):
            out.append({"path": str(path), "category": "content_secret", "line": lineno,
                        "reason": f"第 {lineno} 行含 AWS Access Key 形态（AKIA…）"})
            continue
        m = _KV_RE.search(line)
        if m and not _placeholder(m.group(2)):
            out.append({"path": str(path), "category": "content_secret", "line": lineno,
                        "reason": (f"第 {lineno} 行：{m.group(1)}="
                                   f"<{m.group(2)[:8]}…> 疑似真值（非占位符形态）")})
    return out


def scan_dir(path: "str | Path", read_content: bool = False) -> Dict[str, Any]:
    """扫一个目录。

    `read_content=True`（MCP 面 `deep: true`）= 内容级：只对**文件名已命中凭据**的文件读内容
    （三道上限见模块 docstring）。
    返回 `{"scope": 范围声明, "scanned": 文件数, "findings": [{path, category, reason, line?}]}`。
    目录不存在 / 不是目录也返回**结构一致**的结果（一条 target 类发现），调用方不用分两条路。
    """
    root = Path(os.path.expanduser(str(path)))
    if not root.is_dir():
        return {"scope": (CONTENT_SCOPE_STATEMENT if read_content else SCOPE_STATEMENT),
                "scanned": 0,
                "findings": [{"path": str(root), "category": "target",
                              "reason": f"目录不存在或不是目录: {root}"}]}
    findings: List[Dict[str, Any]] = []
    scanned = 0
    content_files = 0
    content_limit_hit = False
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
                if read_content and hit["category"] == "credential":
                    if content_files >= CONTENT_MAX_FILES:
                        if not content_limit_hit:
                            findings.append({"path": str(p), "category": "limit",
                                             "reason": f"内容级已查 {CONTENT_MAX_FILES} 个文件，"
                                                       "其余未读内容（如实说）"})
                            content_limit_hit = True
                        continue
                    content_files += 1
                    findings.extend(_content_findings(p))
    return {"scope": (CONTENT_SCOPE_STATEMENT if read_content else SCOPE_STATEMENT),
            "scanned": scanned, "content_checked": content_files,
            "findings": findings}


def render_report(report: Dict[str, Any]) -> str:
    """把 scan_dir 的结果翻成给主 agent 看的文本。范围声明放**第一行**。"""
    lines: List[str] = [str(report.get("scope") or ""), ""]
    findings = report.get("findings") or []
    lines.append(f"扫描 {report.get('scanned', 0)} 个文件，发现 {len(findings)} 条：")
    for f in findings:
        loc = f" 第{f['line']}行" if f.get("line") else ""
        lines.append(f"  [{f.get('category', '?')}] {f.get('path')}{loc} —— {f.get('reason')}")
    if not findings:
        lines.append("  （没有发现。上面的范围声明仍然成立。）")
    return "\n".join(lines)
