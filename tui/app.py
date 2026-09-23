#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""tui.app —— ACE 的全屏组件化界面（Textual）

布局（对应交互规格第 1 节"四区骨架"）：

```
┌ ACE · 模型 · 权限 ───────────────────────────── Header（常驻，不随内容滚动）
│  ❯ 你的输入                                     ← 转写区（可滚动，鼠标滚轮/拖动）
│  ◈ 回答（Markdown 增量）
│  ⚙ file_read ✓
├ 轮 2 · 工具 3 · 上下文 18% ──────────────────── Status（常驻单行）
│ ❯ 输入框                                        ← 输入区（固定，草稿不因滚动丢失）
└ Ctrl+O 展开 · Ctrl+T 任务树 · Ctrl+Q 退出 ───── Footer（按键提示读的是当前绑定）
```

三条纪律（都体现在代码里）：
1. **输入区与状态区固定**，只有转写区滚动 —— 目光只在固定位置之间移动；
2. **对话框/覆盖层出现时冻结输入区**，关闭后焦点无条件还回输入框（草稿保留）；
3. **输出经队列进界面**：引擎在别的线程里 print，界面在主线程挂组件 —— 不让两个线程
   同时写屏幕（Textual 里直接 print 会把界面打花）。
"""

from __future__ import annotations

import queue
import sys
import threading
from typing import List, Optional

from tui.bridge import EngineBridge

__all__ = ["AceTuiApp", "run_tui", "EngineBridge"]

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Static


class AceTuiApp(App):
    """ACE 的全屏界面。`engine` 是一个可调用对象：`engine(line) -> None`（处理一行输入）。"""

    CSS = """
    #status { dock: bottom; height: 1; background: $panel; color: $text-muted; }
    #prompt { dock: bottom; height: 1; }
    Footer { dock: bottom; }
    #body { padding: 0 1; }
    .user { color: $accent; }
    .assistant { color: $text; }
    .tool { color: $text-muted; }
    .notice { color: $warning; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+l", "clear_body", "清屏"),
        Binding("pageup", "scroll_up", "上翻"),
        Binding("pagedown", "scroll_down", "下翻"),
    ]

    def __init__(self, engine=None, status_provider=None, title: str = "ACE") -> None:
        super().__init__()
        self.engine = engine
        self.status_provider = status_provider
        self.app_title = title
        self.body_lines = 0
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._bridge = EngineBridge(self._enqueue)
        self._worker: Optional[threading.Thread] = None

    # ---------- 布局 ----------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="body"):
            yield Static("", id="seed")
        yield Static("", id="status")
        yield Input(placeholder="输入消息，/ 看命令，@ 引用文件", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.app_title
        self.sub_title = "全屏界面（Textual）"
        self.query_one("#prompt", Input).focus()
        self._refresh_status()
        self.set_interval(0.5, self._drain_queue)
        self.set_interval(1.0, self._refresh_status)

    def _refresh_status(self) -> None:
        text = ""
        if callable(self.status_provider):
            try:
                parts = self.status_provider() or []
                text = "".join(p[1] if isinstance(p, (tuple, list)) else str(p)
                               for p in parts)
            except Exception as e:  # noqa: BLE001 —— 状态行读不出来不该崩界面
                text = f"状态不可用: {type(e).__name__}"
        self.query_one("#status", Static).update(text.strip())

    # ---------- 输出（引擎 → 界面）----------
    def _enqueue(self, lines: List[str]) -> None:
        for line in lines:
            self._queue.put(line)

    def _drain_queue(self) -> None:
        pending: List[str] = []
        try:
            while True:
                pending.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        if pending:
            self.append_lines(pending)

    def append_lines(self, lines: List[str], kind: str = "assistant") -> None:
        """把若干行挂成组件（转写区自动跟到底部）。"""
        body = self.query_one("#body", VerticalScroll)
        for line in lines:
            _cls = ("user" if line.startswith("❯") else
                    "tool" if line.startswith("⚙") else
                    "notice" if line.startswith(("·", "✗", "‼")) else kind)
            body.mount(Static(line or " ", classes=_cls))
            self.body_lines += 1
        body.scroll_end(animate=False)

    # ---------- 输入 ----------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        event.input.value = ""
        if not text:
            return
        self.append_lines([f"❯ {text}"], "user")
        if not callable(self.engine):
            self.append_lines(["（没有接引擎：这是界面自检模式）"], "notice")
            return
        self._run_engine(text)

    def _run_engine(self, text: str) -> None:
        """在后台线程里跑引擎，输出经桥接回界面 —— 界面永不因为等待而卡死。"""
        def _work() -> None:
            old = sys.stdout
            sys.stdout = self._bridge          # type: ignore[assignment]
            try:
                self.engine(text)
            except Exception as e:             # noqa: BLE001 —— 单行出错不该打崩界面
                self._enqueue([f"✗ {type(e).__name__}: {e}"])
            finally:
                sys.stdout = old
                self._bridge.flush()
        self._worker = threading.Thread(target=_work, daemon=True)
        self._worker.start()

    # ---------- 动作 ----------
    def action_clear_body(self) -> None:
        self.query_one("#body", VerticalScroll).remove_children()
        self.body_lines = 0

    def action_scroll_up(self) -> None:
        self.query_one("#body", VerticalScroll).scroll_page_up(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one("#body", VerticalScroll).scroll_page_down(animate=False)


def run_tui(engine=None, status_provider=None, title: str = "ACE") -> int:
    """启动全屏界面；没装 Textual 时返回 2（调用方据此回退 REPL）。"""
    if not _textual_available():
        return 2
    AceTuiApp(engine=engine, status_provider=status_provider, title=title).run()
    return 0


def _textual_available() -> bool:
    try:
        import textual  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False
