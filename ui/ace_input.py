#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_input —— 输入行的交互逻辑（纯函数）

终端输入框的麻烦事其实只有几件，但每件都很显眼：

1. **大段粘贴**：一次粘 300 行日志进输入行，光标没了、上一条对话被顶出屏幕，
   而且你根本看不出自己粘的是什么。做法是折叠成一行占位符，提交时再展开。
2. **`!` 直接跑命令**：想跑一条命令不该先跟模型说一遍"请帮我执行…"。`!ls` 就是
   `ls`，而且它照旧走执行层（权限/审批/沙箱都在）—— 这一点与 Claude Code 的
   `!` 一致，但闸门是我们的。
3. **长输入的回显**：就算输入行折叠了，提交后如果把原文再打一遍，屏幕照样被刷掉。
   回显要截断，但要**如实说明截了多少**。
4. **暂存（stash）**：一句话写一半突然想问别的 —— 把它存起来，回头再取回。
5. **排队**：一次想交代三件事，与其等一轮结束再打字，不如先排队。

这里只有纯逻辑（解析、折叠、展开、截断、快捷键表），不碰 prompt_toolkit：
既可单测，也能被别的前端复用。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["parse_input_mode", "should_fold_paste", "fold_paste", "expand_pastes",
           "truncate_echo", "stash_push", "stash_pop", "KEYMAP", "keys_table",
           "PASTE_MAX_LINES", "PASTE_MAX_CHARS", "ECHO_MAX_LINES", "ECHO_MAX_CHARS"]

PASTE_MAX_LINES = 6        # 超过这么多行就折叠
PASTE_MAX_CHARS = 800      # 或超过这么多字符
ECHO_MAX_LINES = 12        # 回显时最多打几行
ECHO_MAX_CHARS = 800

# 占位符：带上行数，人一眼能看出自己粘了多大一坨；编号用于提交时还原
_PLACEHOLDER = "[粘贴 #{idx} +{lines} 行]"
_PASTE_RE = re.compile(r"\[粘贴 #(\d+) \+\d+ 行\]")


def parse_input_mode(line: str) -> Tuple[str, str]:
    """输入行 → (模式, 内容)。模式：normal / bash / empty。

    `!` 开头 = bash 模式（直接执行，不发模型）。`!!` 不是转义 —— 想发给模型就以
    普通文字说，别用感叹号开头；这一条写进 `/keys` 的说明里，免得有人猜。
    """
    text = str(line or "")
    if not text.strip():
        return "empty", ""
    if text.startswith("!"):
        payload = text[1:].strip()
        return ("bash", payload) if payload else ("bash", "")
    return "normal", text


def should_fold_paste(text: str) -> bool:
    """这段粘贴值得折叠吗？（多行或够长才折，短文折叠只会让人多一步）"""
    t = str(text or "")
    return t.count("\n") + 1 > PASTE_MAX_LINES or len(t) > PASTE_MAX_CHARS


def fold_paste(text: str, index: int) -> Tuple[str, Optional[Dict[str, Any]]]:
    """粘贴文本 → (占位符, 元信息)；不值得折叠时返回 (原文, None)。"""
    t = str(text or "")
    if not should_fold_paste(t):
        return t, None
    lines = t.count("\n") + 1
    return _PLACEHOLDER.format(idx=index, lines=lines), {"index": index, "text": t,
                                                         "lines": lines}


def expand_pastes(text: str, store: Dict[int, str]) -> str:
    """提交前把占位符换回原文。找不到编号就**原样留着**（比悄悄丢掉强）。"""
    def _rep(m: "re.Match[str]") -> str:
        idx = int(m.group(1))
        return store.get(idx, m.group(0))
    return _PASTE_RE.sub(_rep, str(text or ""))


def truncate_echo(text: str, max_lines: int = ECHO_MAX_LINES,
                  max_chars: int = ECHO_MAX_CHARS) -> str:
    """回显用户输入：超长就截断，并**说明截了多少**。

    "屏幕被自己粘的东西刷掉"是真实痛点，但静默截断更糟 —— 你以为发出去的只有这些。
    """
    t = str(text or "")
    lines = t.split("\n")
    if len(lines) <= max_lines and len(t) <= max_chars:
        return t
    head = lines[:max_lines] if len(lines) > max_lines else lines
    shown = "\n".join(head)[:max_chars]
    dropped_lines = max(0, len(lines) - len(head))
    dropped_chars = max(0, len(t) - len(shown))
    tail = []
    if dropped_lines:
        tail.append(f"{dropped_lines} 行")
    if dropped_chars and not dropped_lines:
        tail.append(f"{dropped_chars} 字符")
    return shown + (f"\n…（回显已截断，实际发出 {len(lines)} 行 / {len(t)} 字符；"
                    f"省略 {'、'.join(tail)}）" if tail else "")


def stash_push(stack: List[str], text: str) -> List[str]:
    """把当前输入存进暂存栈（空输入不入栈）。返回新栈。"""
    t = str(text or "")
    if not t.strip():
        return list(stack)
    return list(stack) + [t]


def stash_pop(stack: List[str]) -> Tuple[List[str], str]:
    """取出最近一次暂存。返回 (新栈, 文本)。栈空返回 (原栈, "")。"""
    s = list(stack or [])
    if not s:
        return s, ""
    return s[:-1], s[-1]


# 内置快捷键表：(键, i18n 键, 说明 i18n 键)。`/keys` 直接遍历它 ——
# 表是唯一来源，改键位时不会漏改文档。
KEYMAP: List[Tuple[str, str]] = [
    ("Enter", "keys_enter"),
    ("Alt+Enter / Ctrl+J", "keys_newline"),
    ("↑ / ↓", "keys_history"),
    ("Ctrl+R", "keys_search_history"),
    ("/history <词>", "keys_history_fuzzy"),
    ("F1 / F2 / F3", "keys_axes"),
    ("F4", "keys_thinking"),
    ("Ctrl+O", "keys_expand"),
    ("Ctrl+S", "keys_stash"),
    ("Ctrl+L", "keys_clear_screen"),
    ("Esc", "keys_escape"),
    ("Ctrl+C", "keys_ctrl_c"),
    ("! <命令>", "keys_bash"),
    ("? <回车>", "keys_help"),
]


def keys_table() -> List[Tuple[str, str]]:
    """给 `/keys` 用的表（原样返回，调用方负责翻译与排版）。"""
    return list(KEYMAP)
