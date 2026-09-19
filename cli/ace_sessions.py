#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_sessions —— 会话管理的纯逻辑（列表 / 摘要 / 续聊 / 分叉 / rewind）

会话的事实源就是 `.ace_sessions/*.jsonl` 事件日志（`cli/ace_sessionlog.py` 写的）。
这里只做**从事件派生**的几件事，不碰 UI：

- `summarize(events)`：轮数 / 工具次数 / 压缩次数 / 首句 / 末句 —— 给 `/sessions` 列表
- `messages_at_turn(events, n)`：把消息历史截到第 n 轮（**rewind 的核心**）
- `replay_messages(events)`：全量重放（与 SessionLog.replay_messages 同口径）

为什么 rewind 是"截断消息"而不是"回滚文件"：这两件事必须分开。对话回退是**上下文**
操作（把模型记忆退回到某一轮），文件回退是**物理**操作（`/rollback` + 快照）。
把它们绑在一起，用户会以为"rewind 一下文件也回来了"——那是错的，也是危险的。
所以 `/rewind` 明确只动对话，并在输出里点明文件要靠 `/rollback`。

纯函数：输入事件列表，输出数据。可单测、可重放。
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

__all__ = ["summarize", "iter_user_turns", "messages_at_turn", "replay_messages",
           "turn_count", "head_for_resume", "label", "pick_by_index",
           "MAX_RESUME_MESSAGES"]

# 续聊/分叉时最多带多少条消息（10 轮）：旧会话无限膨胀会把上下文一次吃满
MAX_RESUME_MESSAGES = 20


def _kind(ev: Any) -> str:
    return str((ev or {}).get("kind") or "") if isinstance(ev, dict) else ""


def turn_count(events: Iterator[Dict[str, Any]]) -> int:
    """轮数 = user/message 事件数（一次用户输入算一轮）。"""
    return sum(1 for ev in events if _kind(ev) == "user/message")


def iter_user_turns(events: List[Dict[str, Any]]) -> List[int]:
    """每个用户轮次对应的**事件下标**（不是 seq ——需要的是切片位置）。

    为什么不用 seq 当边界：压缩事件会替换掉中间的消息，而 seq 只管追加。
    用下标切片才能保证"切到第 n 轮"与 `messages_at_turn` 的重放口径一致。
    """
    return [i for i, ev in enumerate(events or []) if _kind(ev) == "user/message"]


def messages_at_turn(events: List[Dict[str, Any]], turn: int,
                     include_assistant_after: bool = True) -> List[Dict[str, str]]:
    """截到第 `turn` 轮（含）为止的消息历史。

    - `turn <= 0` → 空列表（回到会话开始前）
    - `turn` 超过实际轮数 → 全量（不报错：用户说"退到第 99 轮"时最合理的行为就是不动）
    - `include_assistant_after=False` → 不带上该轮的回复（用于"重问一遍"）

    一轮里可能有多条 assistant（工具往返会产生好几条），所以"结束"的判据是
    **下一条 user 出现**，不是"第一条 assistant 之后就停"。第一版写成后者，
    结果第 2 轮只回出 3 条消息（少了第一轮的回复）——测试当场抓到。
    """
    evs = list(events or [])
    marks = iter_user_turns(evs)
    if turn <= 0 or not marks:
        return []
    turn = min(int(turn), len(marks))
    out: List[Dict[str, str]] = []
    seen = 0
    for ev in evs:
        k = _kind(ev)
        if k == "user/message":
            seen += 1
            if seen > turn:
                break
            out.append({"role": "user", "content": str(ev.get("content") or "")})
        elif k == "assistant/message" and seen >= 1:
            if not include_assistant_after and seen == turn and out \
                    and out[-1]["role"] == "user":
                break                       # 该轮的第一条回复：不带上，就此收尾
            out.append({"role": "assistant", "content": str(ev.get("content") or "")})
    return out


def replay_messages(events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """全量重放 user/assistant（与 SessionLog.replay_messages 同一口径）。"""
    msgs: List[Dict[str, str]] = []
    for ev in events or []:
        k = _kind(ev)
        if k == "user/message":
            msgs.append({"role": "user", "content": str(ev.get("content") or "")})
        elif k == "assistant/message":
            msgs.append({"role": "assistant", "content": str(ev.get("content") or "")})
    return msgs


def summarize(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """列表用的摘要。

    `tools` 只数 `tool/result`（一次调用一条结果）；`compactions` 数压缩事件 ——
    会话被压过说明"它其实已经忘掉一部分了"，列表里该看得出来。
    """
    evs = list(events or [])
    first_user = ""
    last_assistant = ""
    tools = 0
    compactions = 0
    security = 0
    for ev in evs:
        k = _kind(ev)
        if k == "user/message" and not first_user:
            first_user = str(ev.get("content") or "")
        elif k == "assistant/message":
            last_assistant = str(ev.get("content") or "")
        elif k == "tool/result":
            tools += 1
        elif k == "compaction/event":
            compactions += 1
        elif k == "security/denied":
            security += 1
    return {
        "turns": turn_count(iter(evs)),
        "tools": tools,
        "compactions": compactions,
        "security_denied": security,
        "first_user": first_user,
        "last_assistant": last_assistant,
    }


def head_for_resume(events: List[Dict[str, Any]],
                    limit: int = MAX_RESUME_MESSAGES) -> List[Dict[str, str]]:
    """续聊/分叉要带上的消息：**尾部** limit 条（保留最近上下文，与自动恢复同口径）。"""
    msgs = replay_messages(events)
    if limit and limit > 0:
        return msgs[-int(limit):]
    return msgs


def label(events: List[Dict[str, Any]], fallback: str = "") -> str:
    """给会话起个可读名字：首句前 40 字；没有就退回文件名。"""
    s = summarize(events)
    first = " ".join(str(s["first_user"] or "").split())
    if not first:
        return fallback
    return first[:40] + ("…" if len(first) > 40 else "")


def pick_by_index(items: List[Dict[str, Any]], raw: str) -> Optional[Dict[str, Any]]:
    """把 `/sessions` 列表里的编号（1 起）转成条目；越界或非数字返回 None。"""
    try:
        idx = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if 1 <= idx <= len(items or []):
        return items[idx - 1]
    return None
