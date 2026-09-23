#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_turn —— 一轮对话的**交互状态机**（纯逻辑，可穷举测试）

## 要解决的"僵硬"

旧交互是**阻塞式问答**：回车之后整个界面被这一轮占住 —— 不能打字（打了也不知道会怎样）、
不能中断（只能等它跑完，或者 Ctrl+C 把整个进程带走）、授权对话框还要用户手打 `2`。
用户感受到的不是"它在干活"，而是"我动不了了"。

这一层把"这一轮现在处于什么状态、此刻按下去会发生什么"抽成纯模型：

```
idle ──submit──▶ busy ──finish──▶ idle（有排队就立刻接着跑）
                   │
                   ├─ 再来一条输入 → queued（排队，不是丢掉，也不是排队等死）
                   ├─ interrupt   → requested（请求中断：跑完当前这一步就停）
                   │                   └─ 再按一次 → forced（放弃本轮，界面立刻回到可用）
                   └─ 需要授权    → permission（对话框，≥200ms 之后的答案才算数）
```

## 三条产品口径（都体现在返回值里）

1. **忙的时候输入不丢**：`submit()` 在忙时入队（有上限，满了如实拒绝），轮末 `finish()`
   把队首交还给调用方 —— "排队"和"你打得不是时候"是两种完全不同的手感。
2. **中断是两段的**：第一下"请求中断"（当前这一步跑完就停，能拿到半截结果），
   第二下"强制放弃"（界面立刻可用，后台线程仍在收尾但它的输出会被丢弃）。
   一下就把线程扔掉，会让工具跑一半、快照不一致 —— 那不是"响应快"，是"留烂摊子"。
3. **授权对话框的答案要过宽限期**（见 `ui/ace_grace.py`）：飞行过来的回车不算数。

本模块不 import 任何 UI 框架、不打印、不读时钟（`now` 全部可注入）。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ui import ace_grace

__all__ = ["IDLE", "BUSY", "PERMISSION", "STATES", "INTERRUPT_NONE",
           "INTERRUPT_REQUESTED", "INTERRUPT_FORCED", "PERMISSION_OPTIONS",
           "MAX_QUEUE", "SubmitResult", "InterruptResult", "TurnController",
           "next_permission", "permission_banner", "MODE_CYCLE"]

IDLE = "idle"
BUSY = "busy"
PERMISSION = "permission"
STATES = (IDLE, BUSY, PERMISSION)

INTERRUPT_NONE = ""
INTERRUPT_REQUESTED = "requested"
INTERRUPT_FORCED = "forced"

MAX_QUEUE = 8

# 授权对话框的三个选项（顺序 = 界面上 1/2/3，也是方向键的顺序）。
# `value` 与 `agent_runner.GRANT_*` 对齐；`danger` 的那一档在界面上要显眼 ——
# "本会话允许"是一次真实的权力扩张，不该长得像"就这一次"。
PERMISSION_OPTIONS: Tuple[Tuple[str, str, bool], ...] = (
    ("once", "perm_opt_once", False),
    ("session", "perm_opt_session", True),
    ("deny", "perm_opt_deny", False),
)

# 权限档位环：Shift+Tab 沿着它转。`full` 是"不再逐次审批"，所以转进它要**二次确认**
# （见 `needs_confirm`）—— 一个快捷键不该能悄悄解除全部审批。
MODE_CYCLE: Tuple[str, ...] = ("readonly", "write", "full")
# 转进这些档位需要明确确认（danger 档）
MODE_CONFIRM: Tuple[str, ...] = ("full",)


class SubmitResult:
    """`submit()` 的结论：`action` 取 `run` / `queued` / `rejected`。"""

    __slots__ = ("action", "text", "queued", "reason")

    def __init__(self, action: str, text: str = "", queued: int = 0,
                 reason: str = "") -> None:
        self.action = action
        self.text = text
        self.queued = int(queued)
        self.reason = reason

    def __repr__(self) -> str:
        return f"SubmitResult({self.action!r}, queued={self.queued})"


class InterruptResult:
    """`interrupt()` 的结论：`action` 取 `none` / `requested` / `forced`。"""

    __slots__ = ("action", "pending")

    def __init__(self, action: str, pending: int = 0) -> None:
        self.action = action
        self.pending = int(pending)

    def __repr__(self) -> str:
        return f"InterruptResult({self.action!r})"


