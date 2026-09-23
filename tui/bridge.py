#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""tui.bridge —— 引擎与全屏界面之间的那根管子（不依赖 Textual）

界面本体需要 Textual；这根管子的逻辑是纯的：字符串进、行列表出。单独放在这里，
是为了在没有 Textual 的环境（CI、最小安装）里也能测它、也保证它不悄悄依赖框架。

三条规矩：
1. 带 `\r` 的写整条丢掉 —— 那是 spinner 在原地重绘，进滚动区只会变成一屏残影；
2. 颜色码剥掉 —— Textual 自己管样式，留着 ANSI 会把文本串坏；
3. `isatty()` 恒 False —— 让引擎里的"要不要上色 / 弹交互框"走非交互分支（界面自己做）。
"""

from __future__ import annotations

from typing import Any, List

from ui.ace_text import strip_ansi

__all__ = ["EngineBridge"]


class EngineBridge:
    """引擎照常 `print`，界面按行挂组件。

    `post` 是界面注入的回调：`post(lines: list[str]) -> None`。
    """

    def __init__(self, post) -> None:
        self.post = post
        self._buf = ""
        self.dropped = 0

    def write(self, text: Any) -> int:
        s = "" if text is None else str(text)
        if not s:
            return 0
        if "\r" in s:
            self.dropped += 1
            return len(s)
        self._buf += s
        lines: List[str] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            lines.append(strip_ansi(line))
        if lines:
            self.post(lines)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            tail, self._buf = self._buf, ""
            self.post([strip_ansi(tail)])

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("TUI 的 stdout 是队列，没有文件描述符")

    def __getattr__(self, name: str) -> Any:
        if name in ("encoding", "errors"):
            return "utf-8" if name == "encoding" else "replace"
        raise AttributeError(name)
