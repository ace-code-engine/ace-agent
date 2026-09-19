#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_diff —— 工具改动过的内容，把"改了哪几行"摆到屏幕上

为什么需要：`file_write` / `str_replace` 此前只报一行
`  r file_write ✓ [SUCCESS] · 0.01s` —— 用户看不到**到底改了哪几行**。跑错一条
命令当场就知道，改错一行往往几天后才发现，所以"改动可见"比"命令可见"更要紧。
工具侧已经产出事实（`str_replace` 返回 `data["diff"]`，`file_write` 在有旧内容时
同样给一份），这里只负责把它渲染成人能扫的 +/− 行。

纯函数、不打印、**不带颜色**：颜色由调用方按行首标记上（`+` 绿 / `-` 红 / `@@` 青），
这样既好测，也保持"卡片是纯文本"这条既有约定。宽度口径复用 `ui.ace_text`
（CJK 两列、ANSI 零宽）。
"""

from typing import Any, Dict, List, Tuple

from ui.ace_text import ELLIPSIS, display_width, truncate_width

__all__ = ["looks_like_diff", "summarize_diff", "diff_marker", "color_name",
           "colorize_diff", "stat_text", "split_for_display", "MAX_DIFF_LINES"]

# 一张卡里最多显示多少行 diff（多出来的走折叠提示 → /expand 看完整）
MAX_DIFF_LINES = 200


def looks_like_diff(text: str) -> bool:
    """这段文本看起来是 unified diff 吗？

    判据刻意保守（要求 `@@` 或 `---`/`+++` 成对出现）：工具输出里以 `+`/`-` 开头的行
    很常见（表格、列表、密码学里的加减号），只按首字符判断会把普通输出误染成 diff。
    """
    if not text or not isinstance(text, str):
        return False
    lines = text.splitlines()
    if any(ln.startswith("@@") for ln in lines):
        return True
    has_old = any(ln.startswith("--- ") for ln in lines)
    has_new = any(ln.startswith("+++ ") for ln in lines)
    return has_old and has_new


def summarize_diff(text: str) -> Dict[str, Any]:
    """diff 统计：{added, removed, files}。

    `+++`/`---` 文件头不计入增删行（否则每个 diff 都"删了一行加了"一行"，
    数字就没意义了）——这是 diff 统计最容易错的一处。
    """
    added = removed = 0
    files: List[str] = []
    for ln in (text or "").splitlines():
        if ln.startswith("+++ ") or ln.startswith("--- "):
            name = ln[4:].strip()
            if name and name not in ("/dev/null",) and name not in files:
                files.append(name.split("\t")[0])
            continue
        if ln.startswith("@@"):
            continue
        if ln.startswith("+"):
            added += 1
        elif ln.startswith("-"):
            removed += 1
    return {"added": added, "removed": removed, "files": files}


def diff_marker(line: str) -> str:
    """行首标记：'+' / '-' / '@' / ' ' / '?'（不是 diff 行）。"""
    if not line:
        return "?"
    ch = line[0]
    return ch if ch in "+-@ " else "?"


def color_name(line: str) -> str:
    r"""行 → 颜色名（给调用方上色用）：加绿、减红、区块头与文件头青/dim、其余 dim。

    文件头（`--- a/x` / `+++ b/x`）按 dim 处理而不是红/绿：它们不是"删了这行、
    加了那行"，染成红绿会让每次 diff 都显得先删后加一整行。
    `\ No newline at end of file` 这类注解同样走 dim。
    """
    if line.startswith("--- ") or line.startswith("+++ "):
        return "dim"
    return {"+": "green", "-": "red", "@": "cyan", " ": "dim"}.get(
        diff_marker(line), "dim")


def colorize_diff(text: str, width: int = 0, max_lines: int = MAX_DIFF_LINES) -> List[str]:
    """diff 文本 → 待打印行（纯文本，颜色由调用方按 `color_name()` 上）。

    - 按**显示宽度**截断到 `width`（0 = 不限），中文行不会顶破终端；
    - 超过 `max_lines` 时截断并追加一行说明（**不冒充完整**，用户可 `/expand`）；
    - 空输入返回空列表。
    """
    if not text:
        return []
    out: List[str] = []
    lines = text.splitlines()
    capped = len(lines) > max_lines
    for ln in lines[:max_lines]:
        out.append(truncate_width(ln, width) if width and width > 0 else ln)
    if capped:
        out.append(f"… {len(lines) - max_lines} {ELLIPSIS}")
    return out


def stat_text(text: str) -> str:
    """一行统计：`+3 -1`（无改动时返回空串，让调用方不显示）。"""
    s = summarize_diff(text)
    if not s["added"] and not s["removed"]:
        return ""
    return f"+{s['added']} -{s['removed']}"


def split_for_display(text: str, width: int = 0,
                      max_lines: int = MAX_DIFF_LINES) -> List[Tuple[str, str]]:
    """渲染用的一步到位接口：[(行, 颜色名)]。

    给终端直接消费；纯函数，`+`/`-`/`@@` 的颜色就在这里定好，调用方不必再判一次。
    """
    return [(ln, color_name(ln)) for ln in colorize_diff(text, width, max_lines)]
