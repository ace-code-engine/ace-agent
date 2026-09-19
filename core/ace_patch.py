#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_patch —— 最小 unified diff 应用器（给人改过的补丁回填用）

为什么需要它：`/review` 会把上一处改动写成一份补丁、在编辑器里打开给你改，然后
**把你改过的补丁回填到源文件**。回填这一步就得自己解析并应用 unified diff ——
不能指望 `patch(1)`（Windows 上没有）或 `git apply`（要求仓库且语义更严）。

实现范围（写在明面上，不做超纲的事）：

- 只认 `@@ -a,b +c,d @@` 形式的 hunk；上下文行必须**逐字匹配**，否则整体失败
- 支持 `--- a/x` / `+++ b/x` 文件头（忽略其内容，文件名由调用方决定）
- `\\ No newline at end of file` 记下来，用于决定结果是否补尾换行
- 行尾统一按 `\\n` 处理（CRLF 由调用方先归一化，避免"看起来一样却匹配不上"）

失败就**整体不应用**（返回 ok=False + 第一处不匹配的位置）：半个补丁落盘比不落盘更糟。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["apply_unified_diff", "parse_hunks", "hunk_header_re", "MAX_PATCH_BYTES"]

hunk_header_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
MAX_PATCH_BYTES = 2_000_000


def parse_hunks(diff_text: str) -> List[Dict[str, Any]]:
    """把 unified diff 拆成 hunk 列表（纯函数）。

    每个 hunk：{"old_start", "lines": [(marker, text), ...], "no_newline": bool}
    marker 取 ' ' / '-' / '+'。
    """
    hunks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for raw in (diff_text or "").splitlines():
        m = hunk_header_re.match(raw)
        if m:
            if cur is not None:
                hunks.append(cur)
            cur = {"old_start": int(m.group(1)), "lines": [], "no_newline": False}
            continue
        if cur is None:
            continue                       # 文件头 / 前置说明：跳过
        if raw.startswith("\\"):
            cur["no_newline"] = True
            continue
        if not raw:
            # 空行：unified diff 里"上下文空行"应当写成单个空格。这里宽容处理为
            # 上下文空行（很多编辑器会把尾随空格吃掉，硬要求就永远匹配不上）。
            cur["lines"].append((" ", ""))
            continue
        marker, text = raw[0], raw[1:]
        if marker not in " -+":
            cur["lines"].append((" ", raw))
            continue
        cur["lines"].append((marker, text))
    if cur is not None:
        hunks.append(cur)
    return hunks


def apply_unified_diff(original: str, diff_text: str) -> Tuple[str, bool, str]:
    """把 `diff_text` 应用到 `original`。返回 (结果文本, 是否成功, 说明)。

    - 成功：结果为应用后的文本（保持原有换行风格由调用方处理）
    - 失败：返回 (原始文本, False, 原因) —— **不做部分应用**
    """
    if not diff_text or not diff_text.strip():
        return original, False, "补丁是空的"
    # 末尾的空行是**终止符**，不是"上下文空行"：unified diff 里的上下文空行写成单个
    # 空格。不丢掉它，最后那个 hunk 就会多出一条永远匹配不上的上下文行
    # （第一次实现就是这样：写入补丁时多补了一个换行，回填时报"文件已结束"）。
    diff_text = diff_text.rstrip("\n")
    if len(diff_text) > MAX_PATCH_BYTES:
        return original, False, f"补丁过大（{len(diff_text)} 字节）"
    hunks = parse_hunks(diff_text)
    if not hunks:
        return original, False, "没有解析到任何 @@ 块（格式不对？）"
    src = original.replace("\r\n", "\n").replace("\r", "\n")
    lines = src.split("\n")
    # `split("\n")` 会让"以换行结尾"的文件多出一个空元素；应用完再决定要不要去掉
    trailing_newline = src.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]
    out: List[str] = []
    cursor = 0                      # 已消费到原文件的第几行（0 基）
    for hunk in hunks:
        start = max(0, int(hunk["old_start"]) - 1)
        if start < cursor:
            return original, False, f"hunk 起点回退（第 {start + 1} 行），补丁顺序不对"
        if start > len(lines):
            return original, False, f"hunk 起点超出文件（第 {start + 1} 行 > {len(lines)} 行）"
        out.extend(lines[cursor:start])
        cursor = start
        for marker, text in hunk["lines"]:
            if marker == "+":
                out.append(text)
                continue
            if cursor >= len(lines):
                return original, False, f"第 {cursor + 1} 行处文件已结束（补丁还要更多行）"
            if lines[cursor] != text:
                return original, False, (
                    f"第 {cursor + 1} 行不匹配：文件里是 {lines[cursor][:40]!r}，"
                    f"补丁要求 {text[:40]!r}")
            if marker == " ":
                out.append(lines[cursor])
            cursor += 1
    if cursor < len(lines):
        # 补丁只覆盖文件前一段：尾部未提及的内容保留
        out.extend(lines[cursor:])
    result = "\n".join(out)
    if trailing_newline and not hunks[-1].get("no_newline"):
        result += "\n"
    else:
        result = result.rstrip("\n") if hunks[-1].get("no_newline") else result
    return result, True, f"应用了 {len(hunks)} 个 hunk"
