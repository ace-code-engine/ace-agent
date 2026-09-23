#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""tui —— 组件化全屏界面（Textual 引擎）

为什么另起一层而不是继续加 prompt_toolkit：交互规格里那些"产品级"的东西 —— 鼠标命中
测试、可滚动会话区、焦点管理、模态覆盖层、通知条、页签、CSS 主题、进度条 —— 在
prompt_toolkit 里都要手搓；Textual 把它们做成了一等公民，并且自带**无终端测试台**
（`App.run_test()` + pilot），所以交互也能进 CI 被断言，而不是"你自己跑一下看看"。

引擎与界面在这里**分开**：
- 引擎 = 现有的 Python 安全核（`AgentCLI` / 执行层 / 工具），它只管把"发生了什么"写成
  一行行文本（`ui.ace_fullscreen.TranscriptSink` 已经在做这件事）；
- 界面 = 本包。它把那些行挂成组件、管布局与焦点、把按键翻成意图。
  两者的接口就是"一行文本 + 一次按键"，所以以后换成像 Ink/Rust 那样的外壳也不需要动引擎。
"""

from __future__ import annotations

__all__ = ["AceTuiApp", "tui_available"]

try:                                            # Textual 是可选依赖（核心仍零依赖）
    import textual as _textual                  # noqa: F401
    _TEXTUAL_VERSION = getattr(_textual, "__version__", "?")
except Exception:                               # noqa: BLE001
    _TEXTUAL_VERSION = ""


def tui_available() -> bool:
    """Textual 在不在（不在时调用方回退到 REPL，而不是崩）。"""
    return bool(_TEXTUAL_VERSION)


def __getattr__(name: str):                     # 延迟导入：没装 textual 也能 import 本包
    if name == "AceTuiApp":
        from tui.app import AceTuiApp
        return AceTuiApp
    raise AttributeError(name)
