#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ui.ace_tools —— 工具执行看板：四态点 + 同帧同步（纯逻辑，可穷举测试）

## 为什么要一个"看板"而不是一行 spinner

一次请求里工具可能连着跑好几个（读文件 → 改文件 → 跑测试）。原来只有一行"正在调用
工具"，用户看不出**这一步到底做完了没**，也看不出**后面还排着几个**。于是一跑长命令，
人就开始怀疑是不是卡住了。

看板把每个工具当成一行，状态只有四个：

| 状态 | 点 | 含义 |
| --- | --- | --- |
| `queued` | `○` | 已经知道要做，还没轮到 |
| `running` | `▁▃▅▇▅▃` | 正在跑（一个字形循环，速度固定） |
| `done` | `●` | 跑完了 |
| `failed` | `✗` | 报错了（不是"没跑"，是"跑了但失败"） |

## 同帧同步（这条是重点）

`running` 是动画。如果每一行各自记自己的开始时刻、各自算自己的帧，屏幕上两行并行
工具就会**各自闪各自的相位** —— 看起来像两个互不相干的东西在抢注意力，而且每帧要
重算两遍。所以这里只用**一个钟**：`render(now)` 进来先算一次全局帧号，所有 `running`
行共用同一个字形。

## 只重画变了的那几行

`patches(prev, cur)` 返回 `[(行号, 新文本)]`，调用方只把这些行重画（`\r\x1b[K` + 文本），
不整块重刷 —— 整块重刷在慢终端上会闪，而且长会话里块越大闪得越厉害。

## 长会话兜底

`max_rows` 到了就只显示前 `max_rows-1` 行 + 一行"还有 k 个"：看板是**状态**，不是日志，
不能让它把屏幕吃掉（日志归工具卡片和 `/expand`）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ui.ace_text import display_width, truncate_width

__all__ = ["STATES", "DOT", "RUN_FRAMES", "RUN_INTERVAL", "ToolRow", "ToolBoard",
           "frame_index"]

STATES = ("queued", "running", "done", "failed")
DOT: Dict[str, str] = {"queued": "○", "done": "●", "failed": "✗"}
# running 的字形：与 `ui/ace_spinner.py` 的 tool_running 阶段同一套（全局只有一套视觉语言）
RUN_FRAMES = ("▁", "▃", "▅", "▇", "▅", "▃")
RUN_INTERVAL = 0.16


def frame_index(now: float, t0: float, interval: float = RUN_INTERVAL,
                frames: int = len(RUN_FRAMES)) -> int:
    """全局帧号：由**一个时钟**（`now - t0`）算出来，所有 running 行共用。

    负数/异常一律落回 0：时钟倒退（系统时间调整）不该让看板抛异常。
    """
    try:
        elapsed = float(now) - float(t0)
        if elapsed <= 0 or interval <= 0 or frames <= 0:
            return 0
        return int(elapsed / interval) % frames
    except (TypeError, ValueError):
        return 0


class ToolRow:
    """看板里的一行。`state` 只在 `STATES` 里取值（写坏了按 `queued` 处理）。"""

    __slots__ = ("name", "target", "state", "started", "ended", "note", "exit_code")

    def __init__(self, name: str, target: str = "", state: str = "queued") -> None:
        self.name = str(name or "tool")
        self.target = str(target or "")
        self.state = state if state in STATES else "queued"
        self.started: Optional[float] = None
        self.ended: Optional[float] = None
        self.note = ""
        self.exit_code: Optional[int] = None

    def elapsed(self, now: float) -> float:
        if self.started is None:
            return 0.0
        end = self.ended if self.ended is not None else float(now)
        return max(0.0, end - self.started)

    def key(self) -> str:
        return f"{self.name}\x00{self.target}"


