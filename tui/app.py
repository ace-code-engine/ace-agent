#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""tui.app —— ACE 的全屏组件化界面（Textual）

布局（对应交互规格"四区骨架"）：

```
┌ ACE · 模型 · 权限 ────────────────────────────────── Header（常驻，不随内容滚动）
│  ❯ 你的输入                                          ← 转写区（可滚动）
│  ◈ 回答（增量上屏；尾行是"还在长"的那一行）
│  ⚙ file_read ✓   ▅ terminal_exec · 1.2s              ← 工具看板（在跑的一行）
├ 轮 2 · 权限 write · 工具 1 跑/0 排 · 队列 1 ────────── Status（常驻单行）
│ ❯ 输入框（忙的时候照样能打字：回车 = 排队）            ← 输入区（固定）
└ F1 帮助 · Shift+Tab 切权限 · Ctrl+O 展开 · Ctrl+C 中断 ┘ Footer（读当前绑定）
```

## 这一版解决了什么"僵硬"

| 旧手感 | 现在 |
| --- | --- |
| 跑起来之后界面整个卡住，打字没用 | **忙时输入不丢**：回车入队（底栏显示"队列 n"），轮末自动接着跑 |
| 想停只能 Ctrl+C 把进程带走 | **两段式中断**：一下"跑完当前步就停"，再一下"放弃本轮" |
| 授权要手打 `1/2/3` 或 `y/n` | **方向键选择**的模态框，`1/2/3` 仍可用；飞行过来的回车不算数（200ms 宽限） |
| 改权限要打 `/permission write` | `Shift+Tab` 沿着 readonly→write→full 转，转进 `full` 要二次确认 |
| 补全菜单只在装了 prompt_toolkit 时才有 | 菜单是**模型**（`ui/ace_menu`），界面上是输入框上方的浮层，↑/↓/Tab/回车都在 |
| 键位靠记 | `?`/`F1` 打开帮助面板，内容由 `ui/ace_keys.APP_KEYMAP` **生成**（帮助里写着的键一定真的绑了） |
| 输出一行一行蹦 | 桥接支持**活尾行**：模型边吐字边显示，换行才落成一条 |

## 三条纪律（都在代码里）

1. **输入区与状态区固定**，只有转写区滚动；
2. **对话框出现时冻结输入区**，关闭后焦点无条件还回输入框（草稿保留）；
3. **输出经队列进界面**：引擎在别的线程里 print，界面在主线程挂组件。

