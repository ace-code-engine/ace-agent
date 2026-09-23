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
from typing import Any, Callable, List, Optional, Sequence

from tui.bridge import EngineBridge
from ui import ace_keys, ace_menu, ace_turn

__all__ = ["AceTuiApp", "run_tui", "EngineBridge"]

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static


def _bindings(tr: Callable[[str], str]) -> List[Binding]:
    """Textual 的 BINDINGS 由 `ui/ace_keys.APP_KEYMAP` 生成 —— 帮助面板与真绑定同源。

    和弦的**第二段不在这里**：Textual 会把"聚焦控件会消费的键"从上层键位里剔掉
    （普通字母正是被输入框消费的那类），所以 `e`/`t`/`d` 必须绑在输入框自己身上
    （见 `ChordInput`），否则永远不触发。
    """
    out: List[Binding] = []
    skip = {"submit", "dialog_1", "dialog_2", "dialog_3",
            "history_prev", "history_next"}
    for b in ace_keys.APP_KEYMAP:
        if b.action in skip or b.chord:
            continue
        # 优先级键位（抢在聚焦控件**之前**拿到这个键）：
        # - `Tab`：Screen 有一个"焦点轮转"的 tab 绑定，不抢就永远轮不到补全；
        # - `Shift+Tab`：Screen 会拿它去**反向轮转焦点**（实测：按下去焦点跑到会话区、
        #   权限档一动不动 —— 用户只会说"这个键没用"）；
        # - `Ctrl+X`：输入框把它绑成了"剪切"；
        # - `Ctrl+C`：输入框把它绑成了"复制"。聊天里 `Ctrl+C` 必须是中断/取消
        #   （这是所有人的肌肉记忆；复制仍可用鼠标选中 + Ctrl+Shift+C）。
        _prio = b.action in ("complete", "cycle_permission", "chord_prefix",
                             "interrupt")
        out.append(Binding(b.key, b.action, tr(b.desc_key),
                           show=(b.scope == "global"), priority=_prio))
    return out


class ChordInput(Input):
    """输入框 —— 同时负责接住和弦的第二段。

    为什么必须在这个类里做（这是踩出来的，不是设计偏好）：

    1. App 级的单个字母键位会被 Textual **从上层键位表里剔掉** —— 聚焦控件
       （Input）声明"可打印字符归我"，所以 `Ctrl+X` 之后那个 `e` 永远轮不到 App；
    2. 就算绑到 Input 自己身上也没用：`Input._on_key` 对可打印字符是**直接插入并
       stop()**，压根不查绑定。

    所以只能在 `_on_key` 里先问一句"现在是不是在和弦里"。挂起时才拦，平时就是普通
    字母 —— 这也是"按了没反应"和"打字被吃"两种事故的分界线。
    """

    CHORDS = {"e": "expand_all", "t": "tasks", "d": "diff"}

    def chord_action(self, key: str) -> Optional[str]:
        """这个键此刻该触发什么动作（没挂起 / 没登记 → None）。"""
        chords = getattr(self.app, "chords", None)
        if chords is None or not chords.armed:
            return None
        return self.CHORDS.get(str(key or ""))

    async def _on_key(self, event) -> None:
        action = self.chord_action(getattr(event, "character", "") or "")
        if action:
            event.stop()
            event.prevent_default()
            chords = getattr(self.app, "chords", None)
            if chords is not None:
                chords.reset()
            handler = getattr(self.app, f"action_{action}", None)
            if callable(handler):
                handler()
            try:
                self.app._refresh_status()
            except Exception:      # noqa: BLE001
                pass
            return
        await super()._on_key(event)


