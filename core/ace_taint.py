#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_taint —— 来源归属的**测量**账本（RG-03 第一阶段：只测不改裁决）

论文的 I2 是"每次行动必须能追溯到一条**用户侧**授权，外部内容不能单独构成授权"。
ACE 今天没有这个概念：执行层的输入只有 `(agent_output, user_input)`，工具结果里那些外部内容
根本不在它的输入里 —— 实测（`e2e/rg_probes.py rg03`）同一句 `file_delete(notes.txt)`：

    A 用户明确说"帮我把 notes.txt 删了"        → SUCCESS（文件被删）
    B 用户只让看 README（删除指令来自读到的东西）→ SUCCESS（文件被删）
    C 用户完全没提过这个文件                    → SUCCESS（文件被删）

三条裁决**一模一样**，且都零弹窗。执行层回答不了"是谁让做的"。

**为什么第一阶段只测量**：真正的判据需要**模型侧引用**（工具调用里说明"这条动作由哪条用户
观测单授权"）—— 那是协议改动（解析器 / 提示词 / mock / e2e 一起动），而且误报率只有真数据
能回答。所以先按一个**可算的代理指标**统计：写入的目标路径**有没有被用户提到过**。
如果开启判据，有多少次写入会被问人 —— 这就是立项卡 G1 门要的那个数。

口径写清楚（免得把代理指标当成判据）：
- `user`：目标（或其文件名）在**用户自己说的话**里出现过 → 若开启判据不会问人；
- `unattributed`：没有任何用户轮次提到过它，而工具是写类 → 若开启判据**会**问人；
- `unknown`：写类工具但**说不出目标路径**（`terminal_exec` / `code_execute` / `subagent`）→
  路径归属这条代理指标对它无效，单独计数，**不**混进"会问人"里充数。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List

# 结果属于**外部内容**的工具：读文件、检索、翻知识库、看终端输出……它们带回来的文本
# 可能包含"顺手把这个删了"这类指令，而模型没有义务抵抗它 —— 所以要能被归因。
EXTERNAL_TOOLS = frozenset({
    "file_read", "glob", "grep", "search", "kb_search", "kb_list",
    "parse_document", "terminal_view", "skill_load",
})

USER = "user"
UNATTRIBUTED = "unattributed"
UNKNOWN = "unknown"


class TaintLedger:
    """本会话的"用户说过什么 / 读了哪些外部内容 / 哪次写入说得清来源"。

    只读事实、只记数；**不做裁决**（第一阶段）。跨轮存活，挂在 ExecutionLayer 上。
    """

    def __init__(self, max_turns: int = 20, max_chars: int = 8000) -> None:
        self._turns: List[str] = []
        self._max_turns = max_turns
        self._max_chars = max_chars
        self.user_turns = 0
        self.tool_results = 0
        self.external_reads = 0
        self.assessments = 0
        self.would_escalate = 0
        self.unknown_target = 0

    # ---------- 记事实 ----------

    def note_user(self, text: str) -> None:
        """记一条用户输入（只保留最近若干轮，避免无界增长）。"""
        text = str(text or "").strip()
        if not text:
            return
        self.user_turns += 1
        self._turns.append(text[: self._max_chars])
        if len(self._turns) > self._max_turns:
            del self._turns[0]

    def note_tool(self, tool: str, ok: bool = True) -> None:
        """记一次工具往返；外部内容类工具单独计数。"""
        self.tool_results += 1
        if tool in EXTERNAL_TOOLS:
            self.external_reads += 1

    # ---------- 归属判定（代理指标） ----------

    def _mentioned(self, token: str) -> bool:
        """用户在**自己说的话**里提到过这个 token 吗（大小写与分隔符不敏感）。"""
        if not token:
            return False
        # 前后不能再接路径/文件名合法字符，避免 "api" 命中 "apiary"
        pat = re.compile(r"(?<![\w./\\-])" + re.escape(token) + r"(?![\w./\\-])",
                         re.IGNORECASE | re.UNICODE)
        return any(pat.search(t) for t in self._turns)

    def assess(self, tool: str, targets: Iterable[str]) -> Dict[str, Any]:
        """给一次写类调用做一次归属评估。**返回值只用于记录/统计，不改变裁决。**"""
        items = [str(t) for t in (targets or []) if str(t or "").strip()]
        self.assessments += 1
        if not items:
            self.unknown_target += 1
            return {"tool": tool, "attribution": UNKNOWN, "would_escalate": False,
                    "targets": [], "matched": ""}
        # 把两种拼写都算上：用户常写相对路径或只写文件名
        matched = ""
        for t in items:
            for cand in (t, os.path.basename(t.replace("\\", "/"))):
                if self._mentioned(cand):
                    matched = cand
                    break
            if matched:
                break
        if matched:
            return {"tool": tool, "attribution": USER, "would_escalate": False,
                    "targets": items, "matched": matched}
        self.would_escalate += 1
        return {"tool": tool, "attribution": UNATTRIBUTED, "would_escalate": True,
                "targets": items, "matched": ""}

    def snapshot(self) -> Dict[str, int]:
        """给日志 / `/audit` 用的计数（**只测量**：数字不参与任何裁决）。"""
        return {
            "user_turns": self.user_turns,
            "external_reads": self.external_reads,
            "tool_results": self.tool_results,
            "assessments": self.assessments,
            "would_escalate": self.would_escalate,
            "unknown_target": self.unknown_target,
        }


def attribution_stats(events: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """从**事件流**里数归属分布（只读）。

    为什么从日志派生而不是读内存账本：`/audit stats` 回答的是"**这份日志**是什么样"，
    而账本只活在当前进程里（跨会话、`--serve` 重放、排障时都读不到）。这些字段是测量阶段
    写进 `permission/decision` 事件的，所以日志里本来就有。
    """
    out = {"assessed": 0, "user": 0, UNATTRIBUTED: 0, UNKNOWN: 0, "would_escalate": 0}
    for e in events:
        attr = e.get("attribution")
        if not attr:
            continue
        out["assessed"] += 1
        if attr in out:
            out[attr] += 1
        if e.get("would_escalate"):
            out["would_escalate"] += 1
    return out
