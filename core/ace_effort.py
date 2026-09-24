#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_effort —— 思考强度：档位、提示词增量、显示符号（纯逻辑）

## 两条轴要分开（这是核实过上游之后学到的第一条）

- **思考开不开 / 看不看得见**：ACE 的 `/thinking` 管"显示不显示思考过程"；
- **想多深**：本模块管的这件事。

把它们混成一个开关，用户就没法回答"我想看推理，但不想让它为此多花三倍时间"。

## 档位

| 档位 | 符号 | 面向 | 提示词增量 |
| --- | --- | --- | --- |
| `auto` | `○` | 默认：**不加任何话** | 空（不污染默认行为） |
| `low` | `◐` | 查事实、改错字 | 直接给结论与最小改动 |
| `medium` | `●` | 日常开发 | 先想清关键取舍，只说影响结论的那几句 |
| `high` | `◉` | 架构 / 疑难 | 列假设与备选、逐条权衡、说明为什么否掉别的 |

**`auto` 是默认档**：默认不该被我们的偏好污染 —— 不加话，模型用它自己的默认。
「四档 + auto」来自上游核实的结论（上游是 low/medium/high/max 四档 + unset 即 auto），
这里保留了"不设置"这个档，但把最上面那档叫 `high`（我们不假定哪家的模型更强，
所以不设"只有某个模型才能用"的 `max`）。

## 关键词逃生门

提示里出现 `ultrathink`（或 `认真想`）→ **这一轮**按最高档处理，并在界面上说一声。
好处是零 UI 成本：想让它多想一会儿时，敲一个词就行，不用先去改设置。
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = ["EFFORTS", "EFFORT_ORDER", "DEFAULT_EFFORT", "SYMBOLS", "EFFORT_KEYS",
           "normalize", "cycle", "prompt_hint", "labels", "symbol", "describe",
           "parse_command", "keyword_level", "KEYWORDS", "badge", "is_auto"]

EFFORT_ORDER: Tuple[str, ...] = ("auto", "low", "medium", "high", "max")
EFFORTS = EFFORT_ORDER
DEFAULT_EFFORT = "auto"
TOP_EFFORT = "max"        # 关键词逃生门落在最高档

#: 显示符号：一个字形就能看出档位（底栏/主页都用它，省列宽）
SYMBOLS: Dict[str, str] = {"auto": "○", "low": "◐", "medium": "●",
                         "high": "◉", "max": "◆"}

#: 档位 → (名字 i18n 键, 说明 i18n 键)
EFFORT_KEYS: Dict[str, Tuple[str, str]] = {
    "auto": ("effort_auto", "effort_auto_what"),
    "low": ("effort_low", "effort_low_what"),
    "medium": ("effort_medium", "effort_medium_what"),
    "high": ("effort_high", "effort_high_what"),
    "max": ("effort_max", "effort_max_what"),
}

#: 每档的提示词增量。空串 = 什么都不加（默认行为不该被我们的偏好污染）
_HINTS: Dict[str, str] = {
    "auto": "",
    "low": ("【思考强度：低】直接给结论与最小改动：不要列备选方案，"
            "不要说明你考虑过什么，不要在开头复述我的要求。"),
    "medium": ("【思考强度：中】动手前先把关键取舍想清楚（改哪里、会不会连带影响、"
               "怎么验证），但只把影响结论的那一两句说出来，不要长篇推演。"),
    "high": ("【思考强度：高】先列出你的假设与约束，再给出至少两个备选方案并逐条权衡"
             "（代价、风险、回退难度），明确说明为什么否掉其它方案，最后才动手；"
             "结论要能被别人复核。"),
    "max": ("【思考强度：最高】在「高」的基础上再加三条：①先把问题**重述一遍**，"
            "确认我们要解决的是同一件事；②列出你打算怎么**验证**结论（测试、复现步骤、"
            "反例）；③明确说出你不确定的地方与它会影响什么。宁可多花时间，不要给一个"
            "看起来完整但没验证过的答案。"),
}

#: 关键词逃生门：出现即"这一轮按最高档"，不必先去改设置
KEYWORDS: Tuple[str, ...] = ("ultrathink", "认真想", "深入思考")
_KEY_RE = re.compile(r"|".join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)


def normalize(name: str) -> str:
    """把用户写法收敛到档位名：写坏/空 → `auto`（**不抛异常，也不静默变高**）。"""
    key = str(name or "").strip().lower()
    alias = {"auto": "auto", "": "auto", "unset": "auto", "default": "auto",
             "自动": "auto", "默认": "auto", "-": "auto",
             "low": "low", "min": "low", "低": "low", "quick": "low", "1": "low",
             "medium": "medium", "mid": "medium", "中": "medium", "2": "medium",
             "high": "high", "深": "high", "3": "high",
             "max": "max", "maximum": "max", "ultra": "max", "高": "high",
             "最高": "max", "4": "max"}
    return alias.get(key, DEFAULT_EFFORT)


def is_auto(level: str) -> bool:
    return normalize(level) == DEFAULT_EFFORT


def cycle(current: str, step: int = 1) -> str:
    """档位环：auto → low → medium → high → auto（传 -1 倒着走）。"""
    cur = normalize(current)
    i = EFFORT_ORDER.index(cur)
    return EFFORT_ORDER[(i + int(step)) % len(EFFORT_ORDER)]


def prompt_hint(level: str) -> str:
    """这一档要往系统提示里加的话；空串表示什么都不加。"""
    return _HINTS.get(normalize(level), "")


def symbol(level: str) -> str:
    return SYMBOLS.get(normalize(level), SYMBOLS[DEFAULT_EFFORT])


def labels(level: str) -> Tuple[str, str]:
    """`(名字 i18n 键, 说明 i18n 键)`。"""
    return EFFORT_KEYS.get(normalize(level), EFFORT_KEYS[DEFAULT_EFFORT])


def badge(level: str, translate: Optional[Callable[[str], str]] = None) -> str:
    """一行短标记：`◉ 高 · /effort`（底栏与提示条都用它，自带"怎么改"）。"""
    tr = translate or (lambda k: k)
    lv = normalize(level)
    return f"{symbol(lv)} {tr(EFFORT_KEYS[lv][0])} · /effort"


def describe(translate: Optional[Callable[[str], str]] = None
             ) -> List[Tuple[str, str, str]]:
    """全部档位的 `(档位, 符号, 说明)`，给选择框/帮助用。"""
    tr = translate or (lambda k: k)
    return [(e, SYMBOLS[e], tr(EFFORT_KEYS[e][1])) for e in EFFORT_ORDER]


def keyword_level(text: str) -> Optional[str]:
    """这段输入里有没有"这一轮多想一会儿"的关键词；有就返回最高档，否则 None。"""
    return TOP_EFFORT if _KEY_RE.search(str(text or "")) else None


def parse_command(parts: Sequence[str], current: str = DEFAULT_EFFORT
                  ) -> Tuple[Optional[str], str]:
    """`/effort [档|next|prev|list]` → `(新档位 或 None, 提示码)`。

    返回 `None` 表示"只是看看"（调用方显示当前档）；提示码由调用方翻译 ——
    本模块不碰 i18n、不打印、不读配置。
    """
    arg = (parts[1].lower().strip() if len(parts) > 1 else "")
    if not arg:
        return None, "effort_show"
    if arg in ("next", "+", "下一档", "下"):
        return cycle(current, 1), "effort_set"
    if arg in ("prev", "-", "上一档", "上"):
        return cycle(current, -1), "effort_set"
    if arg in ("list", "?", "help", "帮助"):
        return None, "effort_list"
    return normalize(arg), "effort_set"