class ChoiceScreen(ModalScreen):
    """通用选择框：`/model`、`/provider`、`/sessions`、`/permission` 这些命令在
    组件界面里必须走这里 —— 在界面里 stdin 归界面所有，prompt_toolkit 的选择器
    会和界面抢同一份按键（表现就是"这个命令一按就花屏/卡住"）。

    输入即过滤（复用 `ui/ace_selector` 的模糊匹配），↑/↓ 选择，回车确认，Esc 取消。
    """

    CSS = """
    ChoiceScreen { align: center middle; }
    #choice_box { width: 76; height: auto; max-height: 80%; border: round $accent;
                  padding: 1 2; background: $surface; }
    .choice_opt { padding: 0 1; }
    .choice_opt.sel { background: $accent; color: $text; }
    """

    BINDINGS = [
        Binding("up", "move(-1)", "", show=False),
        Binding("down", "move(1)", "", show=False),
        Binding("enter", "choose", "确认"),
        Binding("escape", "cancel", "取消"),
    ]

    def __init__(self, title: str, items, t, on_done, filterable: bool = True) -> None:
        super().__init__()
        self.title_text = title
        self.items = list(items)
        self.shown = list(self.items)
        self.t = t
        self.on_done = on_done
        self.filterable = bool(filterable)
        self.sel = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="choice_box"):
            yield Static(self.title_text, id="choice_title")
            if self.filterable:
                yield Input(placeholder=self.t("choose_filter"), id="choice_filter")
            yield Static("", id="choice_list")
            yield Static(self.t("choose_hint_keys"), classes="dim")

    def on_mount(self) -> None:
        self._repaint()
        if self.filterable:
            self.query_one("#choice_filter", Input).focus()

    def _repaint(self) -> None:
        rows = []
        for i, item in enumerate(self.shown[:12]):
            mark = "▶" if i == self.sel else " "
            rows.append(f"{mark} {item}")
        if len(self.shown) > 12:
            rows.append(self.t("choose_more").replace("{n}", str(len(self.shown) - 12)))
        try:
            self.query_one("#choice_list", Static).update("\n".join(rows))
        except Exception:      # noqa: BLE001
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        q = (event.value or "").strip()
        if not q:
            self.shown = list(self.items)
        else:
            try:
                from ui.ace_selector import filter_items
                order = [i for i, _s in filter_items(self.items, q)]
                self.shown = [self.items[i] for i in order]
            except Exception:      # noqa: BLE001 —— 过滤失败就不过滤，别把选择框弄空
                self.shown = [x for x in self.items if q.lower() in x.lower()]
        self.sel = 0
        self._repaint()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_choose()

    def action_move(self, delta: int) -> None:
        if self.shown:
            self.sel = (self.sel + int(delta)) % len(self.shown)
            self._repaint()

    def action_choose(self) -> None:
        value = self.shown[self.sel] if self.shown else None
        self.dismiss()
        self.on_done(value)

    def action_cancel(self) -> None:
        self.dismiss()
        self.on_done(None)


