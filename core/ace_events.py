#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_events —— 机器可读的事件流（`ace --json`）

为什么需要：终端界面是给人看的，脚本/CI/其它前端（DSH 这类）需要的是**结构化事实**。
此前只有"人看的输出"一条路，于是想做自动化就只能去截屏式地解析人话 —— 那种接口
改一个字就碎。这里给出第二条通道：一行一个 JSON 对象，字段有契约、有断言。

事件契约（stdout，每行一个 JSON 对象；**没有 ANSI、没有 \r 重绘、没有进度条**）：

| type | 必有字段 | 说明 |
|---|---|---|
| `session_start` | `version` `permission` `sandbox` `project_root` | 会话建立 |
| `user_message` | `text` | 用户这一轮说了什么 |
| `model_request` | `round` `messages_count` `system_len` | 每次模型请求的 envelope |
| `tool_call` | `tool` `params` | 模型要调工具 |
| `tool_result` | `tool` `status` `elapsed` `message` | 工具结果（`data` 可能很大） |
| `permission_request` | `tool` `reason` | 需要审批（非交互下随后会被拒） |
| `notice` | `text` | 人看的输出被转成事件（这样"人话"也不会丢） |
| `final` | `text` | 模型的最终回复 |
| `session_end` | `rounds` `tools` `violations` `elapsed` | 会话结束 |

明说没做的：**不流式发 model_delta**（一次回复可能几千条 delta，灌进事件流只会让
消费者自己再攒一遍）。要增量请用 SDK 层自己接 `on_delta`。

纯逻辑（事件构造、schema 校验）与输出分离：前者可单测，后者只负责写一行 JSON。
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Any, Dict, List, Optional

__all__ = ["EVENT_TYPES", "EVENT_REQUIRED", "make_event", "validate_event",
           "EventEmitter", "NoticeProxy", "strip_ansi"]

EVENT_TYPES = ("session_start", "user_message", "model_request", "tool_call",
               "tool_result", "permission_request", "notice", "final", "session_end")

# 每个事件的必需字段（校验与文档的唯一来源）
EVENT_REQUIRED: Dict[str, tuple] = {
    "session_start": ("version", "permission", "sandbox", "project_root"),
    "user_message": ("text",),
    "model_request": ("round", "messages_count", "system_len"),
    "tool_call": ("tool", "params"),
    "tool_result": ("tool", "status", "elapsed"),
    "permission_request": ("tool", "reason"),
    "notice": ("text",),
    "final": ("text",),
    "session_end": ("rounds", "tools", "elapsed"),
}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """去掉 ANSI 颜色码（事件流里不该有颜色 —— 消费者不是终端）。"""
    return _ANSI.sub("", text or "")


def make_event(type_: str, **fields: Any) -> Dict[str, Any]:
    """构造一个事件（纯函数）。未知类型照样产出 —— 但 `validate_event` 会报出来。"""
    ev: Dict[str, Any] = {"type": str(type_), "ts": round(time.time(), 3)}
    for k, v in fields.items():
        ev[str(k)] = v
    return ev


def validate_event(ev: Any) -> List[str]:
    """校验一个事件：返回问题列表（空 = 合法）。纯函数，可单测。

    只查"类型对不对、必需字段在不在、值能不能 JSON 序列化"这三件**契约**的事，
    不校验业务语义 —— 后者由各自的断言盯着。
    """
    problems: List[str] = []
    if not isinstance(ev, dict):
        return ["事件不是对象"]
    t = ev.get("type")
    if not isinstance(t, str) or not t:
        problems.append("缺少 type")
        return problems
    if t not in EVENT_TYPES:
        problems.append(f"未知事件类型: {t}")
        return problems
    for field in EVENT_REQUIRED.get(t, ()):
        if field not in ev:
            problems.append(f"{t} 缺少字段 {field}")
    if not isinstance(ev.get("ts"), (int, float)):
        problems.append(f"{t} 缺少时间戳 ts")
    try:
        json.dumps(ev, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        problems.append(f"{t} 不能 JSON 序列化: {e}")
    return problems


class EventEmitter:
    """写事件流：`emit(type, **fields)` → 一行 JSON。

    - 字段里出现不可序列化的对象时用 `default=str` 兜底（**不抛异常**：事件流断了
      比字段变成字符串更糟）
    - `enabled=False` 时是空操作，调用方不必到处判断
    """

    def __init__(self, stream: Any = None, enabled: bool = True) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self.enabled = bool(enabled)
        self.count = 0
        self.by_type: Dict[str, int] = {}

    def emit(self, type_: str, **fields: Any) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        ev = make_event(type_, **fields)
        self.count += 1
        self.by_type[type_] = self.by_type.get(type_, 0) + 1
        try:
            self.stream.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            self.stream.flush()
        except (OSError, ValueError):
            pass
        return ev

    def close(self) -> None:
        try:
            self.stream.flush()
        except (OSError, ValueError):
            pass


class NoticeProxy:
    """把"人看的输出"转成 `notice` 事件（`--json` 模式下替换 sys.stdout）。

    为什么用代理而不是把每处 print 都改掉：这个项目的输出点有几百处，
    逐个改既改不完、也会让后来人随手又加一处裸 print。代理是**一处生效**的。

    两件必须做的事：
    - 丢掉 `\\r` 重绘（进度条/转轮）—— 事件流里那些只会变成垃圾
    - 剥掉 ANSI 颜色码 —— 消费者不是终端
    """

    def __init__(self, emitter: EventEmitter, real: Any = None) -> None:
        self.emitter = emitter
        self.real = real if real is not None else sys.__stdout__
        self._buf = ""
        self.encoding = getattr(self.real, "encoding", "utf-8")
        self.errors = getattr(self.real, "errors", "replace")

    # ---- 类文件接口（print 依赖的就是这些） ----
    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        if "\r" in text:
            # 转轮/进度条：整条丢掉（连同尚未落盘的半行）。
            # 为什么不是"只取 \r 之后那一段"：转轮每 0.12s 重绘一次，把最后一段留下
            # 会在结束换行时把它当 notice 发出去 —— 事件流里就多出一堆 "◈ 思考中 0s"。
            self._buf = ""
            return len(text)
        self._buf += text
        while "\n" in self._buf:
            line, _, self._buf = self._buf.partition("\n")
            self._emit_line(line)
        return len(text)

    def _emit_line(self, line: str) -> None:
        clean = strip_ansi(line).rstrip()
        if not clean.strip():
            return
        self.emitter.emit("notice", text=clean)

    def flush(self) -> None:
        if self._buf:
            self._emit_line(self._buf)
            self._buf = ""
        try:
            self.real.flush()
        except (OSError, ValueError):
            pass

    def isatty(self) -> bool:
        """恒 False：JSON 模式下不该有人以为自己在跟终端说话。"""
        return False

    def fileno(self) -> int:
        return self.real.fileno()

    def close(self) -> None:
        self.flush()