依赖：`textual`（可选）。没装时 `run_tui()` 返回 2，调用方回退 REPL —— 核心零依赖不变。
"""

from __future__ import annotations

import queue
import sys
import threading
from typing import Any, Callable, List, Optional

from tui.bridge import EngineBridge
from ui import ace_keys, ace_menu, ace_turn

__all__ = ["AceTuiApp", "run_tui", "EngineBridge"]

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static


def _bindings(tr: Callable[[str], str]) -> List[Binding]:
    """Textual 的 BINDINGS 由 `ui/ace_keys.APP_KEYMAP` 生成 —— 帮助面板与真绑定同源。"""
    out: List[Binding] = []
    skip = {"chord_prefix", "submit", "newline", "dialog_1",
            "dialog_2", "dialog_3", "history_prev", "history_next"}
    for b in ace_keys.APP_KEYMAP:
        if b.action in skip:
            continue          # 这些由输入框/对话框自己处理，不抢全局键
        # `Tab` 必须 priority：Screen 自己有一个"焦点轮转"的 tab 绑定，
        # 它比 app 级绑定先命中 —— 不抢在它前面，"补全"这个键就永远不会生效。
        out.append(Binding(b.key, b.action, tr(b.desc_key),
                           show=(b.scope == "global"),
                           priority=(b.action == "complete")))
    return out


class HelpScreen(ModalScreen):
    """键盘帮助：**浮层**，不是往会话区里打三十行。

    内容由 `ui/ace_keys.APP_KEYMAP` 生成（帮助里写着的键一定真的绑上了）。
    """

    CSS = """
    HelpScreen { align: center middle; }
    #help_box { width: 78; height: auto; max-height: 80%; border: round $accent;
                padding: 1 2; background: $surface; }
    """

    BINDINGS = [
        Binding("escape", "close", "关闭"),
        Binding("f1", "close", "", show=False),
        Binding("q", "close", "", show=False),
        Binding("enter", "close", "", show=False),
    ]

    def __init__(self, rows, t) -> None:
        super().__init__()
        self.rows = list(rows)
        self.t = t

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help_box"):
            yield Static(self.t("tui_help_title"))
            scope_names = {"global": "全局", "prompt": "输入框", "dialog": "对话框",
                           "transcript": "会话区", "overlay": "浮层"}
            last = None
            for scope, key, desc in self.rows:
                if scope != last:
                    yield Static(f"  [{scope_names.get(scope, scope)}]", classes="dim")
                    last = scope
                yield Static(f"    {key:<18}{desc}")
            yield Static(self.t("tui_help_footer"), classes="dim")

    def action_close(self) -> None:
        self.dismiss()


class PermissionScreen(ModalScreen):
    """授权对话框：方向键选、回车确认、`1/2/3` 直接选、`Esc` = **拒绝**。

    冻结输入区（模态），关闭后调用方无条件把焦点还给输入框。
    """

    CSS = """
    PermissionScreen { align: center middle; }
    #perm_box { width: 72; height: auto; border: round $warning; padding: 1 2;
                background: $surface; }
    .perm_opt { padding: 0 1; }
    .perm_opt.sel { background: $accent; color: $text; }
    .perm_danger { color: $warning; }
    """

    BINDINGS = [
        Binding("up", "move(-1)", "上移", show=False),
        Binding("down", "move(1)", "下移", show=False),
        Binding("k", "move(-1)", "", show=False),
        Binding("j", "move(1)", "", show=False),
        Binding("enter", "choose", "确认"),
        Binding("escape", "deny", "拒绝"),
        Binding("1", "pick(0)", "", show=False),
        Binding("2", "pick(1)", "", show=False),
        Binding("3", "pick(2)", "", show=False),
    ]

    def __init__(self, tool: str, reason: str, options, t,
                 on_done: Callable[[str], None]) -> None:
        super().__init__()
        self.tool = tool
        self.reason = reason
        self.options = list(options)
        self.t = t
        self.on_done = on_done
        self.sel = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="perm_box"):
            yield Static(self.t("perm_request_title", tool=self.tool), id="perm_title")
            if self.reason:
                yield Static(self.t("perm_reason", reason=self.reason), classes="dim")
            for i, (_v, desc_key, danger) in enumerate(self.options):
                cls = "perm_opt" + (" perm_danger" if danger else "")
                yield Static(f"  {i + 1}) {self.t(desc_key)}", classes=cls, id=f"opt{i}")
            yield Static(self.t("perm_hint_keys"), classes="dim")

    def on_mount(self) -> None:
        self._paint()

    def _paint(self) -> None:
        for i in range(len(self.options)):
            try:
                w = self.query_one(f"#opt{i}", Static)
            except Exception:      # noqa: BLE001 —— 还没挂上
                continue
            w.set_class(i == self.sel, "sel")
            w.update(f"{'▶' if i == self.sel else ' '} {i + 1}) "
                     f"{self.t(self.options[i][1])}")

    def action_move(self, delta: int) -> None:
        self.sel = (self.sel + int(delta)) % max(1, len(self.options))
        self._paint()

    def action_pick(self, idx: int) -> None:
        self.sel = max(0, min(int(idx), len(self.options) - 1))
        self._paint()
        self.action_choose()

    def action_choose(self) -> None:
        value = str(self.options[self.sel][0])
        self.dismiss()
        self.on_done(value)

    def action_deny(self) -> None:
        """Esc = 拒绝（危险对话框里"关掉"绝不能等于"放行"）。"""
        self.dismiss()
        self.on_done("deny")


class AceTuiApp(App):
    """ACE 的全屏界面。

    宿主协议（`ui_host` 可选）：本界面挂在 CLI 上，CLI 通过 `attach_ui()` 反向调用
    这里的 `ask_permission()` —— 引擎线程阻塞等答案，界面在主线程问用户。
    """

    CSS = """
    #status { dock: bottom; height: 1; background: $panel; color: $text-muted; }
    #board  { dock: bottom; height: auto; max-height: 6; color: $text-muted; }
    #prompt { dock: bottom; height: 1; }
    #palette { dock: bottom; height: auto; max-height: 10; display: none;
               background: $surface; border-top: solid $accent; }
    #palette.open { display: block; }
    #live { color: $text; }
    Footer { dock: bottom; }
    #body { padding: 0 1; }
    .user { color: $accent; }
    .assistant { color: $text; }
    .tool { color: $text-muted; }
    .notice { color: $warning; }
    .dim { color: $text-muted; }
    .turn_bar { color: $text-muted; height: 1; }
    """
    BINDINGS = [Binding("up", "nav(-1)", "", show=False),
                Binding("down", "nav(1)", "", show=False)]
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, engine=None, status_provider=None, title: str = "ACE",
                 translate: Optional[Callable[[str], str]] = None,
                 command_table: Optional[dict] = None,
                 on_stop: Optional[Callable[[], None]] = None,
                 board_provider: Optional[Callable[[], Any]] = None,
                 ui_host: Any = None) -> None:
        super().__init__()
        self.engine = engine
        self.status_provider = status_provider
        self.app_title = title
        self.t = translate or (lambda k, **kw: k)
        self.commands = dict(command_table or {})
        self.on_stop = on_stop
        self.board_provider = board_provider
        self.ui_host = ui_host
        self.body_lines = 0
        self.turn = ace_turn.TurnController()
        self.chords = ace_keys.ChordMap()
        self._menu: Optional[ace_menu.MenuState] = None
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._bridge = EngineBridge(self._enqueue, partial=self._enqueue_partial)
        self._worker: Optional[threading.Thread] = None
        self._live_text = ""
        self._perm_lock = threading.Lock()
        self._perm_slot: List[str] = []
        self._perm_event = threading.Event()
        self._history: List[str] = []
        self._hist_idx = 0
        self._quit_armed = False
        self._mode_armed = False
        # Textual 的键位是**类级**合并出来的（`DOMNode.__init__` 从 `cls._merged_bindings`
        # 复制一份），所以实例上再赋 `self.BINDINGS` 是没用的 —— 必须往这张表里加。
        for _b in _bindings(self.t):
            try:
                self._bindings._add_binding(_b)
            except Exception:      # noqa: BLE001 —— 加不上就只剩类级那几个，界面不崩
                pass

    # ================= 布局 =================
    def _msg(self, key: str, **kw) -> str:
        """翻译 + 填值。`translate` 只吃一个键的调用方（测试里常用）也照样能用。"""
        try:
            return self.t(key, **kw) if kw else self.t(key)
        except TypeError:
            base = self.t(key)
            for k, v in kw.items():
                base = base.replace("{" + str(k) + "}", str(v))
            return base

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="body"):
            yield Static("", id="seed")
        yield Static("", id="live")
        yield Static("", id="board")
        yield Static("", id="status")
        with Vertical(id="palette"):
            yield Static("", id="palette_inner")
        yield Input(placeholder=self.t("tui_input_placeholder"), id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.app_title
        self.sub_title = self.t("tui_subtitle")
        self.query_one("#prompt", Input).focus()
        self._refresh_status()
        self.set_interval(0.2, self._drain_queue)
        self.set_interval(0.5, self._refresh_status)
        self.set_interval(0.5, self._tick_board)
        if self.ui_host is not None and hasattr(self.ui_host, "attach_ui"):
            try:
                self.ui_host.attach_ui(self)     # 引擎侧以后从这条路问界面
            except Exception:                    # noqa: BLE001
                pass

    # ================= 状态行 / 看板 =================
    def _status_text(self) -> str:
        parts: List[str] = []
        if callable(self.status_provider):
            try:
                for p in (self.status_provider() or []):
                    parts.append(p[1] if isinstance(p, (tuple, list)) else str(p))
            except Exception as e:               # noqa: BLE001
                parts.append(f"状态不可用: {type(e).__name__}")
        snap = self.turn.snapshot()
        if snap["queued"]:
            parts.append(self._msg("tui_status_queue", n=str(snap["queued"])))
        if snap["busy"]:
            parts.append(self._msg("tui_status_busy", s=f"{float(snap['elapsed']):.0f}"))
        parts.append(" " + self.turn.hint(self.t) + " ")
        if self.chords.armed:
            parts.append(self._msg("tui_status_chord", k=self.chords.armed))
        return "".join(parts).strip()

    def _refresh_status(self) -> None:
        try:
            self.query_one("#status", Static).update(self._status_text())
        except Exception:      # noqa: BLE001 —— 还没挂上
            pass
        if self.chords.expired(self._now()):
            self._refresh_status()

    def _tick_board(self) -> None:
        """工具看板：每 160ms 重画一次（同帧同步的字形由看板自己算）。"""
        text = ""
        board = None
        if callable(self.board_provider):
            try:
                board = self.board_provider()
            except Exception:      # noqa: BLE001
                board = None
        if board is None:
            board = getattr(self.ui_host, "_board", None)
        if board is not None and board.count():
            text = "\n".join(board.render(width=self.size.width - 2))
        try:
            self.query_one("#board", Static).update(text)
        except Exception:      # noqa: BLE001
            pass

    # ================= 输出（引擎 → 界面）=================
    def _enqueue(self, lines: List[str]) -> None:
        for line in lines:
            self._queue.put(("line", line))

    def _enqueue_partial(self, text: str) -> None:
        self._queue.put(("partial", text))

    def _drain_queue(self) -> None:
        pending: List[str] = []
        partial: Optional[str] = None
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "partial":
                    partial = payload
                else:
                    pending.append(payload)
        except queue.Empty:
            pass
        if pending:
            self.append_lines(pending)
            partial = ""
        if partial is not None:
            self.set_live(partial)

    def append_lines(self, lines: List[str], kind: str = "assistant") -> None:
        body = self.query_one("#body", VerticalScroll)
        for line in lines:
            _cls = ("user" if line.startswith("❯") else
                    "tool" if line.startswith("⚙") else
                    "notice" if line.startswith(("·", "✗", "‼")) else kind)
            body.mount(Static(line or " ", classes=_cls))
            self.body_lines += 1
        body.scroll_end(animate=False)

    def set_live(self, text: str) -> None:
        """活尾行：模型正在写、还没换行的那一行。"""
        self._live_text = text
        try:
            self.query_one("#live", Static).update(text)
        except Exception:      # noqa: BLE001
            pass

    def notice(self, text: str) -> None:
        self.append_lines([text], "notice")

    # ================= 输入 =================
    def on_input_changed(self, event: Input.Changed) -> None:
        """输入变化 → 刷新补全浮层（命令/参数/@ 提及同一套模型）。"""
        self._refresh_palette(event.value or "")

    def _refresh_palette(self, text: str) -> None:
        try:
            state = ace_menu.build_menu(text, len(text), self.commands,
                                        translate=self.t)
            panel = self.query_one("#palette", Vertical)
            panel.set_class(state.open, "open")
            if state.open:
                self.query_one("#palette_inner", Static).update(
                    "\n".join(ace_menu.render_menu(state, self.size.width - 2,
                                                   translate=self.t)))
            self._menu = state
        except Exception:      # noqa: BLE001 —— 菜单画不出来不该拦着打字
            self._menu = None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        event.input.value = ""
        self._refresh_palette("")
        if not text:
            return
        # 菜单开着且候选与输入不同 → 先补全（与 REPL 同一套回车语义）
        state = getattr(self, "_menu", None)
        if state is not None and state.open and ace_menu.accepts_on_enter(state, text):
            completed = state.accepted_text(text)
            event.input.value = completed
            self._refresh_palette(completed)
            return
        self._history.append(text)
        self._hist_idx = len(self._history)
        res = self.turn.submit(text)
        if res.action == "rejected":
            self.notice(self.t("tui_queue_full") if res.reason == "queue_full"
                        else self.t("tui_empty_input"))
            return
        self.append_lines([f"❯ {text}"], "user")
        if res.action == "queued":
            self.notice(self._msg("tui_queued", n=str(res.queued)))
            return
        self._run_engine(text)

    def _run_engine(self, text: str, counted: bool = True) -> None:
        """在后台线程里跑引擎：界面永不因为等待而卡死，输出经桥接回界面。

        `counted=False` 用于宿主命令（`/status` 这类）：它们不占用"一轮"的记账，
        跑完也不去动队列 —— 否则按一次 F1 就会把排队的第一条提前拉起来。
        """
        def _work() -> None:
            old = sys.stdout
            sys.stdout = self._bridge          # type: ignore[assignment]
            try:
                if callable(self.engine):
                    self.engine(text)
            except Exception as e:             # noqa: BLE001 —— 单行出错不该打崩界面
                self._enqueue([f"✗ {type(e).__name__}: {e}"])
            finally:
                sys.stdout = old
                self._bridge.flush()
                self.call_from_thread(self._turn_done, counted)

        self._worker = threading.Thread(target=_work, daemon=True)
        self._worker.start()

    def _turn_done(self, counted: bool = True) -> None:
        """一轮结束（主线程）：先看有没有排队的输入，有就立刻接着跑。"""
        if not counted:
            self._refresh_status()
            return
        nxt = self.turn.finish()
        if nxt:
            self.notice(self._msg("tui_dequeued", text=nxt))
            self.append_lines([f"❯ {nxt}"], "user")
            self._run_engine(nxt)
        self._refresh_status()

    # ================= 中断 =================
    def action_interrupt(self) -> None:
        """Ctrl+C：两段式（请求中断 → 强制放弃）；空闲时"再按一次退出"。"""
        res = self.turn.interrupt()
        if res.action == "none":
            if getattr(self, "_quit_armed", False):
                self.exit()
                return
            self._quit_armed = True
            self.notice(self.t("tui_quit_armed"))
            self.set_timer(2.0, lambda: setattr(self, "_quit_armed", False))
            return
        if res.action == "requested":
            self.notice(self.t("tui_interrupting"))
            if callable(self.on_stop):
                try:
                    self.on_stop()
                except Exception:              # noqa: BLE001
                    pass
        else:
            self.notice(self._msg("tui_abandoned", n=str(res.pending)))
        self._refresh_status()

    def action_cycle_permission(self) -> None:
        """Shift+Tab：沿权限环转档。转进 `full` 要二次确认（快捷键不该解除全部审批）。"""
        get = getattr(self.ui_host, "get_permission", None)
        setp = getattr(self.ui_host, "set_permission", None)
        if not callable(get) or not callable(setp):
            self.notice(self.t("tui_no_mode_switch"))
            return
        cur = str(get() or "readonly")
        nxt = ace_turn.next_permission(cur)
        if ace_turn.needs_confirm(nxt) and not getattr(self, "_mode_armed", False):
            self._mode_armed = True
            self.notice(self._msg("tui_mode_confirm", mode=nxt))
            self.set_timer(3.0, lambda: setattr(self, "_mode_armed", False))
            return
        self._mode_armed = False
        setp(nxt)
        self.notice(ace_turn.permission_banner(nxt, translate=self.t))
        self._refresh_status()

    # ================= 对话框（引擎线程阻塞等答案）=================
    def ask_permission(self, tool: str, reason: str, options) -> str:
        """给 CLI 调的：弹出模态框、阻塞引擎线程直到用户作答。

        宽限期在这里生效（`TurnController.answer_permission`）：对话框刚出现的那一瞬
        飞过来的回车不算数 —— 引擎线程等的是"真答案"。
        """
        with self._perm_lock:
            self._perm_event.clear()
            self._perm_slot.clear()
            opts = self.turn.ask_permission(tool, reason, options)
            values = [str(o[0]) for o in opts]

            def _done(value: str) -> None:
                self._perm_slot.append(value)
                self._perm_event.set()

            self.call_from_thread(self.push_screen,
                                  PermissionScreen(tool, reason, opts, self._msg, _done))
            self._perm_event.wait(timeout=600)
            self._refresh_status()
            value = self._perm_slot[0] if self._perm_slot else "deny"
            idx = values.index(value) if value in values else len(values) - 1
            resolved = self.turn.answer_permission(idx, opts)
            if resolved is None:
                # 宽限期内飞过来的答案：不采纳（方向永远收紧）
                self.call_from_thread(self.notice, self.t("grace_inflight"))
                return "deny"
            return resolved

    # ================= 动作 =================
    def action_cancel(self) -> None:
        """Esc：先收菜单，菜单没开就当中断（正在跑）或清提示。"""
        state = getattr(self, "_menu", None)
        if state is not None and state.open:
            self._refresh_palette("")
            return
        if self.turn.busy():
            self.action_interrupt()
            return
        try:
            self.query_one("#prompt", Input).value = ""
        except Exception:      # noqa: BLE001
            pass

    def action_clear_transcript(self) -> None:
        self.query_one("#body", VerticalScroll).remove_children()
        self.body_lines = 0

    def action_expand(self) -> None:
        host = self.ui_host
        if host is not None and hasattr(host, "_cmd_expandall"):
            self.call_later(host._cmd_expandall, [])
            self.notice(self.t("tui_expanded"))

    def action_expand_all(self) -> None:
        self.action_expand()

    def action_tasks(self) -> None:
        self._host_command("/tasks")

    def action_diff(self) -> None:
        self._host_command("/diff")

    def action_help(self) -> None:
        """F1：键盘帮助**浮层**（读完 Esc 关掉，会话区不被三十行键位表刷掉）。"""
        rows = ace_keys.help_rows(translate=self._msg)
        try:
            self.push_screen(HelpScreen(rows, self._msg))
        except Exception:      # noqa: BLE001 —— 浮层起不来时退化成打印，不能不显示
            lines = [self._msg("tui_help_title")]
            for _scope, key, desc in rows:
                lines.append(f"  {key:<16}{desc}")
            lines.append(self._msg("tui_help_footer"))
            self.append_lines(lines, "notice")

    def action_find(self) -> None:
        self._host_command("/search")

    def action_toggle_board(self) -> None:
        try:
            b = self.query_one("#board", Static)
            b.styles.display = "none" if b.styles.display != "none" else "block"
        except Exception:      # noqa: BLE001
            pass

    def action_toggle_thinking(self) -> None:
        self._host_command("/thinking")

    def action_search_history(self) -> None:
        self.action_nav(-1)

    def action_history_prev(self) -> None:
        self.action_nav(-1)

    def action_history_next(self) -> None:
        self.action_nav(1)

    def action_nav(self, delta: int) -> None:
        """↑/↓：菜单开着就选候选，否则翻历史 —— 同一个键，按上下文解释。"""
        state = getattr(self, "_menu", None)
        if state is not None and state.open:
            state.move(int(delta))
            try:
                self.query_one("#palette_inner", Static).update(
                    "\n".join(ace_menu.render_menu(state, self.size.width - 2,
                                                   translate=self.t)))
            except Exception:      # noqa: BLE001
                pass
            return
        if not self._history:
            return
        if int(delta) < 0:
            self._hist_idx = max(0, self._hist_idx - 1)
        else:
            self._hist_idx = min(len(self._history), self._hist_idx + 1)
        val = "" if self._hist_idx >= len(self._history) else self._history[self._hist_idx]
        try:
            self.query_one("#prompt", Input).value = val
            self.query_one("#prompt", Input).cursor_position = len(val)
        except Exception:      # noqa: BLE001
            pass

    def action_complete(self) -> None:
        """Tab：把当前候选补全进输入框（不发送）。"""
        state = getattr(self, "_menu", None)
        if state is None or not state.open:
            return
        try:
            inp = self.query_one("#prompt", Input)
            inp.value = state.accepted_text(inp.value or "")
            self._refresh_palette(inp.value)
        except Exception:      # noqa: BLE001
            pass

    def action_scroll_up(self) -> None:
        self.query_one("#body", VerticalScroll).scroll_page_up(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one("#body", VerticalScroll).scroll_page_down(animate=False)

    def action_quit(self) -> None:
        self.exit()

    def _host_command(self, cmd: str) -> None:
        """把界面动作翻成一条宿主命令（引擎侧的命令表是同一份），不占一轮记账。"""
        if callable(self.engine):
            self._run_engine(cmd, counted=False)

    @staticmethod
    def _now() -> float:
        import time
        return time.monotonic()


def run_tui(engine=None, status_provider=None, title: str = "ACE",
            translate: Optional[Callable[[str], str]] = None,
            command_table: Optional[dict] = None,
            on_stop: Optional[Callable[[], None]] = None,
            board_provider: Optional[Callable[[], Any]] = None,
            ui_host: Any = None) -> int:
    """启动全屏界面；没装 Textual 时返回 2（调用方据此回退 REPL）。"""
    if not _textual_available():
        return 2
    AceTuiApp(engine=engine, status_provider=status_provider, title=title,
              translate=translate, command_table=command_table,
              on_stop=on_stop, board_provider=board_provider,
              ui_host=ui_host).run()
    return 0


def _textual_available() -> bool:
    try:
        import textual  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False
