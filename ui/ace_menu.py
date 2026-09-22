#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_menu —— 补全菜单的**模型**：候选从哪来、怎么排、怎么画

为什么要把菜单从"补全器"里拆出来：此前菜单只活在 prompt_toolkit 的 `Completer` 里 ——
装了依赖才存在，没装就只剩一个光秃秃的 `input()`（用户看到的就是"菜单没安装、不好用"）。
把"有哪些候选、当前选中哪个、回车该填什么"抽成纯数据之后：

- **两条渲染路径共用同一份候选**：prompt_toolkit 的浮层菜单，和没有依赖时的自绘菜单
  （`ui/ace_prompt.py`）—— 不会出现"装没装依赖，菜单内容还不一样"；
- 菜单行为可以被断言（候选项、排序、替换区间、回车语义都是纯函数返回值）；
- 加一类候选（斜杠命令 / @ 提及 / 命令参数）只在这里加一处。

菜单打开规则（产品口径，也是本模块的契约）：
- 输入以 `/` 开头 → 命令菜单；以 `@` 开头 → 提及菜单；命令后跟空格 → **参数菜单**；
- 候选按 `ui/ace_selector.filter_items` 的子序列模糊匹配排序（与选择器同一套评分）；
- 回车语义：**候选与已输入内容不同 → 先补全（不发送）**；已经一致 → 直接发送。
  这一条是"菜单不碍事"的关键：否则用户打完 `/help` 还要多按一次回车才能发。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = ["MenuItem", "MenuState", "command_items", "mention_items",
           "argument_items", "build_menu", "render_menu", "menu_hint",
           "MENTION_TRIGGERS", "ARGUMENT_HINTS"]

# `@` 提及的四类（顺序 = 菜单里的展示顺序）
MENTION_TRIGGERS: Tuple[Tuple[str, str], ...] = (
    ("lang", "at_complete_lang"), ("skill", "at_complete_skill"),
    ("file", "at_complete_file"), ("folder", "at_complete_folder"),
)

# 命令的参数提示：命令 → [(参数, 说明 i18n 键)]。有提示的命令输入空格后即弹参数菜单，
# 用户不必去翻 /help —— "下一步能填什么"应该在光标旁边，而不是在另一屏。
ARGUMENT_HINTS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "/permission": (("readonly", "arg_perm_readonly"), ("write", "arg_perm_write"),
                    ("full", "arg_perm_full"), ("rules", "arg_perm_rules")),
    "/sandbox": (("off", "arg_sandbox_off"), ("job", "arg_sandbox_job"),
                 ("docker", "arg_sandbox_docker")),
    "/net": (("on", "arg_net_on"), ("off", "arg_net_off")),
    "/thinking": (("on", "arg_on"), ("off", "arg_off")),
    "/style": (("default", "style_default"), ("concise", "style_concise"),
               ("explanatory", "style_explanatory"), ("strict", "style_strict")),
    "/fullscreen": (("on", "arg_on"), ("off", "arg_off")),
    "/todo": (("add", "arg_todo_add"), ("start", "arg_todo_start"),
              ("done", "arg_todo_done"), ("remove", "arg_todo_remove"),
              ("clear", "arg_todo_clear")),
    "/queue": (("clear", "arg_clear"),),
    "/stash": (("pop", "arg_stash_pop"), ("clear", "arg_clear")),
    "/tasks": (),
}


class MenuItem:
    """一个候选：`label` 给人看，`insert` 是回车/Tab 后真正填进输入框的文本。"""

    def __init__(self, label: str, insert: str = "", desc: str = "",
                 group: str = "", kind: str = "command") -> None:
        self.label = str(label)
        self.insert = str(insert or label)
        self.desc = str(desc)
        self.group = str(group)
        self.kind = str(kind)

    def line(self, mark: str = "  ", width: int = 0) -> str:
        text = f"{mark}{self.label}"
        if self.desc:
            text += f"  {self.desc}"
        return text

    def __repr__(self) -> str:
        return f"MenuItem({self.label!r} → {self.insert!r}, {self.group!r})"