class TurnController:
    """一轮的状态机。宿主（TUI / REPL）只跟它对话，不自己记状态。"""

    def __init__(self, max_queue: int = MAX_QUEUE,
                 now: Optional[Callable[[], float]] = None,
                 grace_ms: Optional[int] = None) -> None:
        self.max_queue = max(1, int(max_queue))
        self._now = now or _monotonic
        self.state = IDLE
        self.queue: List[str] = []
        self.interrupt_state = INTERRUPT_NONE
        self.abandoned = False            # 强制放弃：本轮输出作废
        self.turns = 0                    # 跑完的轮数（界面用来显示"第几轮"）
        self.t0: Optional[float] = None
        self.tool = ""                    # 当前工具（界面显示"正在跑什么"）
        self.permission_tool = ""
        self.permission_reason = ""
        self._gate = ace_grace.GraceGate(grace_ms)
        self.discarded = 0

    # ---------- 输入 ----------
    def submit(self, text: str) -> SubmitResult:
        """收到一条输入：空闲就立刻跑，忙就排队（满了如实拒绝，不静默丢）。"""
        msg = str(text or "").strip()
        if not msg:
            return SubmitResult("rejected", "", len(self.queue), "empty")
        if self.state == IDLE:
            self.begin()
            return SubmitResult("run", msg, len(self.queue))
        if self.abandoned:
            # 已经放弃本轮：输入直接进队，等宿主把本轮彻底收尾后立刻跑
            self.queue.append(msg)
            return SubmitResult("queued", msg, len(self.queue))
        if len(self.queue) >= self.max_queue:
            return SubmitResult("rejected", msg, len(self.queue), "queue_full")
        self.queue.append(msg)
        return SubmitResult("queued", msg, len(self.queue))

    def begin(self) -> None:
        """本轮真的开始跑（`submit` 内部会调；宿主从队列里取新的也要调）。"""
        self.state = BUSY
        self.interrupt_state = INTERRUPT_NONE
        self.abandoned = False
        self.t0 = self._now()
        self.tool = ""

    def finish(self) -> Optional[str]:
        """本轮结束：返回队首的那条输入（没有就 None）。宿主据此立刻接着跑。"""
        self.turns += 1
        self.state = IDLE
        self.t0 = None
        self.tool = ""
        self.interrupt_state = INTERRUPT_NONE
        self.abandoned = False
        self.permission_tool = ""
        if self.queue:
            return self.queue.pop(0)
        return None

    def drop_queue(self) -> int:
        """清空队列（`/queue clear` 与"放弃本轮"共用）。返回丢掉几条。"""
        n = len(self.queue)
        self.queue = []
        return n

    # ---------- 中断 ----------
    def interrupt(self) -> InterruptResult:
        """两段式中断：第一下请求（跑完当前步就停），第二下强制放弃。"""
        if self.state == IDLE and not self.queue:
            return InterruptResult("none")
        if self.state == IDLE and self.queue:
            # 空闲但有排队：这一下是"把排队的都撤了"
            dropped = self.drop_queue()
            return InterruptResult("forced", dropped)
        if self.interrupt_state == INTERRUPT_REQUESTED:
            self.interrupt_state = INTERRUPT_FORCED
            self.abandoned = True
            self.state = IDLE
            self.t0 = None
            return InterruptResult("forced", len(self.queue))
        self.interrupt_state = INTERRUPT_REQUESTED
        return InterruptResult("requested", len(self.queue))

    def stop_requested(self) -> bool:
        """引擎该不该停：宿主把这一句接进模型轮询 / 工具执行前的检查。"""
        return self.interrupt_state != INTERRUPT_NONE or self.abandoned

    def discard_output(self) -> bool:
        """引擎线程产出的东西要不要丢（强制放弃之后）。"""
        return self.abandoned

    # ---------- 授权 ----------
    def ask_permission(self, tool: str, reason: str = "",
                       options: Optional[Sequence[Tuple[str, str, bool]]] = None
                       ) -> List[Tuple[str, str, bool]]:
        """弹出授权对话框：返回**要显示的选项**（顺序即方向键顺序）。"""
        self.state = PERMISSION
        self.permission_tool = str(tool or "")
        self.permission_reason = str(reason or "")
        self._gate.arm(self._now())
        return list(options or PERMISSION_OPTIONS)

    def answer_permission(self, index: int = 0,
                          options: Optional[Sequence[Tuple[str, str, bool]]] = None
                          ) -> Optional[str]:
        """对话框的答案。

        - 落在宽限期内的答案 → 返回 `None`（不采纳，调用方提示"按得太快"）；
        - 正常答案 → 返回该选项的 `value`，并把状态收回 `BUSY`。
        """
        opts = list(options or PERMISSION_OPTIONS)
        if not self._gate.admit(self._now()):
            self.discarded += 1
            return None
        idx = max(0, min(int(index), len(opts) - 1))
        value = str(opts[idx][0])
        self.state = BUSY
        self.permission_tool = ""
        self.permission_reason = ""
        return value

    def cancel_permission(self) -> str:
        """对话框被 Esc 关掉：**按拒绝处理**（危险对话框里"关掉"不能等于"放行"）。"""
        self.state = BUSY
        self.permission_tool = ""
        self.permission_reason = ""
        return "deny"

    # ---------- 读 ----------
    def elapsed(self) -> float:
        if self.t0 is None:
            return 0.0
        return max(0.0, self._now() - self.t0)

    def busy(self) -> bool:
        return self.state in (BUSY, PERMISSION)

    def snapshot(self) -> Dict[str, object]:
        """界面要的一屏数据（底栏、提示条都读这一份，避免两处各算一遍）。"""
        return {
            "state": self.state,
            "busy": self.busy(),
            "queued": len(self.queue),
            "turn": self.turns + (1 if self.busy() else 0),
            "elapsed": self.elapsed(),
            "tool": self.tool,
            "interrupt": self.interrupt_state,
            "abandoned": self.abandoned,
            "permission": self.permission_tool,
            "permission_reason": self.permission_reason,
            "discarded": self.discarded,
        }

    def hint(self, translate: Optional[Callable[[str], str]] = None) -> str:
        """一行"现在能按什么"（底栏/提示条用）。i18n 键名可由调用方翻译。"""
        tr = translate or (lambda k: k)
        if self.state == PERMISSION:
            return tr("turn_hint_permission")
        if self.interrupt_state == INTERRUPT_REQUESTED:
            return tr("turn_hint_interrupting")
        if self.state == BUSY:
            return tr("turn_hint_busy").replace("{n}", str(len(self.queue)))
        if self.queue:
            return tr("turn_hint_queued").replace("{n}", str(len(self.queue)))
        return tr("turn_hint_idle")


