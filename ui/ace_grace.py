#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ui.ace_grace —— 危险对话框的"防误触宽限期"（纯逻辑，可穷举测试）

## 要解决的问题

模型还在跑、用户以为还在等，于是随手敲了个回车想"催一下"。就在这一刻授权对话框
弹出来，那个回车**落在了对话框上** —— 一次误触变成了一次放行。这不是理论风险：
`input()` 的缓冲会把对话框出现前敲的键原样喂给它。

## 判定口径

对话框贴出的时刻记 `t0`；答案回来的时刻记 `t1`。**人在 200ms 内不可能读完一个三选一
的对话框再作答**，所以 `t1 - t0 < 宽限期` 的答案一律判为"上一个动作里飞过来的按键"，
丢弃并重新问一次 —— 方向永远是**收紧**（丢掉的答案按"没回答"处理，而不是按"同意"）。

反过来，粘贴一整段 `1\n` 也可能落在宽限期内：那是用户主动要放行，代价只是多点一次。
安全侧多问一句，比放行一次误触便宜得多。

宽限期可用 `ACE_PERM_GRACE_MS` 调（`0` = 关掉）。上限 5000ms：再长就变成"对话框反应
迟钝"，用户会以为程序卡住 —— 这条保护自己不能成为新的问题。
"""

from __future__ import annotations

import os
import time
from typing import Optional

__all__ = ["GRACE_MS_DEFAULT", "GRACE_MS_MAX", "grace_ms_from_env", "wrong_time",
           "is_inflight", "GraceGate"]

GRACE_MS_DEFAULT = 200
GRACE_MS_MAX = 5000
GRACE_MS_MIN = 0
# 最多重问几次：两次都判成飞行按键，说明这不是误触（可能是自动化脚本在喂输入），
# 再拦下去就变成"用户明明答了却永远进不去"。
MAX_DISCARDS = 2


def grace_ms_from_env(env: Optional[dict] = None) -> int:
    """读 `ACE_PERM_GRACE_MS`；缺失/写坏/越界都落回默认值（配置错误不改安全口径）。"""
    raw = (env if env is not None else os.environ).get("ACE_PERM_GRACE_MS")
    if raw is None or str(raw).strip() == "":
        return GRACE_MS_DEFAULT
    try:
        val = int(str(raw).strip())
    except (TypeError, ValueError):
        return GRACE_MS_DEFAULT
    if val < GRACE_MS_MIN or val > GRACE_MS_MAX:
        return GRACE_MS_DEFAULT
    return val


def is_inflight(elapsed_s: float, grace_ms: int) -> bool:
    """答案来得比宽限期还快 → 判为飞行按键。宽限期为 0 时一律放行（用户显式关掉）。"""
    if grace_ms <= 0:
        return False
    try:
        return float(elapsed_s) * 1000.0 < float(grace_ms)
    except (TypeError, ValueError):
        return False


def wrong_time(now: float, t0: float, grace_ms: int) -> bool:
    """`is_inflight` 的时刻版：给调用方少算一次减法。"""
    return is_inflight(float(now) - float(t0), grace_ms)


class GraceGate:
    """一次对话框对应的闸门：`arm()` 开表，`admit()` 判这个答案算不算数。

    `now` 可注入 —— 测试不靠 `sleep`，靠假时钟（否则要么慢，要么偶发）。
    """

    def __init__(self, grace_ms: Optional[int] = None) -> None:
        self.grace_ms = grace_ms_from_env() if grace_ms is None else int(grace_ms)
        self.discarded = 0
        self._t0: Optional[float] = None

    def arm(self, now: Optional[float] = None) -> float:
        self._t0 = time.monotonic() if now is None else float(now)
        return self._t0

    def admit(self, now: Optional[float] = None) -> bool:
        """`True` = 这个答案算数；`False` = 判为飞行按键（已计入 `discarded`）。"""
        if self._t0 is None:
            return True
        _now = time.monotonic() if now is None else float(now)
        if wrong_time(_now, self._t0, self.grace_ms):
            self.discarded += 1
            return False
        return True

    @property
    def exhausted(self) -> bool:
        """重问次数用尽：再问下去就是把用户锁在门外，调用方应当直接采纳下一个答案。"""
        return self.discarded >= MAX_DISCARDS