class MenuState:
    """菜单状态：候选列表 + 当前选中 + 是否打开（纯数据，不含 I/O）。"""

    def __init__(self, items: Optional[Sequence[MenuItem]] = None,
                 selected: int = 0, open_: bool = False,
                 kind: str = "", query: str = "",
                 span: Tuple[int, int] = (0, 0)) -> None:
        self.items: List[MenuItem] = list(items or [])
        self.selected = max(0, int(selected))
        self.open = bool(open_) and bool(self.items)
        self.kind = str(kind)
        self.query = str(query)
        self.span: Tuple[int, int] = (int(span[0]), int(span[1]))

    @property
    def current(self) -> Optional[MenuItem]:
        if not self.items:
            return None
        return self.items[min(self.selected, len(self.items) - 1)]

    def move(self, delta: int) -> "MenuState":
        if not self.items:
            return self
        n = len(self.items)
        self.selected = (self.selected + delta) % n      # 循环：到底再按一下回到开头
        return self

    def accepted_text(self, text: str) -> str:
        """把当前候选填进 `text`（替换 `span` 区间）——回车/Tab 的语义就在这一处。"""
        cur = self.current
        if cur is None:
            return text
        start, end = self.span
        return text[:start] + cur.insert + text[end:]

    def __repr__(self) -> str:
        return (f"MenuState(open={self.open}, kind={self.kind!r}, "
                f"n={len(self.items)}, sel={self.selected})")


# ============================================================
# 候选来源
# ============================================================

def command_items(commands: Dict[str, str],
                  custom: Optional[Sequence[Tuple[str, str]]] = None,
                  translate: Optional[Callable[[str], str]] = None,
                  group_of: Optional[Callable[[str], str]] = None
                  ) -> List[MenuItem]:
    """斜杠命令候选：内置（带分组）+ 自定义命令（单独一组放最后）。"""
    tr = translate or (lambda k: k)
    out: List[MenuItem] = []
    for name, desc_key in (commands or {}).items():
        out.append(MenuItem(name, name, tr(desc_key),
                            tr(group_of(name)) if group_of else "", "command"))
    for name, desc in (custom or []):
        out.append(MenuItem(str(name), str(name), str(desc), tr("group_custom"),
                            "custom"))
    return out


def mention_items(kind: str = "", translate: Optional[Callable[[str], str]] = None,
                  values: Optional[Sequence[str]] = None) -> List[MenuItem]:
    """`@` 提及候选：kind 为空时给四类触发词；给定 kind 时给该类的取值（可选）。"""
    tr = translate or (lambda k: k)
    if not kind:
        return [MenuItem(f"@{k}", f"@{k} ", tr(desc_key), tr("group_extend"),
                         "mention")
                for k, desc_key in MENTION_TRIGGERS]
    return [MenuItem(str(v), f"{v} ", "", tr("group_extend"), "mention")
            for v in (values or [])]


def argument_items(cmd: str, translate: Optional[Callable[[str], str]] = None
                   ) -> List[MenuItem]:
    """命令的参数候选（`/permission ` 之后弹的就是它）。"""
    tr = translate or (lambda k: k)
    hints = ARGUMENT_HINTS.get(str(cmd or ""))
    if not hints:
        return []
    return [MenuItem(str(a), str(a) + " ", tr(desc_key), tr(cmd), "argument")
            for a, desc_key in hints]


def _token_under_cursor(text: str, cursor: int) -> Tuple[str, int, int]:
    """光标处的"词"：返回 `(token, start, end)`，以空白为界（`/`、`@` 也算词首）。"""
    t = str(text or "")
    cur = max(0, min(int(cursor), len(t)))
    start = cur
    while start > 0 and not t[start - 1].isspace():
        start -= 1
    end = cur
    while end < len(t) and not t[end].isspace():
        end += 1
    return t[start:end], start, end


