#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.file_tools —— 兼容层（R-02，v3.9）

`FileTools` 这条继承链与对外名字**保持不变**：`tools/__init__.py` 仍在组合它，
`registry.py` 里的 handler 名（`"_exec_file_ops"` 之类）是字符串，方法必须还在链上。
真正的实现按三条执行路径拆在 `file_ops.py` / `terminal_view.py` / `terminal_exec.py`。
"""

from tools.file_ops import FileOps
from tools.terminal_exec import TerminalExec
from tools.terminal_view import TerminalView


class FileTools(FileOps, TerminalView, TerminalExec):
    """历史名：组合三条执行路径（拆分前是一个 1237 行的类）"""
    pass
