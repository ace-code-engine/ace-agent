#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway_v2.flywheel —— L5 反馈飞轮

违规数据自动收集（JSONL），用于 SFT 微调。
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from gateway_v2.intent import Intent


class Flywheel:
    """L5 反馈飞轮：违规数据自动收集（JSONL），用于 SFT 微调。

    **不存违规原文**（安全语义，改动前请先读这段）：这条路径最常命中的规则就是
    `no_hardcoded_secrets`，而原来记录里存的是 `output_snippet = output_text[:500]`，
    默认落点又在**项目目录内**（`<project_root>/.agent_flywheel/violations.jsonl`），
    `export_for_sft()` 还会把它当 prompt 导出 —— 等于"刚拦下一段密钥，转头把它写进
    项目里的一个文件"。

    现在只留**可复核的派生事实**：sha256（能不能与原文对上）、长度、规则、来源工具。
    代价说清楚：飞轮不再能直接喂 SFT 原文，取样前必须自己从会话日志里按 sha256 取回
    并自行脱敏。宁可少一份训练样本，也不留一份明文凭据。
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._counts: Dict[str, int] = {}

    def log_violation(self, intent: Any, output_text: str, rule: str,
                      extra: Optional[Dict] = None) -> None:
        text = output_text or ""
        record = {
            "ts": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "intent": intent.to_dict() if isinstance(intent, Intent) else str(intent),
            "rule": rule,
            # 只留派生事实，不留原文（见类 docstring）
            "output_sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
            "output_len": len(text),
            "extra": extra or {},
        }
        self._counts[rule] = self._counts.get(rule, 0) + 1
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_event(self, event: str, detail: Optional[Dict] = None) -> None:
        record = {"ts": time.time(),
                  "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "event": event, "detail": detail or {}}
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def stats(self) -> Dict[str, Any]:
        return {"violations": dict(self._counts),
                "total": sum(self._counts.values()),
                "path": str(self.path) if self.path else None}

    def export_for_sft(self) -> List[Dict[str, str]]:
        """导出违规样本（坏样例：违规规则说明 + 可追溯的指纹）。

        原文不在这里（见类 docstring）：prompt 只给 sha256/长度，需要正文的取样流程
        自己去会话日志按指纹取回并脱敏。字段名保持 `prompt`/`completion`，免得下游
        导出脚本一夜之间失效；但它不再是"原文"。
        """
        if not self.path or not self.path.exists():
            return []
        samples: List[Dict[str, str]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            samples.append({
                "prompt": (f"<违规原文不落盘> sha256={rec.get('output_sha256', '')} "
                           f"len={rec.get('output_len', 0)}"),
                "completion": f"该输出违反了规则 {rec.get('rule')}，已被守门拦截。",
                "rule": rec.get("rule", ""),
            })
        return samples