def build_menu(text: str, cursor: int, commands: Dict[str, str],
               custom: Optional[Sequence[Tuple[str, str]]] = None,
               translate: Optional[Callable[[str], str]] = None,
               group_of: Optional[Callable[[str], str]] = None,
               mention_values: Optional[Dict[str, Sequence[str]]] = None,
               limit: int = 12) -> MenuState:
    """输入 → 菜单状态（**唯一**决定"此刻该弹什么"的地方）。

    四种情形，优先级从高到低：
      1. 当前词以 `@` 开头 → 提及触发词菜单（`@`、`@la`…）；
      2. 行首词是 `@kind` 且该 kind 有取值 → 提及取值菜单（`@lang ` → zh/en/ja）；
      3. 当前词以 `/` 开头且还没打全 → 命令菜单；
      4. 行首是有参数提示的命令、且已经过了空格 → 参数菜单（`/permission r`）；
    其余（普通文本、命令已打全）→ **关闭**的菜单：不弹就是关，用户不必按 Esc 关它，
    回车也就直接发送（"打完命令回车发出去"这个直觉必须成立）。
    """
    tr = translate or (lambda k: k)
    t = str(text or "")
    cur = max(0, min(int(cursor), len(t)))
    token, start, end = _token_under_cursor(t, cur)
    before = t[:cur]
    first = before.strip().split(" ", 1)[0] if before.strip() else ""

    # ① `@` 触发词
    if token.startswith("@"):
        return _ranked(mention_items("", tr), token[1:], start, end, tr,
                       kind="@", limit=limit)
    # ② `@kind ` 取值（如 @lang → zh/en/ja）
    if first.startswith("@") and first[1:] in (mention_values or {}):
        kind = first[1:]
        known = set((mention_values or {}).get(kind, []))
        used = set(before.split()[1:])
        if used & known:
            return MenuState()          # 取值已经选好：菜单让位，回车直接发送
        values = [v for v in (mention_values or {}).get(kind, []) if v not in used]
        if values:
            return _ranked(mention_items(kind, tr, values), token, start, end, tr,
                           kind=f"@{kind}", limit=limit)
    # ③ 命令菜单
    if token.startswith("/"):
        items = command_items(commands, custom, tr, group_of)
        exact = [it for it in items if it.label == token]
        if exact and len(token) > 1:
            # 命令名已打全：不再拿菜单挡着回车（把回车让给"直接发送"）
            return MenuState(exact, 0, False, "command", token, (start, end))
        return _ranked(items, token, start, end, tr, kind="command", limit=limit)
    # ④ 参数菜单（命令 + 空格）
    if first.startswith("/") and first in ARGUMENT_HINTS and " " in before:
        known = {a for a, _k in ARGUMENT_HINTS[first]}
        used = set(before.split()[1:])
        if used & known:
            # 参数已经选好（`/permission readonly `）：菜单让位，回车直接发送。
            # 否则菜单会一直"再补一个参数"，用户永远按不出回车（探针里踩到过）。
            return MenuState()
        args = [it for it in argument_items(first, tr) if it.label not in used]
        if args:
            return _ranked(args, token, start, end, tr, kind=f"arg:{first}",
                           limit=limit)
    return MenuState()


def _ranked(items: Sequence[MenuItem], query: str, start: int, end: int,
            translate: Callable[[str], str], kind: str,
            limit: int = 12) -> MenuState:
    """模糊排序（复用选择器的子序列评分，与选择器同一套手感）。"""
    items = list(items)
    q = str(query or "").strip()
    if q:
        try:
            from ui.ace_selector import filter_items
            labels = [it.label for it in items]
            order = [i for i, _s in filter_items(labels, q)]
            items = [items[i] for i in order]
        except ImportError:      # 极端情况下退化为前缀匹配
            items = [it for it in items if it.label.startswith(q)]
    # 完全一致的候选排最前（用户已经打全了，回车应该直接发送而不是补全）
    exact = [it for it in items if it.label == q]
    rest = [it for it in items if it.label != q]
    items = exact + rest
    return MenuState(items[:max(1, int(limit))], 0, True, kind, q, (start, end))


# ============================================================
# 渲染
# ============================================================

def render_menu(state: MenuState, width: int = 80, max_rows: int = 8,
                styler: Optional[Callable[[str, str], str]] = None,
                translate: Optional[Callable[[str], str]] = None) -> List[str]:
    """菜单 → 待打印行（纯文本；带分组标题与滚动窗口的省略说明）。

    `styler(kind, text)` 可注入（测试传 no-op 就能断言纯文本）。
    """
    st = styler or (lambda _k, x: x)
    tr = translate or (lambda k: k)
    if not state.items:
        return []
    rows: List[str] = []
    shown = state.items[:max(1, int(max_rows))]
    last_group = None
    sel = min(state.selected, len(state.items) - 1)
    for i, item in enumerate(shown):
        if item.group and item.group != last_group:
            rows.append(st("dim", f"  {item.group}"))
            last_group = item.group
        mark = st("cyan", "▶ ") if i == sel else "  "
        line = item.line("", 0)
        if i == sel:
            line = st("bold", line)
        rows.append(f"{mark}{line}")
    hidden = len(state.items) - len(shown)
    if hidden > 0:
        rows.append(st("dim", tr("menu_more").replace("{n}", str(hidden))))
    rows.append(st("dim", menu_hint(state, tr)))
    return rows


def menu_hint(state: MenuState, translate: Optional[Callable[[str], str]] = None
              ) -> str:
    """一行按键提示（菜单开着时显示在菜单底部）。"""
    tr = translate or (lambda k: k)
    if state.kind.startswith("arg:"):
        return tr("menu_hint_arg")
    if state.kind == "command":
        return tr("menu_hint_command")
    return tr("menu_hint_mention")


def accepts_on_enter(state: MenuState, text: str) -> bool:
    """回车该"补全"还是"发送"（产品口径的唯一判定点）。

    候选与已输入内容不同 → 补全；已经一致 → 发送。这样"打完命令直接回车发出去"
    与"打到一半回车补齐"两个直觉都成立，不必记两条规则。
    """
    cur = state.current
    if cur is None:
        return False
    _token, _s, _e = _token_under_cursor(text, len(text))
    return state.accepted_text(text) != text
