#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径规范化：把"拼写"归一成"OS 实际认出的那个东西"（H-10）。

**为什么需要它**：敏感名单的判定此前是在**原始字符串**上做的，而同一个文件在
Windows 上有多种拼写 —— 8.3 短名、尾点/尾空格、大小写、`..`、junction/symlink。
本机实测（读操作，未改动任何东西）：

    sensitive_target("C:/Users/<me>/.ssh/config")    -> '敏感目录: .ssh'   ← 挡住
    sensitive_target("C:/Users/<me>/SSH~1/config")   -> None               ← 放行！
    而 C:\\Users\\<me>\\SSH~1 在本机是**存在的真实 8.3 短名**（OS 解析到 .ssh）

也就是说"换一句别名就能把敏感目录读出来"。同类：`.ssh.`（尾点）、`AWS~1`、
`.ai_code.json.` —— 都能绕过。

**做法**：把解析集中到这一处，**所有名单判定都在解析之后做**。不是给每个消费者
各补一遍 —— 那正是 H-06/H-11 同一个病的来源（同一个判据在多处各写一份）。

`Path.resolve()` 在 Windows 上会走 `GetFinalPathNameByHandle`，实测能一并解决
8.3 短名、尾点/尾空格、大小写与 `..`。它**不**跟随不存在的路径（`strict=False`
只做词法归一 + 解析已存在的前缀），这与我们的用途一致：对不存在的目标做判定时，
能归一到什么程度就归一到什么程度。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

__all__ = ["canonical_path", "canonical_text", "same_file"]


def canonical_path(path: "Path | str", *, base: "Optional[Path | str]" = None
                   ) -> Optional[Path]:
    """解析成 OS 最终路径；失败返回 None（调用方退回按原串判定）。

    `base` 是**相对路径的起点**，默认 `Path.cwd()`。需要传它的场合：解析"模型写在
    工具参数里的路径"时，相对路径的起点是**项目根**而不是进程 cwd —— 两者在
    `--project-root` 与 cwd 不同的场景下（无头、测试、`/open` 之外的调用）并不相等，
    用 cwd 当起点会把项目内的文件解析到项目外，精确回滚于是变成静默空操作。
    """
    try:
        p = Path(os.path.expanduser(str(path)))
        if not p.is_absolute():
            p = (Path(base) if base is not None else Path.cwd()) / p
        return p.resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def canonical_text(path: "Path | str") -> str:
    """解析后的字符串形态（已 `normcase`）。失败返回空串。

    `normcase` 在 Windows 上折大小写并把 `/` 折成 `\\` —— 判定用，不用于显示。
    """
    p = canonical_path(path)
    if p is None:
        return ""
    return os.path.normcase(str(p))


def same_file(a: "Path | str", b: "Path | str") -> bool:
    """两个拼写指的是不是同一个文件/目录。"""
    ca, cb = canonical_text(a), canonical_text(b)
    return bool(ca) and ca == cb