def _monotonic() -> float:
    import time
    return time.monotonic()


# ============================================================
# 权限档位环（Shift+Tab）
# ============================================================

def next_permission(current: str, step: int = 1) -> str:
    """档位环上的下一档：readonly → write → full → readonly（倒着走传 step=-1）。"""
    cur = str(current or "").strip().lower()
    if cur not in MODE_CYCLE:
        return MODE_CYCLE[0]
    i = MODE_CYCLE.index(cur)
    return MODE_CYCLE[(i + int(step)) % len(MODE_CYCLE)]


def needs_confirm(target: str) -> bool:
    """转进这一档要不要二次确认（`full` = 不再逐次审批，一个快捷键不该能解除它）。"""
    return str(target or "").strip().lower() in MODE_CONFIRM


def permission_banner(perm: str, sandbox: str = "",
                      translate: Optional[Callable[[str], str]] = None) -> str:
    """切换档位后的一行提示：说清"现在是什么、还能怎么调"，而不是只报一个新值。

    读权限的人需要知道"这一档意味着什么"：`write` 是改文件仍要批，`full` 是不再逐次
    询问 —— 只显示一个词，用户得自己去翻文档，那就是僵硬。
    """
    tr = translate or (lambda k: k)
    p = str(perm or "").strip().lower()
    key = {"readonly": "mode_readonly", "write": "mode_write",
           "full": "mode_full"}.get(p, "mode_readonly")
    line = tr("mode_switch").replace("{mode}", p).replace("{what}", tr(key))
    if sandbox:
        line += tr("mode_sandbox_suffix").replace("{sandbox}", str(sandbox))
    return line
