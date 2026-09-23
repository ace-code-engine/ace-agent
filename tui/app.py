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
from typing import Any, Callable, List, Optional, Sequence, Tuple

from tui.bridge import EngineBridge
from ui import ace_keys, ace_menu, ace_turn

__all__ = ["AceTuiApp", "run_tui", "EngineBridge"]

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static


def clipboard_image_path() -> str:
    """剪贴板里的图 → 一个临时 PNG 路径；没有图/平台不支持就返回空串。

    为什么单独一个模块级函数：这样测试能替换它（CI 里没有剪贴板，也没有 X11/Windows
    API），同时"拿不到图"这件事在界面上必须**明说**，而不是静默什么都不发生。
    只在 Windows 上实现（用 .NET 的剪贴板）；其它平台返回空串 —— 诚实降级，
    不假装支持。
    """
    import os as _os
    if _os.name != "nt":
        return ""
    import subprocess as _sp
    import tempfile as _tf
    out = _tf.mktemp(suffix=".png")
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$i=[System.Windows.Forms.Clipboard]::GetImage();"
          f"if($i){{$i.Save('{out.replace(chr(92), '/')}')}}")
    try:
        _sp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, timeout=20)
    except Exception:      # noqa: BLE001 —— 拿不到就当没有图
        return ""
    try:
        if _os.path.exists(out) and _os.path.getsize(out) > 0:
            return out
    except OSError:
        return ""
    return ""


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
        # - `Ctrl+F`：输入框把它绑成了"删掉右侧一个词"（`delete_right_word`）；
        # - `Ctrl+C`：输入框把它绑成了"复制"。聊天里 `Ctrl+C` 必须是中断/取消
        #   （这是所有人的肌肉记忆；复制仍可用鼠标选中 + Ctrl+Shift+C）。
        _prio = b.action in ("complete", "cycle_permission", "chord_prefix",
                             "interrupt", "find")
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

    # 和弦第二段的键 → 动作（键名用 Textual 的写法；可打印字符就是字符本身）
    CHORDS = {"e": "expand_all", "t": "tasks", "d": "diff",
              "enter": "queue_submit", "ctrl+s": "send_now",
              "ctrl+e": "external_editor"}

    def vim_editor(self):
        """vim 模式的行编辑器（`/vim on` 之后生效）。"""
        ed = getattr(self, "_vim", None)
        if ed is None:
            from ui.ace_vim import VimLineEditor
            ed = VimLineEditor(self.value or "", self.cursor_position, enabled=False)
            self._vim = ed
        host = getattr(self.app, "ui_host", None)
        cfg = getattr(host, "cfg", None)
        want = bool(isinstance(cfg, dict) and cfg.get("vim_mode"))
        ed.enabled = want
        if not want and ed.mode != "insert":
            ed.state = ed.state.copy(mode="insert")
        return ed

    def chord_action(self, key: str) -> Optional[str]:
        """这个键此刻该触发什么动作（没挂起 / 没登记 → None）。"""
        chords = getattr(self.app, "chords", None)
        if chords is None or not chords.armed:
            return None
        k = str(key or "")
        if k in self.CHORDS:
            return self.CHORDS[k]
        return self.CHORDS.get(k[:1])

    def _sync_vim(self, ed) -> None:
        """把 vim 编辑器的文本/光标写回输入框（两处状态不许漂）。"""
        try:
            self.value = ed.text
            self.cursor_position = max(0, min(ed.cursor, len(ed.text)))
        except Exception:      # noqa: BLE001
            pass
        try:
            self.app._refresh_status()
        except Exception:      # noqa: BLE001
            pass

    async def _on_key(self, event) -> None:
        key = str(getattr(event, "key", "") or "")
        char = getattr(event, "character", "") or ""

        # vim 模式（`/vim on`）：普通模式下所有键都归编辑器，插入模式才走输入框
        ed = self.vim_editor()
        if ed.enabled:
            if key == "escape":
                ed.set_text(self.value or "", self.cursor_position)
                ed.feed("Escape")
                self._sync_vim(ed)
                event.stop()
                event.prevent_default()
                return
            if ed.mode != "insert":
                ed.set_text(self.value or "", self.cursor_position)
                self._sync_vim(ed)
                if ed.feed(key) or ed.last_note:
                    event.stop()
                    event.prevent_default()
                    self._sync_vim(ed)
                return

        # 行编辑三兄弟：Input 自带 ctrl+w/u/k，但**它不填 kill ring**，而且词边界口径
        # 与 readline 不一致（`Ctrl+W` 该按空白切）。所以在这里自己接。
        if key == "ctrl+w":
            event.stop()
            event.prevent_default()
            self.app.action_delete_word_back()
            return
        if key == "ctrl+u":
            event.stop()
            event.prevent_default()
            self.app.action_delete_to_start()
            return
        if key == "ctrl+k":
            event.stop()
            event.prevent_default()
            self.app.action_delete_to_end()
            return

        # `Ctrl+D`：空输入退出（有内容时是 Input 自己的"删右侧字符"，不抢）
        if key == "ctrl+d" and not (self.value or ""):
            event.stop()
            event.prevent_default()
            self.app.exit()
            return

        # 行尾反斜杠 + 回车 = 续行（有些终端送不出 Alt+Enter，这是通用退路）
        if key == "enter" and (self.value or "").endswith("\\"):
            event.stop()
            event.prevent_default()
            self.value = (self.value or "")[:-1] + "\n"
            try:
                self.cursor_position = len(self.value)
            except Exception:      # noqa: BLE001
                pass
            return

        # `?` 在空输入上 = 帮助面板（有字时就是普通问号 —— 不抢用户要打的东西）
        if char == "?" and not (self.value or ""):
            event.stop()
            event.prevent_default()
            handler = getattr(self.app, "action_help", None)
            if callable(handler):
                handler()
            return

        # 剪贴板图片：Ctrl+V / Alt+V。有图就挂上；没有图 → 交回默认粘贴（别吞掉粘贴）
        if key in ("ctrl+v", "alt+v"):
            if clipboard_image_path():
                event.stop()
                event.prevent_default()
                handler = getattr(self.app, "action_paste_image", None)
                if callable(handler):
                    handler()
                return

        action = self.chord_action(key)
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
        if ed.enabled:
            ed.set_text(self.value or "", self.cursor_position)


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
        # `Tab` = 给这次决定加一句话。拒绝时这句话会成为**回传模型的原因**，
        # 于是"不行"不再是一堵墙，而是一次可执行的纠偏（Claude 那边也是这个设计）。
        Binding("tab", "toggle_comment", "备注", show=False),
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
        self.comment = ""
        self.comment_open = False

    def compose(self) -> ComposeResult:
        with Vertical(id="perm_box"):
            yield Static(self.t("perm_request_title", tool=self.tool), id="perm_title")
            if self.reason:
                yield Static(self.t("perm_reason", reason=self.reason), classes="dim")
            for i, (_v, desc_key, danger) in enumerate(self.options):
                cls = "perm_opt" + (" perm_danger" if danger else "")
                yield Static(f"  {i + 1}) {self.t(desc_key)}", classes=cls, id=f"opt{i}")
            yield Input(placeholder=self.t("perm_comment_placeholder"),
                        id="perm_comment")
            yield Static(self.t("perm_hint_keys"), classes="dim")

    def on_mount(self) -> None:
        self._paint()
        try:
            self.query_one("#perm_comment", Input).styles.display = "none"
        except Exception:      # noqa: BLE001
            pass

    def on_input_changed(self, event) -> None:
        self.comment = event.value or ""

    def on_input_submitted(self, event) -> None:
        """在备注里回车 = 带着这句话做决定。"""
        self.comment = event.value or ""
        self.action_choose()

    def action_toggle_comment(self) -> None:
        """`Tab`：开/关备注输入框（开着时焦点进去，Esc 仍等于拒绝）。"""
        self.comment_open = not self.comment_open
        try:
            box = self.query_one("#perm_comment", Input)
            box.styles.display = "block" if self.comment_open else "none"
            if self.comment_open:
                box.focus()
            else:
                self.focus_next()
        except Exception:      # noqa: BLE001
            pass

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
        self._esc_at = 0.0
        self._kill_ring: List[str] = []   # kill ring：Ctrl+K/U/W/Alt+D 删掉的东西
        self._kill_pos = -1
        self._kill_accum = False          # 连续删是否还在累积（readline 的老规矩）
        self._undo: List[Tuple[str, int]] = []
        self._last_prompt: Tuple[str, int] = ("", 0)
        self._undo_guard = False
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
    def _cfg(self) -> dict:
        """宿主的配置字典（读当前档位/开关用）；没有就返回空字典。"""
        cfg = getattr(self.ui_host, "cfg", None)
        return cfg if isinstance(cfg, dict) else {}

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
        self._show_home()
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

    def _show_home(self) -> None:
        """首屏 = 主页（会话区的第一块，打字之后它自然滚上去）。

        为什么不做成独立全屏页：独立页要"进去—出来"两次切换，滚动还会丢；
        而"聊天记录是主线"这件事，靠"主页就是第一块记录"最自然地表达出来。
        """
        host = self.ui_host
        lines: List[str] = []
        try:
            if callable(getattr(host, "home_lines", None)):
                lines = list(host.home_lines(self.size.width - 2) or [])
        except Exception:      # noqa: BLE001 —— 主页画不出来不该拦着启动
            lines = []
        if lines:
            self.append_lines(lines)

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
        # 思考强度：非 auto 才显示（auto 是默认，天天挂在底栏只会变成噪音）
        try:
            from core import ace_effort as _eff
            _lv = _eff.normalize(self._cfg().get("effort"))
            if not _eff.is_auto(_lv):
                parts.append(" " + _eff.symbol(_lv) + _eff.normalize(_lv) + " ")
        except Exception:      # noqa: BLE001
            pass
        parts.append(" " + self.turn.hint(self.t) + " ")
        try:
            _inp = self._prompt()
            _ed = getattr(_inp, "vim_editor", None)
            if callable(_ed):
                _v = _ed()
                if getattr(_v, "enabled", False):
                    parts.append(" " + _v.status() + " ")
        except Exception:      # noqa: BLE001
            pass
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

    @staticmethod
    def _strip_invisible(text: str) -> Tuple[str, int]:
        """去掉零宽/双向控制/标签字符（粘贴来的提示注入最爱藏这儿）。

        返回 `(净化后文本, 去掉几个)`。只去"人看不见但模型看得见"的那类字符；
        波斯语/印度语的连接符与 emoji 变体选择符**保留**（它们是正常文字的一部分）。
        """
        bad = []
        for ch in text:
            cp = ord(ch)
            if (cp == 0x200B or cp == 0x200C and False or cp in (0x200B, 0x200E, 0x200F,
                                                                0x202A, 0x202B, 0x202C,
                                                                0x202D, 0x202E, 0x2066,
                                                                0x2067, 0x2068, 0x2069,
                                                                0xFEFF)
                    or 0xE0000 <= cp <= 0xE007F):
                bad.append(ch)
        clean = "".join(c for c in text if c not in bad)
        return clean, len(bad)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        text, _hidden = self._strip_invisible(text)
        if _hidden:
            self.notice(self._msg("tui_invisible_stripped", n=_hidden))
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
            # 宿主命令可能把"待填进输入框的东西"放在这里（`/history` 就是）
            host = self.ui_host
            pending = str(getattr(host, "_pending_input", "") or "")
            if pending:
                try:
                    host._pending_input = ""
                except Exception:      # noqa: BLE001
                    pass
                self._set_prompt(pending)
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

            _screen: dict = {}

            def _done(value: str) -> None:
                self._perm_slot.append(value)
                _screen["comment"] = str(
                    getattr(_screen.get("widget"), "comment", "") or "")
                self._perm_event.set()

            _scr = PermissionScreen(tool, reason, opts, self._msg, _done)
            _screen["widget"] = _scr
            self.call_from_thread(self.push_screen, _scr)
            self._perm_event.wait(timeout=600)
            self._refresh_status()
            value = self._perm_slot[0] if self._perm_slot else "deny"
            idx = values.index(value) if value in values else len(values) - 1
            resolved = self.turn.answer_permission(idx, opts)
            _comment = str(_screen.get("comment") or "").strip()
            if _comment and resolved is not None:
                # 拒绝的理由要回传模型；允许的备注则当成一句补充说明打出来
                host = self.ui_host
                if resolved == "deny" and host is not None:
                    try:
                        host._deny_feedback = _comment[:400]
                    except Exception:      # noqa: BLE001
                        pass
                else:
                    self.call_from_thread(
                        self.notice, self._msg("perm_comment_sent", text=_comment[:60]))
            if resolved is None:
                # 宽限期内飞过来的答案：不采纳（方向永远收紧）
                self.call_from_thread(self.notice, self.t("grace_inflight"))
                return "deny"
            return resolved

    # ================= 动作 =================
    def _prompt(self):
        try:
            return self.query_one("#prompt", Input)
        except Exception:      # noqa: BLE001
            return None

    def _set_prompt(self, value: str, cursor=None, record: bool = True) -> None:
        inp = self._prompt()
        if inp is None:
            return
        if record:
            self._push_undo()
        self._undo_guard = True
        try:
            inp.value = value
            inp.cursor_position = len(value) if cursor is None else int(cursor)
            self._last_prompt = (str(value), int(inp.cursor_position or 0))
        finally:
            self._undo_guard = False

    def _push_undo(self) -> None:
        """记一个撤销点（`Ctrl+_` 用）。逐键也记 —— 那就是 readline 的 undo 粒度。"""
        inp = self._prompt()
        if inp is None:
            return
        state = (inp.value or "", int(inp.cursor_position or 0))
        if self._undo and self._undo[-1] == state:
            return
        self._undo.append(state)
        del self._undo[:-200]

    def on_input_changed(self, event) -> None:
        """输入框内容变了：把**变化前**的状态记成撤销点 + 刷新补全浮层。

        为什么记"变化前"：`Input.Changed` 是**事后**通知，这时 `value` 已经是新值；
        照它记撤销点，`Ctrl+_` 只会把"当前值"再设一遍（看起来就是"撤销没反应"）。
        """
        self._kill_accum = False      # 打字/别的改动 → 下一次删是新的一格
        if not self._undo_guard:
            prev = getattr(self, "_last_prompt", None)
            if prev is not None and (not self._undo or self._undo[-1] != prev):
                self._undo.append(prev)
                del self._undo[:-200]
        try:
            self._last_prompt = ((event.value or ""), int(event.input.cursor_position or 0))
        except Exception:      # noqa: BLE001
            self._last_prompt = ((event.value or ""), 0)
        self._refresh_palette(event.value or "")


    @staticmethod
    def _is_cjk(ch: str) -> bool:
        """中日韩字符：**每个字自己算一个词**（与 readline/上游的分词口径一致）。

        为什么单独判：`str.isalnum()` 对汉字返回 True，若不特判，`Alt+B` 会把一整句
        中文当成一个词跳过去 —— 而中文用户期望的是"一个字一个字地退"。
        """
        cp = ord(ch)
        return (0x3040 <= cp <= 0x30FF or 0x3400 <= cp <= 0x4DBF
                or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
                or 0xAC00 <= cp <= 0xD7AF)

    @staticmethod
    def _word_bounds(text: str, pos: int, alnum: bool = False):
        """光标前的那个词 `(start, end)`。

        两种口径都要有，因为终端里的习惯就是两种（readline 也一样）：
        - `Ctrl+W`／`Alt+Backspace`：**以空白为界** —— 一下删掉整个 `src/utils/foo.ts`；
        - `Alt+B`／`Alt+F`：**以字母数字为界**（`_ . /` 都算分隔）—— 在
          `src/utils/foo.ts` 里是 `ts` → `foo` → `utils` → `src` 一步步走。
        """
        i = max(0, min(int(pos), len(text)))

        def is_sep(ch: str) -> bool:
            return ch.isspace() or (alnum and not (ch.isalnum() or ch == "_"))

        while i > 0 and is_sep(text[i - 1]):
            i -= 1
        end = i
        while i > 0 and not is_sep(text[i - 1]):
            i -= 1
            if alnum and AceTuiApp._is_cjk(text[i]):
                break                     # CJK：一个字就算一个词
        return i, end

    def _push_kill(self, text: str, append: bool = False) -> None:
        """把删掉的文本放进 kill ring（10 格）。

        两条 readline 的老规矩：
        - 连续删（中间没有别的操作）**攒进同一格** —— 于是 `Ctrl+W` 三次之后一个
          `Ctrl+Y` 能把三个词一起粘回来；
        - 超过 10 格丢最旧的。留 10 格是为了 `Alt+Y` 能往回翻几手，再多也没人翻。
        """
        if not text:
            return
        ring = self._kill_ring
        if append and ring and self._kill_accum:
            ring[-1] = str(ring[-1]) + text      # 连续删：攒进同一格
        else:
            ring.append(text)
        del ring[:-10]
        self._kill_accum = True
        self._kill_pos = len(ring) - 1

    @property
    def _kill(self) -> str:
        """最近一次被删掉的文本（兼容旧的读取点）。"""
        return self._kill_ring[-1] if self._kill_ring else ""

    def action_yank_pop(self) -> None:
        """`Alt+Y`：在 kill ring 里往回翻一格（粘上更早删掉的内容）。"""
        ring = self._kill_ring
        if len(ring) < 2:
            return
        self._kill_pos = (self._kill_pos - 1) % len(ring)
        self._insert_text(str(ring[self._kill_pos]))

    def _insert_text(self, text: str) -> None:
        """在光标处插入文本（不改 kill ring）。"""
        inp = self._prompt()
        if inp is None or not text:
            return
        val = inp.value or ""
        pos = max(0, min(inp.cursor_position, len(val)))
        self._set_prompt(val[:pos] + text + val[pos:], pos + len(text))

    def action_delete_word_back(self) -> None:
        """`Ctrl+W` / `Alt+Backspace`：删掉光标前一个词（readline 手感）。"""
        inp = self._prompt()
        if inp is None:
            return
        val = inp.value or ""
        s, e = self._word_bounds(val, inp.cursor_position)
        if s == e:
            return
        self._push_kill(val[s:e], append=True)
        self._set_prompt(val[:s] + val[e:], s)

    def action_delete_to_start(self) -> None:
        """`Ctrl+U`：删到行首（readline 的老规矩；已在行首就不做）。"""
        inp = self._prompt()
        if inp is None:
            return
        val = inp.value or ""
        pos = inp.cursor_position
        if pos <= 0:
            return
        self._push_kill(val[:pos], append=True)
        self._set_prompt(val[pos:], 0)

    def action_word_left(self) -> None:
        """`Alt+B`：光标退一个词。"""
        inp = self._prompt()
        if inp is None:
            return
        val = inp.value or ""
        s, _e = self._word_bounds(val, inp.cursor_position, alnum=True)
        self._set_prompt(val, s)

    def action_word_right(self) -> None:
        """`Alt+F`：光标前进一个词（停在词尾）。"""
        inp = self._prompt()
        if inp is None:
            return
        val = inp.value or ""
        i = max(0, min(inp.cursor_position, len(val)))

        def is_sep(ch: str) -> bool:
            return ch.isspace() or not (ch.isalnum() or ch == "_")

        while i < len(val) and is_sep(val[i]):
            i += 1
        while i < len(val) and not is_sep(val[i]):
            i += 1
            if self._is_cjk(val[i - 1]):
                break
        self._set_prompt(val, i)

    def action_delete_word_end(self) -> None:
        """`Alt+D`：删到词尾（字母数字口径，与 Alt+F 同一套边界）。"""
        inp = self._prompt()
        if inp is None:
            return
        val = inp.value or ""
        i = max(0, min(inp.cursor_position, len(val)))
        j = i
        while j < len(val) and (val[j].isspace() or not (val[j].isalnum() or val[j] == "_")):
            j += 1
        while j < len(val) and (val[j].isalnum() or val[j] == "_"):
            j += 1
            if self._is_cjk(val[j - 1]):
                break
        if j == i:
            return
        self._push_kill(val[i:j], append=True)
        self._set_prompt(val[:i] + val[j:], i)

    def action_delete_to_end(self) -> None:
        """`Ctrl+K`：删到行尾（存进 kill ring，`Ctrl+Y` 能粘回来）。"""
        inp = self._prompt()
        if inp is None:
            return
        val = inp.value or ""
        pos = max(0, min(inp.cursor_position, len(val)))
        if pos >= len(val):
            return
        self._push_kill(val[pos:], append=True)
        self._set_prompt(val[:pos], pos)

    def action_paste_killed(self) -> None:
        """`Ctrl+Y`：把上次删掉的（Ctrl+K/U/W、Alt+D）粘回来；`Alt+Y` 往回翻。"""
        self._insert_text(self._kill)

    def action_undo(self) -> None:
        """`Ctrl+_` / `Ctrl+Shift+-`：撤销上一次输入编辑（含逐键输入）。

        为什么不是 `Ctrl+Z`：那是终端的挂起键（Unix 上是 SIGTSTP），抢它等于抢掉
        用户"把进程丢到后台"的能力 —— 上游也是这么选的。
        """
        if not self._undo:
            return
        val, pos = self._undo.pop()
        self._set_prompt(val, pos, record=False)

    def action_stash_prompt(self) -> None:
        """`Ctrl+S`：暂存草稿 / 空输入时取回（与 `/stash` 同一份状态）。"""
        self._host_command("/stash")

    def action_queue_submit(self) -> None:
        """`Ctrl+X Enter`：排队发送，**不打断**当前这一轮。"""
        inp = self._prompt()
        text = (inp.value or "").strip() if inp is not None else ""
        if not text:
            return
        self._set_prompt("")
        res = self.turn.submit(text)
        self.append_lines([f"❯ {text}"], "user")
        if res.action == "run":
            self._run_engine(text)
        else:
            self.notice(self._msg("tui_queued_no_interrupt", n=res.queued))

    def action_send_now(self) -> None:
        """`Ctrl+X Ctrl+S` / `Ctrl+Enter`：立刻发送（打断当前轮，草稿与队列一起发）。"""
        inp = self._prompt()
        text = (inp.value or "").strip() if inp is not None else ""
        if self.turn.busy():
            self.turn.interrupt()
            self.turn.interrupt()          # 请求 → 放弃：界面立刻可用
            self.notice(self._msg("tui_send_now"))
        if text:
            self._set_prompt("")
            res = self.turn.submit(text)
            self.append_lines([f"❯ {text}"], "user")
            if res.action == "run":
                self._run_engine(text)
            self.notice(self._msg("tui_sent_now"))

    def action_external_editor(self) -> None:
        """`Ctrl+G` / `Ctrl+X Ctrl+E`：把输入丢进 `$EDITOR` 编辑，存盘读回来。

        长提示词（一大段需求、一次贴十个文件路径）在单行输入框里改是折磨；
        这是 readline 的老办法，也是唯一"用你熟悉的编辑器"的出口。
        """
        inp = self._prompt()
        if inp is None:
            return
        import os as _os
        import subprocess as _sp
        import tempfile as _tf
        editor = (_os.environ.get("VISUAL") or _os.environ.get("EDITOR")
                  or ("notepad" if _os.name == "nt" else "vi"))
        draft = inp.value or ""
        path = _tf.mktemp(suffix=".md")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(draft)
            with self.suspend():
                _sp.call([editor, path])
            with open(path, "r", encoding="utf-8") as fh:
                new = fh.read()
        except Exception as e:      # noqa: BLE001 —— 编辑器起不来就如实说，别丢草稿
            self.notice(self._msg("tui_editor_failed", err=type(e).__name__))
            return
        finally:
            try:
                _os.unlink(path)
            except OSError:
                pass
        if new.strip() != draft.strip():
            self._set_prompt(new.rstrip("\n"))
            self.notice(self._msg("tui_editor_loaded", editor=editor))

    def action_paste_image(self) -> None:
        """`Ctrl+V` / `Alt+V`：把剪贴板里的图挂进下一轮（拿不到就什么都不做）。

        边界写清楚：图会被**原样发给模型提供商**（和 `@image` 同一条路），
        所以成功时会明说一句"将随下一条消息发出"。
        """
        path = clipboard_image_path()
        host = self.ui_host
        if not path:
            self.notice(self._msg("tui_image_none"))
            return
        try:
            host._at_image(path)
        except Exception:      # noqa: BLE001
            self.notice(self._msg("tui_image_failed"))
            return
        self.notice(self._msg("tui_image_attached"))

    def action_quit_if_empty(self) -> None:
        """`Ctrl+D`：输入框空着时退出；有内容时那是 `Input` 自己的"删右侧字符"，不动它。"""
        inp = self._prompt()
        if inp is not None and (inp.value or ""):
            return
        self.exit()

    def action_prev(self) -> None:
        """`Ctrl+P`：查找模式里跳上一处；否则等于"历史里上一条"。"""
        if getattr(self, "_find_ready", False) and self._find_query:
            self._find_advance(-1)
            return
        self.action_nav(-1)

    def action_next(self) -> None:
        """`Ctrl+N`：查找模式里跳下一处；否则等于"历史里下一条"。"""
        if getattr(self, "_find_ready", False) and self._find_query:
            self._find_advance(1)
            return
        self.action_nav(1)

    def action_model_pick(self) -> None:
        """`Alt+M`：模型选择器（与 `/model` 同一个界面入口）。"""
        self._host_command("/model")

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
        """Esc：先收菜单；再按一次（双击）召回上一条消息；正在跑就当中断；否则清输入。

        `Esc Esc` 是 Claude 那边的"改上一条"：一条消息发出去才发现打错了，
        不该逼用户重新打一遍。
        """
        state = getattr(self, "_menu", None)
        if state is not None and state.open:
            self._refresh_palette("")
            self._esc_at = 0.0
            return
        if self.turn.busy():
            self.action_interrupt()
            return
        inp = self._prompt()
        draft = (inp.value or "") if inp is not None else ""
        now = self._now()
        if draft.strip():
            # 有草稿：清空，但**存进历史**（↑ 能召回）——清空不等于丢掉
            if draft.strip() not in self._history:
                self._history.append(draft)
            self._hist_idx = len(self._history)
            self._set_prompt("")
            self._esc_at = now
            self.notice(self._msg("tui_draft_cleared"))
            return
        if (now - float(getattr(self, "_esc_at", 0.0))) <= 1.2:
            self._esc_at = 0.0
            self._open_rewind()
            return
        self._esc_at = now

    def _snapshots(self) -> List[dict]:
        """当前项目的文件快照（拿不到就空列表）。"""
        guardian = getattr(getattr(self.ui_host, "el", None), "guardian", None)
        try:
            return list(guardian.list_snapshots()) if guardian is not None else []
        except Exception:      # noqa: BLE001
            return []

    def _open_rewind(self) -> None:
        """`Esc Esc`（空输入）：**两段式**回溯 —— 先选回到哪一条，再选退什么。

        为什么分两段（抄的是上游的做法，理由也确实成立）："退到哪"和"退什么"是两个
        独立的决定，挤在一个列表里会出现"回退文件到快照 3"和"退对话两轮"这种无法比较
        的选项并排 —— 用户只能靠读完整句判断。分开之后每一步都只有一类东西可比。

        能力门控：没有快照就不给"回退文件"这一项（给了也只会报错）。
        """
        picks = list(dict.fromkeys(reversed(self._history)))[:20]
        if not picks:
            self.notice(self._msg("rewind_no_turns"))
            return
        snapshots = self._snapshots()

        def _stage2(choice) -> None:
            if not choice:
                return
            try:
                idx = picks.index(choice)
            except ValueError:
                return
            turns = idx + 1                     # 从这条开始（含它）一共要退几轮
            actions: List[Tuple[str, str]] = [
                (self._msg("rewind_both", n=turns), f"/rewind {turns}"),
                (self._msg("rewind_talk_only", n=turns), f"/rewind {turns}"),
            ]
            if snapshots:
                sid = snapshots[0].get("id", "?")
                actions.append((self._msg("rewind_files_latest", id=sid),
                                f"/rollback {sid}"))
            actions.append((self._msg("rewind_cancel"), ""))

            def _apply(value) -> None:
                if not value:
                    return
                for label, cmd in actions:
                    if label == value and cmd:
                        self._host_command(cmd)
                        return

            try:
                self.push_screen(ChoiceScreen(self._msg("rewind_action_title"),
                                              [a[0] for a in actions], self._msg,
                                              _apply, filterable=False))
            except Exception:      # noqa: BLE001
                pass

        try:
            self.push_screen(ChoiceScreen(self._msg("rewind_title"), picks,
                                          self._msg, _stage2))
        except Exception:      # noqa: BLE001
            pass

    def action_new_chat(self) -> None:
        """`Alt+N`：开一段新对话（与 `/new` 同一条路）。"""
        self._host_command("/new")

    def action_history(self) -> None:
        """`Alt+H`：历史对话 —— 走 `/sessions` 的选择框。"""
        self._host_command("/sessions")

    def action_effort(self) -> None:
        """`Alt+T`：思考强度环（auto → low → medium → high）。"""
        self._host_command("/effort next")

    def action_net_toggle(self) -> None:
        """`Alt+W`：联网思考开关。"""
        self._host_command("/net")

    def action_lang(self) -> None:
        """`Alt+L`：回答语言环（中文 → English → 日本語）。"""
        self._host_command("/lang next")

    def action_home(self) -> None:
        """`Alt+1` / `/home`：把主页再打一遍（会话滚上去之后想再看一眼）。"""
        self._show_home()

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

    def _find_advance(self, delta: int = 1) -> None:
        """跳到下一处命中（到尾回头 / 反向同理），并把命中的那条滚进视野。"""
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
        if int(delta) >= 0:
            nxt = next((i for i in hits if i > self._find_idx), hits[0])
        else:
            nxt = next((i for i in reversed(hits) if i < self._find_idx), hits[-1])
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
        """`Ctrl+R`：模糊搜历史（跨会话），选中就填进输入框。

        为什么不是"直接往回填一条"：历史长了以后一条条翻是折磨，`/history` 那套
        模糊匹配 + 选择框才是这个键该有的样子（Claude 的 Ctrl+R 也是搜索）。
        """
        if self._history:
            self._history_picker()
            return
        self._host_command("/history")

    def _history_picker(self) -> None:
        items = list(dict.fromkeys(reversed(self._history)))     # 去重、最近的在前

        def _done(value) -> None:
            if value:
                self._set_prompt(str(value))

        try:
            self.push_screen(ChoiceScreen(self._msg("history_pick"), items,
                                          self._msg, _done))
        except Exception:      # noqa: BLE001
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
