#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""破坏性目标集合：每种工具"这次会动哪些路径"的**唯一入口**（H-13）。

**为什么需要它**：这件事此前散在两处，而且**都漏了同一项** ——

| 位置 | 干什么 | 漏了什么 |
|---|---|---|
| `execution_layer._outside_destructive_reason` | 项目外覆盖/删除要问人 | `file_move` 的 `source` |
| `core/ace_rules.rule_matches` | 用户的 deny 规则 | 同上 |
| `execution_layer._gated_identity` | 授权绑到"被批准的那个对象" | 同上 |

三处都只读 `path` / `dest` / `target`，于是 **`file_move(source=…, dest=…)` 的
`source` 对三者都不可见**。而"把项目外一个已存在的文件移走"等于**删除**它：
既不问人、也不进规则、项目外也没有快照可回滚 —— 一次调用永久丢一个文件。
实测 `SECURITY-MODEL.md` 承诺过"覆盖或删除项目外已经在那儿的文件会逐次确认"，
`file_delete` 做到了、`file_move` 没有。

同一个判据写在三处、三处一起漏 —— 这正是本卡 §0 说的那个病。所以这里给一个
**唯一入口**，三处都改成问它。
"""
from __future__ import annotations

from typing import Any, List, Mapping

__all__ = ["WRITE_TOOLS_WITH_PATH", "destructive_targets"]

# "会按路径动文件"的四个工具（决定"项目外覆盖要问人"那条闸门管不管）。
WRITE_TOOLS_WITH_PATH = ("file_write", "file_delete", "str_replace", "file_move")


def destructive_targets(tool: str, params: Mapping[str, Any]) -> List[str]:
    """这个工具这次调用会动到的路径（去重、保持顺序，**破坏性的在前**）。

    对 `file_move` 顺序是 `source` → `dest`：前者是"移走 = 删除"，后者只在覆盖
    已存在文件时才是破坏性的。调用方（问人 / 规则匹配）按顺序看，第一个命中的
    就是该报给用户的那一个。
    """
    if not isinstance(params, Mapping):
        return []
    out: List[str] = []

    def _add(val: Any) -> None:
        try:
            s = str(val or "").strip()
        except (TypeError, ValueError):
            return
        if s and s not in out:
            out.append(s)

    if tool == "file_move":
        # 源在前：把项目外的文件移走就是把它删了，这是更该被拦住的那一边。
        _add(params.get("source") or params.get("src") or params.get("from"))
        _add(params.get("dest") or params.get("path") or params.get("target"))
        return out
    if tool in ("file_write", "file_delete", "str_replace"):
        _add(params.get("path") or params.get("dest") or params.get("target"))
        return out
    # 其余工具：只给规则匹配用（它们不参与"项目外覆盖要问人"那条闸门）。
    for _k in ("path", "dest", "target", "source"):
        _add(params.get(_k))
    return out
