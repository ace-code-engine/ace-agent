#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_term —— 终端能力自检：能自动判的自动判，判不了的问人

为什么需要：终端能力决定了"界面能开到什么程度" —— 没有真彩就别上渐变、没有备用屏幕就
别进全屏、`Unicode` 不可靠时得换 ASCII 符号（本项目在 Windows GBK 控制台上就吃过一次
方框字的亏）。这些东西**大部分能自动探测**（环境变量 + `isatty` + `TERM`），但有两件
事探不出来：**"你屏幕上看到的颜色对不对"** 和 **"滚轮/鼠标真的有用吗"** —— 前者要人看
一眼，后者要人动一下。所以这里两条路：

- `detect_capabilities()`：纯函数，从环境变量/是否 TTY/平台推出每项 `yes`/`no`/`unknown`；
- `probe_steps()`：用人能答的 3 个问题（看到彩色了吗 / 方块字有没有 / 滚轮管用吗）
  覆盖掉探测结果，由 `ui/ace_dialog` 的向导框架跑（本模块只出**步骤定义**，不弹框）。

`unknown` 不是凑数：探不出来就说探不出来，界面据此走保守分支，而不是假装支持然后画花屏。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

__all__ = ["CAPABILITIES", "CAP_LABELS", "detect_capabilities", "capability_rows",
           "probe_steps", "apply_probe", "summarize"]

# 能自动判定的能力项（顺序 = 展示顺序）
CAPABILITIES: Tuple[str, ...] = (
    "color", "truecolor", "unicode", "alt_screen", "bracketed_paste",
    "mouse", "hyperlinks",
)
CAP_LABELS: Dict[str, str] = {
    "color": "cap_color", "truecolor": "cap_truecolor", "unicode": "cap_unicode",
    "alt_screen": "cap_alt_screen", "bracketed_paste": "cap_bracketed_paste",
    "mouse": "cap_mouse", "hyperlinks": "cap_hyperlinks",
}
_YES, _NO, _UNK = "yes", "no", "unknown"


def detect_capabilities(env: Dict[str, str], isatty: bool = True,
                        platform: str = "linux",
                        term: str = "") -> Dict[str, str]:
    """环境 → 每项 `yes`/`no`/`unknown`（纯函数：env/平台都从参数进）。

    - `NO_COLOR` 是用户的明确要求，优先级最高（哪怕 `TERM` 说支持真彩）；
    - `COLORTERM=truecolor|24bit` 才算真彩，`TERM` 里带 `256color` 只说明 256 色；
    - `alt_screen`/`bracketed_paste`/`mouse` 需要 TTY 才有意义（管道里一律 no）；
    - Windows 上 `WT_SESSION`（Windows Terminal）才敢说 bracketed paste 与鼠标可靠，
      旧 conhost 一律 unknown —— 这正是本项目踩过的那个坑。
    """
    e = {str(k): str(v) for k, v in (env or {}).items()}
    t = (term or e.get("TERM", "") or "").lower()
    plat = (platform or "").lower()
    out: Dict[str, str] = {}

    if not isatty:
        return {c: _NO for c in CAPABILITIES}
    if e.get("NO_COLOR"):
        out["color"] = out["truecolor"] = _NO
    else:
        out["color"] = _YES if (t and t != "dumb") or e.get("COLORTERM") else _UNK
        ct = str(e.get("COLORTERM", "")).lower()
        out["truecolor"] = _YES if ct in ("truecolor", "24bit") else _NO

    enc = str(e.get("PYTHONIOENCODING", "") or e.get("LC_ALL", "")
              or e.get("LANG", "")).lower()
    if plat.startswith("win"):
        out["unicode"] = _YES if e.get("WT_SESSION") else _UNK
    else:
        out["unicode"] = _YES if "utf-8" in enc or "utf8" in enc else _UNK

    out["alt_screen"] = _YES if t and t != "dumb" else _UNK
    if plat.startswith("win"):
        out["bracketed_paste"] = _YES if e.get("WT_SESSION") else _UNK
        out["mouse"] = _YES if e.get("WT_SESSION") else _UNK
    else:
        out["bracketed_paste"] = _YES
        out["mouse"] = _YES if "xterm" in t or "kitty" in t or "wezterm" in t else _UNK
    out["hyperlinks"] = _YES if ("kitty" in t or "wezterm" in t
                                 or "vte" in t or e.get("VTE_VERSION")) else _UNK
    return out


def capability_rows(caps: Dict[str, str], translate=None
                    ) -> List[Tuple[str, str, str]]:
    """→ `[(能力 id, 说明 i18n 键, 结论)]`，供调用方排版（本模块不打印、不翻译）。"""
    tr = translate or (lambda k: k)
    rows: List[Tuple[str, str, str]] = []
    for cap in CAPABILITIES:
        rows.append((cap, tr(CAP_LABELS.get(cap, cap)), str((caps or {}).get(cap, _UNK))))
    return rows


def summarize(caps: Dict[str, str]) -> str:
    """一句话结论：全支持 = full / 有 unknown = partial / 有 no = limited。

    界面按这三档决定"能开到什么程度"，而不是逐项去 if。
    """
    vals = [str((caps or {}).get(c, _UNK)) for c in CAPABILITIES]
    if all(v == _YES for v in vals):
        return "full"
    if any(v == _NO for v in vals):
        return "limited"
    return "partial"


def probe_steps(translate=None) -> List[Any]:
    """自检向导的步骤（3 个"人看一眼就能答"的问题）。

    只做**自动探测答不了**的那几项：颜色对不对、方块字有没有、滚轮管不管用。
    其余项（真彩/备用屏幕）自动探测已经够准，问人也只是让人烦。
    返回 `ui.ace_dialog.WizardStep` 列表；`translate` 缺省时用 i18n 键名（测试用）。
    """
    from ui.ace_dialog import WizardStep
    tr = translate or (lambda k: k)

    def _yn(answer: str) -> str:
        return "" if str(answer).strip().lower() in ("y", "yes", "1", "是", "对") \
            else "cap_probe_need_yn"

    return [
        WizardStep("color", tr("cap_probe_color"), tr("cap_probe_color_ask"),
                   default="y", choices=["y", "n"], validate=_yn),
        WizardStep("unicode", tr("cap_probe_unicode"), tr("cap_probe_unicode_ask"),
                   default="y", choices=["y", "n"], validate=_yn),
        WizardStep("mouse", tr("cap_probe_mouse"), tr("cap_probe_mouse_ask"),
                   default="n", choices=["y", "n"], validate=_yn),
    ]


def apply_probe(caps: Dict[str, str], answers: Dict[str, str]) -> Dict[str, str]:
    """把向导答案覆盖到探测结果上（人看过的答案 > 环境变量推断）。"""
    out = dict(caps or {})
    for key, ans in (answers or {}).items():
        if key not in CAPABILITIES:
            continue
        out[key] = _YES if str(ans).strip().lower() in ("y", "yes", "1", "是", "对") \
            else _NO
    return out


def env_snapshot() -> Dict[str, str]:
    """当前进程的相关环境变量（探测的输入；单独一层便于断言与打印）。"""
    keys = ("TERM", "COLORTERM", "NO_COLOR", "VTE_VERSION", "WT_SESSION",
            "PYTHONIOENCODING", "LANG", "LC_ALL", "TERM_PROGRAM")
    return {k: os.environ.get(k, "") for k in keys if os.environ.get(k)}
