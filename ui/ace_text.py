#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_text —— 终端文本宽度（CJK 占两列）

为什么单独成模块：需要它的地方不止一处 —— 工具结果卡片（按列截断）、搜索式选择器
（行宽与对齐）、演示录制的 SVG 画布宽度。而 `len()` 数的是**码点**：一个汉字在终端里
占两列，于是"截到 60 字"的中文行实际能占 120 列，卡片边框当场错位。中文优先的工具
里这是硬伤，不是审美问题。

刻意不引入 wcwidth：核心零依赖是这个项目的硬约束。终端排版实际会遇到的字符远少于
Unicode 全表，`east_asian_width` 的 W/F 两类 + 组合符/零宽字符已经覆盖绝大部分场景。

近似之处（写在明面上，不假装精确）：
- 部分 emoji 的 `east_asian_width` 是 'N'，按 1 列算，而终端常按 2 列画 —— 各家终端
  自己就不统一，这里按 Unicode 数据给一个稳定答案，不做终端探测。
- **Ambiguous（A）类按 1 列算**，包括省略号 `…`（U+2026）。在 CJK locale 的终端里它
  常被画成 2 列，所以极窄的限宽下仍可能差 1 列。取"按 1 列算"是因为这批字符在
  ASCII 语境里是主流用法，且 `truncate_width` 的硬保证是**按本模块的口径不超限**，
  不是"在每种终端上都恰好占满"。
- 变体选择符（U+FE0F）按零宽处理；某些终端会把 "❤️" 画成 2 列。

纯函数、无副作用，可直接单测。

**ANSI 感知**：`display_width` / `truncate_width` / `pad_width` 都忽略 SGR 转义序列
（`\x1b[...m`）—— 否则给一行加上颜色之后，宽度就会凭空多出十几个"列"，边框当场
错位。`truncate_width` 会保留序列本身，并在真的截断时补一个复位码，避免颜色漏到
后面的行上。
"""

import re
from typing import List

__all__ = ["char_width", "display_width", "truncate_width", "pad_width",
           "strip_ansi", "ELLIPSIS", "SEPARATORS"]

ELLIPSIS = "…"

# SGR（颜色/样式）序列：终端里不占列，但 `len()` 会数进去。
_ANSI_SGR = re.compile(r"\x1b\[[0-9;]*m")
_ANSI_SPLIT = re.compile(r"(\x1b\[[0-9;]*m)")
_ANSI_RESET = "\x1b[0m"


def _tokenize(text: str):
    """把字符串拆成 ("ansi", 序列) / ("ch", 单字符) 两种 token（ANSI 零宽）。"""
    for part in _ANSI_SPLIT.split(text):
        if not part:
            continue
        if _ANSI_SGR.fullmatch(part):
            yield "ansi", part
        else:
            for ch in part:
                yield "ch", ch

# 词边界：搜索评分用（`-v4` 里的 v 比词中的 v 值钱）。
SEPARATORS = " \t-_/.:,()[]{}<>|"

# 零宽字符：终端里不占列，但 `len()` 会数进去。
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\u200e\u200f\u2060\ufeff")


def char_width(ch: str) -> int:
    """单个字符在终端里占几列（近似）。

    0 = 组合符（Mn/Me，如声调符号）与零宽字符
    2 = East_Asian_Width 是 W/F 的（汉字、全角标点、多数 emoji）
    1 = 其余
    """
    import unicodedata
    if ch in _ZERO_WIDTH or unicodedata.category(ch) in ("Mn", "Me"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def strip_ansi(text: str) -> str:
    """去掉 SGR 颜色/样式序列（只处理 `ESC[...m` 这一类）。"""
    return _ANSI_SGR.sub("", text)


def display_width(text: str) -> int:
    """整串的**可见**显示宽度（列数）；ANSI 颜色码不计入。"""
    return sum(char_width(ch) for ch in strip_ansi(text))


def truncate_width(text: str, limit: int, ellipsis: str = ELLIPSIS) -> str:
    """按**显示宽度**截断到 limit 列，超长时尾部替换成省略号。

    规则：
    - limit <= 0 → 空串
    - 放得下省略号才加省略号；放不下就硬切（宁短不超）
    - 绝不把双宽字符劈成一半：累计到放不下就停
    - ANSI 序列零宽且原样保留；截断处补复位码，避免颜色漏到下一行

    >>> truncate_width("中文中文", 6)
    '中文中…'
    >>> truncate_width("abcdef", 4)
    'abc…'
    """
    limit = int(limit)
    if limit <= 0:
        return ""
    if display_width(text) <= limit:
        return text
    ell_w = display_width(ellipsis)
    use_ellipsis = limit > ell_w
    budget = limit - ell_w if use_ellipsis else limit
    out: List[str] = []
    used = 0
    colored = False
    for kind, val in _tokenize(text):
        if kind == "ansi":
            out.append(val)              # 零宽，原样保留
            colored = True
            continue
        w = char_width(val)
        if used + w > budget:
            break
        out.append(val)
        used += w
    return ("".join(out) + (ellipsis if use_ellipsis else "")
            + (_ANSI_RESET if colored else ""))


def pad_width(text: str, width: int, fill: str = " ") -> str:
    """右侧补空格到 width 列（按**可见**宽度算，ANSI 不计入）。

    已经够宽时**原样返回**，不截断 —— 截断是调用方的决定（想两者都要就用
    `pad_width(truncate_width(t, w), w)`）。`fill` 只取第一个字符，避免误传多字符
    字符串时补出一串奇怪的东西。
    """
    pad = int(width) - display_width(text)
    if pad <= 0:
        return text
    return text + (fill[:1] or " ") * pad
