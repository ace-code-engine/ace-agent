#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_spinner —— 等待指示器状态机：**扫光速度即语义**，卡住会被颜色说出来

为什么值得单独做一层：此前等待行只有一个会转的点号 + 秒数，于是"在等网络"和"模型在
长思考"长得一模一样，用户只能靠读文字区分；而"卡住了"更是完全看不出来（转得一样快）。
参照的交互口径是：**不同阶段的字形与速度不同**（等首字节快、推理慢、正式回答旋转、
工具执行另一套），**静默超时后颜色从主题色平滑过渡到告警红**，并且这套动效必须有
**无动效替代编码**（整屏不动时仍能看出状态）。

三件可断言的事（都是纯函数）：
- `frames_for(phase)` / `frame_at(phase, elapsed)`：阶段 → 帧序列与当前帧；
- `stall_level(idle, threshold)`：0→1 的"卡住程度"；
- `stall_color(level, truecolor)`：真彩走平滑过渡，**低色深在过半处离散跳到告警色**
  （降级之后语义仍然成立）。
`spinner_line()` 负责把上面三样拼成一行（并按列截断，免得顶破终端让 `\r` 重绘错位）。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from ui.ace_text import truncate_width

__all__ = ["PHASES", "frames_for", "frame_at", "phase_interval", "stall_level",
           "stall_color", "spinner_line", "DEFAULT_STALL_SECONDS",
           "THEME_RGB", "WARN_RGB"]

# 阶段：等首字节（网络）→ 推理 → 正式回答 → 工具参数流入 → 工具执行
PHASES: Tuple[str, ...] = ("waiting", "reasoning", "answering", "tool_args",
                           "tool_running")

# 每个阶段一套字形与帧间隔（0.08s = 快、0.24s = 慢）。字符都是单宽、无 emoji。
_GLYPHS: Dict[str, Tuple[Tuple[str, ...], float]] = {
    "waiting": (("·", "˙", "•", "˙"), 0.08),          # 等首字节：快闪
    "reasoning": (("◐", "◓", "◑", "◒"), 0.24),        # 推理：慢转
    "answering": (("◈", "◇", "◆", "◇"), 0.12),        # 正式回答：中速旋转
    "tool_args": (("▖", "▘", "▝", "▗"), 0.10),        # 参数流入：四角推进
    "tool_running": (("▁", "▃", "▅", "▇", "▅", "▃"), 0.16),   # 执行：脉冲
}
DEFAULT_PHASE = "reasoning"
DEFAULT_STALL_SECONDS = 3.0

# 主题绿 → 告警红（真彩色下按比例插值）
THEME_RGB = (0x7E, 0xCB, 0x8F)
WARN_RGB = (0xFF, 0x6B, 0x6B)
_RESET = "\x1b[0m"


def _norm_phase(phase: str) -> str:
    p = str(phase or DEFAULT_PHASE)
    return p if p in _GLYPHS else DEFAULT_PHASE


def frames_for(phase: str) -> List[str]:
    """阶段的帧序列（认不出的阶段退回默认，不抛）。"""
    return list(_GLYPHS[_norm_phase(phase)][0])


def phase_interval(phase: str) -> float:
    """阶段的帧间隔（秒）——**速度本身是语义**。"""
    return float(_GLYPHS[_norm_phase(phase)][1])


def frame_at(phase: str, elapsed: float, reduced_motion: bool = False) -> str:
    """当前该显示哪一帧；`reduced_motion` 时固定首帧（不动也能看出状态）。"""
    frames = frames_for(phase)
    if reduced_motion:
        return frames[0]
    idx = int(max(0.0, float(elapsed)) / phase_interval(phase)) % len(frames)
    return frames[idx]


def stall_level(idle_secs: float, threshold: float = DEFAULT_STALL_SECONDS) -> float:
    """"卡住程度" 0→1：静默超过阈值后随时间递增（有活跃工具时调用方不该调它）。"""
    try:
        idle = max(0.0, float(idle_secs))
        th = max(0.1, float(threshold))
    except (TypeError, ValueError):
        return 0.0
    if idle <= th:
        return 0.0
    return min(1.0, (idle - th) / (th * 2))       # 再过一个阈值时长到满


def _lerp_rgb(a: Sequence[int], b: Sequence[int], level: float) -> Tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * float(level))) for i in range(3))  # type: ignore[return-value]


def stall_color(level: float, truecolor: bool = True) -> str:
    """卡住程度 → ANSI 颜色码。

    真彩：主题色与告警色之间**平滑插值**；低色深：**过半处离散跳到告警色**（降级后
    "不太对"的语义仍然成立，而不是变成一个看不出差别的中间色）。
    """
    lv = max(0.0, min(1.0, float(level or 0.0)))
    if lv <= 0.0:
        if truecolor:
            return f"\x1b[38;2;{THEME_RGB[0]};{THEME_RGB[1]};{THEME_RGB[2]}m"
        return "\x1b[32m"
    if not truecolor:
        return "\x1b[31m" if lv > 0.5 else "\x1b[33m"
    r, g, b = _lerp_rgb(THEME_RGB, WARN_RGB, lv)
    return f"\x1b[38;2;{r};{g};{b}m"


def spinner_line(phase: str, elapsed: float, idle: float = 0.0,
                 label: str = "", reduced_motion: bool = False,
                 truecolor: bool = True, width: int = 0,
                 color: bool = True,
                 stall_seconds: float = DEFAULT_STALL_SECONDS,
                 active_tool: bool = False) -> str:
    """等待行：`◐ 正在读取 x.py 3s`（颜色随卡住程度过渡）。

    `active_tool=True`（工具正在跑）时**不做卡住判定** —— 一条长命令跑 60 秒是正常的，
    把它染成告警色只会教用户忽略颜色。
    """
    glyph = frame_at(phase, elapsed, reduced_motion)
    secs = int(max(0.0, float(elapsed)))
    text = f"{glyph} {label}".rstrip()
    text += f" {secs}s"
    level = 0.0 if active_tool else stall_level(idle, stall_seconds)
    if level > 0.0 and not reduced_motion:
        text = f"{stall_color(level, truecolor)}{text}{_RESET}"
    elif level > 0.0:
        # 无动效：用文字编码代替颜色动画（静态也能看出"卡了"）
        text += "  (无响应)"
    return truncate_width(text, width) if width and width > 0 else text
