#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_notify —— 通知与终端通道：一行通知区 + 桌面通知 + 终端标题

为什么单独一层：此前 ACE 的"通知"就是 `print` 一行 —— 谁都能盖掉谁（低优先级的提示会
顶掉刚打出来的错误），也没有任何"看一眼就知道它在等你"的通道（终端标题、系统通知）。
这一层做两件事：

- **排队与优先级**（纯逻辑，可断言）：同时只显示一条；高优先级插队；带 TTL，过期自动让位；
  同文去重（重复提示不刷屏）。
- **终端通道**（薄）：设置窗口标题（OSC 2）、发桌面通知（OSC 9 / OSC 777 / OSC 99 三种
  约定都支持，终端认哪个就发哪个）。没有 TTY 时**一个字都不发** —— 管道里塞转义序列
  只会污染给机器读的输出。

优先级：`urgent`（要人做决定）> `high`（出错）> `normal`（进度）> `low`（提示）。
TTL 按优先级给：越紧急留得越久（但要人回答的东西不该自己消失）。
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["Notice", "NoticeQueue", "PRIORITIES", "priority_rank",
           "title_sequence", "notify_sequence", "TerminalChannel"]

# 优先级 → (等级, 默认 TTL 秒)；TTL 为 None = 不自动消失（要人处理的东西）
PRIORITIES: Dict[str, Tuple[int, Optional[float]]] = {
    "urgent": (0, None),      # 需要人做决定（授权/计划）——不许自动消失
    "high": (1, 12.0),        # 出错
    "normal": (2, 8.0),       # 进度（写到一半、跑完了）
    "low": (3, 5.0),          # 提示（键位、模式）
}
DEFAULT_PRIORITY = "normal"


def priority_rank(name: str) -> int:
    """优先级 → 等级数字（越小越紧急）；认不出的按 normal。"""
    return PRIORITIES.get(str(name or DEFAULT_PRIORITY), PRIORITIES[DEFAULT_PRIORITY])[0]


class Notice:
    """一条通知：文本 + 优先级 + 过期时间（`expires_at=None` = 不自动过期）。"""

    def __init__(self, text: str, priority: str = DEFAULT_PRIORITY,
                 now: Optional[float] = None, ttl: Optional[float] = None) -> None:
        self.text = str(text)
        self.priority = str(priority) if str(priority) in PRIORITIES else DEFAULT_PRIORITY
        _rank, _ttl = PRIORITIES[self.priority]
        self.ttl = _ttl if ttl is None else ttl
        self.created = float(now if now is not None else time.monotonic())
        self.expires_at = None if self.ttl is None else self.created + float(self.ttl)

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and float(now) >= self.expires_at

    def __repr__(self) -> str:
        return f"Notice({self.priority!r}, {self.text!r})"


class NoticeQueue:
    """通知队列：同时只显示**一条**，按优先级与新鲜度挑。

    规则（都写成可断言的纯逻辑）：
    1. 同文去重：同一条文本再次入队时只刷新时间，不叠加两条；
    2. 挑选：先按优先级（紧急优先），同级按最新；
    3. 过期：当前这条过期就顺位到下一条（不要人处理的那种会一直留着）；
    4. 容量：超过上限丢最旧的低优先级（通知区不是日志）。
    """

    def __init__(self, max_items: int = 20) -> None:
        self.items: List[Notice] = []
        self.max_items = max(1, int(max_items))

    def push(self, text: str, priority: str = DEFAULT_PRIORITY,
             now: Optional[float] = None) -> Notice:
        text = str(text or "").strip()
        if not text:
            return Notice("", priority, now)
        for it in self.items:
            if it.text == text:                     # 同文去重：刷新时间即可
                it.created = float(now if now is not None else time.monotonic())
                _rank, _ttl = PRIORITIES[it.priority]
                it.ttl = _ttl
                it.expires_at = None if it.ttl is None else it.created + float(it.ttl)
                return it
        item = Notice(text, priority, now)
        self.items.append(item)
        if len(self.items) > self.max_items:
            self.items.sort(key=lambda n: (priority_rank(n.priority), -n.created))
            self.items = self.items[:self.max_items]
        return item

    def current(self, now: Optional[float] = None) -> Optional[Notice]:
        """当前该显示的那条（顺手清掉过期的）。"""
        t = float(now if now is not None else time.monotonic())
        self.items = [n for n in self.items if not n.expired(t)]
        if not self.items:
            return None
        return min(self.items, key=lambda n: (priority_rank(n.priority), -n.created))

    def clear(self) -> None:
        self.items = []

    def __len__(self) -> int:
        return len(self.items)


# ============================================================
# 终端通道（OSC 序列）：只对真终端发
# ============================================================

def title_sequence(title: str) -> str:
    r"""设置窗口标题的 OSC 2 序列（空标题 = 恢复默认，也返回空串）。"""
    t = str(title or "")
    if not t:
        return ""
    safe = t.replace("\x07", "").replace("\x1b", "")
    return f"\x1b]2;{safe}\x07"


def notify_sequence(text: str, title: str = "",
                    style: str = "osc9") -> str:
    r"""桌面通知序列。三种约定都支持（终端认哪个就配哪个）：

    - `osc9`  ：`ESC ] 9 ; 文本 BEL`（iTerm2 / WezTerm / Windows Terminal 等）
    - `osc777`：`ESC ] 777 ; notify ; 标题 ; 正文 BEL`（urxvt / 一部分 Linux 终端）
    - `osc99` ：`ESC ] 99 ; ; 正文 BEL`（Kitty 通知协议）

    文本里的 `BEL`/`ESC` 会被剔除 —— 否则一条通知能被内容截断（注入）。
    """
    body = str(text or "").replace("\x07", " ").replace("\x1b", " ").strip()
    if not body:
        return ""
    head = str(title or "").replace("\x07", " ").replace("\x1b", " ")
    fmt = str(style or "osc9").lower()
    if fmt == "osc777":
        return f"\x1b]777;notify;{head};{body}\x07"
    if fmt == "osc99":
        return f"\x1b]99;;{body}\x07"
    return f"\x1b]9;{body}\x07"


class TerminalChannel:
    """往终端发通道信号的薄封装：**没有 TTY 就什么都不发**。

    为什么这条纪律重要：管道/CI 里塞 OSC 序列会污染给机器读的输出（我们的 headless
    事件流就是被脚本消费的）。所以这里先判 `isatty`，再写。
    """

    def __init__(self, stream: Any = None, enabled: bool = True,
                 notify_style: str = "osc9") -> None:
        self.stream = stream
        self.enabled = bool(enabled) and not os.environ.get("ACE_NO_NOTIFY")
        self.notify_style = str(notify_style or "osc9")
        self.sent: List[str] = []            # 发过什么（测试与 /status 用）

    def _tty(self) -> bool:
        s = self.stream or sys.stdout
        try:
            return bool(s.isatty())
        except Exception:  # noqa: BLE001 —— 判不了就当不是终端
            return False

    def _write(self, seq: str) -> bool:
        if not seq or not self.enabled or not self._tty():
            return False
        try:
            s = self.stream or sys.stdout
            s.write(seq)
            s.flush()
            self.sent.append(seq)
            return True
        except Exception:  # noqa: BLE001 —— 写不进去不该影响任何事
            return False

    def set_title(self, title: str) -> bool:
        return self._write(title_sequence(title))

    def notify(self, text: str, title: str = "") -> bool:
        return self._write(notify_sequence(text, title, self.notify_style))