class TextScreen(ModalScreen):
    """通用文本输入框：向导步骤、拒绝理由、`/rollback` 的确认这些都走它。

    为什么要它：这些地方原来都是 `input()`，而组件界面里 `input()` 会和界面
    抢 stdin —— 表现就是"这个命令一按就卡住"。
    """

    CSS = """
    TextScreen { align: center middle; }
    #text_box { width: 76; height: auto; border: round $accent; padding: 1 2;
                background: $surface; }
    """

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, title: str, t, on_done, default: str = "") -> None:
        super().__init__()
        self.title_text = title
        self.t = t
        self.on_done = on_done
        self.default = str(default or "")

    def compose(self) -> ComposeResult:
        with Vertical(id="text_box"):
            yield Static(self.title_text)
            yield Input(value=self.default, placeholder=self.t("text_enter_hint"),
                        id="text_field")
            yield Static(self.t("text_hint_keys"), classes="dim")

    def on_mount(self) -> None:
        self.query_one("#text_field", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value or ""
        self.dismiss()
        self.on_done(value)

    def action_cancel(self) -> None:
        self.dismiss()
        self.on_done(None)


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
        self._chord_deadline = 0.0
        self._find_query = ""
        self._find_ready = False
        self._find_idx = -1
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
        yield ChordInput(placeholder=self._msg("tui_input_placeholder"), id="prompt")
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
    # ================= 宿主协议：CLI 通过这几个方法问界面 =================
    def _modal(self, factory, title: str, default: Any = None) -> Any:
        """弹一个模态框并阻塞**调用线程**（引擎线程）直到有人作答。

        超时设得长：等人是正常的，超时只是兜底（界面已经关掉时别把引擎永久挂住）。
        """
        with self._perm_lock:
            self._perm_event.clear()
            self._perm_slot.clear()

            def _done(value: Any) -> None:
                self._perm_slot.append(value)
                self._perm_event.set()

            self.call_from_thread(self.push_screen, factory(_done))
            self._perm_event.wait(timeout=900)
            return self._perm_slot[0] if self._perm_slot else default

    def choose(self, title: str, options: Sequence[str]) -> Optional[str]:
        """列表选择（`/model`、`/provider`、`/sessions`、`/permission` 档位…）。"""
        items = [str(o) for o in options]
        if not items:
            return None
        return self._modal(lambda done: ChoiceScreen(title, items, self._msg, done),
                           title, None)

    def ask_text(self, prompt: str, default: str = "") -> Optional[str]:
        """文本输入（向导步骤、拒绝理由、确认语句…）。"""
        return self._modal(lambda done: TextScreen(prompt, self._msg, done, default),
                           prompt, None)

    def confirm(self, question: str) -> bool:
        """二选一确认：**默认否**（关掉/超时都不等于同意）。"""
        yes = self._msg("confirm_yes")
        no = self._msg("confirm_no")
        picked = self._modal(
            lambda done: ChoiceScreen(question, [yes, no], self._msg, done,
                                      filterable=False),
            question, no)
        return picked == yes

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

    # ================= 和弦与输入细节 =================
    def action_chord_prefix(self) -> None:
        """`Ctrl+X`：挂起和弦（底栏显示"Ctrl+X …"），等第二个键。

        第二个键由**优先级键位**接住（见 `_bindings`），所以焦点留在输入框也没关系：
        没挂起时那个字母压根不是绑定，照常打字。
        """
        self.chords.feed("ctrl+x", self._now())
        self._chord_deadline = self._now() + ace_keys.CHORD_TIMEOUT
        self._refresh_status()

    def check_action(self, action: str, parameters: str):
        """和弦的第二段只在挂起时可用。

        这一条是**必须**的：`e`/`t`/`d` 是普通字母，全局绑死它们会在焦点不在输入框时
        （比如刚点过会话区）把用户的按键吃掉 —— 表现就是"打字没反应"。
        """
        if action in ("expand_all", "tasks", "diff") and not self.chords.armed:
            return False
        return True

    def on_key(self, event) -> None:
        """和弦兜底：挂起时按了**没登记**的键（比如功能键），把状态撤掉。

        普通字母不会到这里 —— 它们由 `ChordInput` 自己的优先级键位先接住。
        """
        if not self.chords.armed:
            return
        action, _pending = self.chords.feed(getattr(event, "key", ""), self._now())
        self._refresh_status()
        if action:
            event.stop()
            handler = getattr(self, f"action_{action}", None)
            if callable(handler):
                handler()

    def _refocus_prompt(self) -> None:
        try:
            self.query_one("#prompt", Input).focus()
        except Exception:      # noqa: BLE001
            pass

    def action_newline(self) -> None:
        r"""`Ctrl+J`：在输入框里插入一个换行（多行消息 / 贴一段代码）。

        `Input` 是单行的，但**值里可以有 `\n`**：引擎本来就吃多行消息，粘贴也是这么
        进来的（探针验过），所以这里只需把换行插到光标处，不必换掉输入组件。
        """
        try:
            inp = self.query_one("#prompt", Input)
            pos = inp.cursor_position
            val = inp.value or ""
            inp.value = val[:pos] + "\n" + val[pos:]
            inp.cursor_position = pos + 1
        except Exception:      # noqa: BLE001
            pass

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
        """`Ctrl+O`：展开**上一次被折叠的输出**（卡片上那句"展开看完整"的兑现）。

        别和 `/expandall` 混：那是一个总开关（以后都不折），这个是"把刚才那条摊开看看"。
        绑错命令的话，用户按下去只会以为"怎么什么都没发生"。
        """
        self._host_command("/expand")

    def action_expand_all(self) -> None:
        """`Ctrl+X e`：全部展开的总开关。"""
        self._host_command("/expandall")

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
        """`Ctrl+F`：在**本次会话的转写区**里找，再按一次跳到下一处。

        为什么不是联网搜索：这条键位在帮助里写的是"搜会话"。绑到一个会发网络请求的
        命令上，用户按下去只会看到"搜索中…"，然后以为界面卡了。
        """
        if self._find_query and getattr(self, "_find_ready", False):
            self._find_advance()
            return
        self._push_text(self._msg("find_title"), "", self._find_start)

    def _push_text(self, title: str, default: str, on_done) -> None:
        """界面自己发起的文本输入（**不阻塞**：这里是主线程，等下去就是死锁）。"""
        try:
            self.push_screen(TextScreen(title, self._msg, on_done, default))
        except Exception:      # noqa: BLE001
            pass

    def _find_start(self, value: Optional[str]) -> None:
        q = str(value or "").strip()
        if not q:
            return
        self._find_query = q
        self._find_ready = True
        self._find_idx = -1
        self._find_advance()

    def _find_advance(self) -> None:
        """跳到下一处命中（到尾回头），并把命中的那条滚进视野。"""
        q = str(getattr(self, "_find_query", "") or "").lower()
        if not q:
            return
        try:
            body = self.query_one("#body", VerticalScroll)
            kids = list(body.children)
        except Exception:      # noqa: BLE001
            return
        texts: List[str] = []
        for _w in kids:
            try:
                texts.append(str(_w.render()))
            except Exception:      # noqa: BLE001
                texts.append("")
        hits = [i for i, t in enumerate(texts) if q in t.lower()]
        if not hits:
            self.notice(self._msg("find_none", q=self._find_query))
            self._find_ready = False
            return
        nxt = next((i for i in hits if i > self._find_idx), hits[0])
        self._find_idx = nxt
        try:
            kids[nxt].scroll_visible(animate=False)
        except Exception:      # noqa: BLE001
            pass
        self.notice(self._msg("find_hit", q=self._find_query,
                              n=hits.index(nxt) + 1, total=len(hits)))

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