class ToolBoard:
    """一轮请求里的工具看板。`now` 全部可注入 —— 动画测试不靠 sleep。"""

    def __init__(self, width: int = 78, max_rows: int = 6,
                 interval: float = RUN_INTERVAL) -> None:
        self.width = int(width)
        self.max_rows = max(1, int(max_rows))
        self.interval = float(interval)
        self.rows: List[ToolRow] = []
        self.t0: Optional[float] = None

    # ---------- 状态变更 ----------
    def queue(self, name: str, target: str = "") -> ToolRow:
        row = ToolRow(name, target, "queued")
        self.rows.append(row)
        return row

    def start(self, name: str, target: str = "", now: Optional[float] = None) -> ToolRow:
        """标记开始：同名同目标的行已存在就复用（并行时会重复调用同一工具）。"""
        row = self._find(name, target)
        if row is None:
            row = self.queue(name, target)
        row.state = "running"
        row.started = self._now(now)
        if self.t0 is None:
            self.t0 = row.started
        return row

    def finish(self, name: str, target: str = "", ok: bool = True,
               now: Optional[float] = None, exit_code: Optional[int] = None,
               note: str = "") -> Optional[ToolRow]:
        row = self._find(name, target)
        if row is None:
            return None
        row.state = "done" if ok else "failed"
        row.ended = self._now(now)
        row.exit_code = exit_code
        if note:
            row.note = str(note)
        return row

    def _find(self, name: str, target: str) -> Optional[ToolRow]:
        key = f"{name}\x00{target}"
        for row in self.rows:
            if row.key() == key and row.state in ("queued", "running"):
                return row
        return None

    @staticmethod
    def _now(now: Optional[float]) -> float:
        if now is not None:
            return float(now)
        import time
        return time.monotonic()

    # ---------- 查询 ----------
    def count(self, state: Optional[str] = None) -> int:
        if state is None:
            return len(self.rows)
        return sum(1 for r in self.rows if r.state == state)

    def active(self) -> int:
        return self.count("running") + self.count("queued")

    def headline(self) -> str:
        """一行摘要（给状态行/spinner 用）：`⚙ file_write ×2 · 1 个在跑`。"""
        if not self.rows:
            return ""
        if len(self.rows) == 1:
            row = self.rows[0]
            mark = DOT.get(row.state, "?") if row.state != "running" else "▅"
            return f"{mark} {row.name}" + (f" {row.target}" if row.target else "")
        done = self.count("done") + self.count("failed")
        return f"⚙ {len(self.rows)} 个工具 · {done} 完成 · {self.active()} 待跑"

    # ---------- 渲染 ----------
    def render(self, now: Optional[float] = None, width: Optional[int] = None) -> List[str]:
        """整块渲染。**同一个 `now` 只算一次帧号**，所有 running 行共用。"""
        _now = self._now(now)
        idx = frame_index(_now, self.t0 if self.t0 is not None else _now,
                          self.interval, len(RUN_FRAMES))
        glyph = RUN_FRAMES[idx]
        _w = int(width if width is not None else self.width)
        out: List[str] = []
        shown = self.rows[:self.max_rows]
        for row in shown:
            dot = glyph if row.state == "running" else DOT.get(row.state, "?")
            parts = [f"{dot} {row.name}"]
            if row.target:
                parts.append(row.target)
            if row.state in ("done", "failed"):
                parts.append(f"{row.elapsed(_now):.1f}s")
                if row.exit_code not in (None, 0):
                    parts.append(f"exit {row.exit_code}")
            if row.note:
                parts.append(row.note)
            out.append(self._fit(" · ".join(parts), _w))
        rest = len(self.rows) - len(shown)
        if rest > 0:
            out.append(self._fit(f"… 还有 {rest} 个工具（看板只报状态，明细见工具卡片）", _w))
        return out

    @staticmethod
    def _fit(text: str, width: int) -> str:
        """按显示宽度截断（CJK 占两列；路径/命令里的中文照样按列算）。"""
        if width <= 0:
            return text
        if display_width(text) <= width:
            return text
        return truncate_width(text, width)

    def patches(self, prev: List[str], cur: List[str]) -> List[Tuple[int, str]]:
        """只回**变了**的行：`[(行号, 新文本)]`。行数变化按"多退少补"处理。"""
        out: List[Tuple[int, str]] = []
        for i, line in enumerate(cur):
            if i >= len(prev) or prev[i] != line:
                out.append((i, line))
        return out

    def clear_finished(self) -> int:
        """把已经收尾的行摘掉（收尾卡片已经把它们讲完了，看板不留尸体）。返回摘掉几行。"""
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.state in ("queued", "running")]
        return before - len(self.rows)
