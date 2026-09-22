#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_vim —— vim 子集：motions / operators / text objects（纯函数）

为什么自己写一层：prompt_toolkit 的 `EditingMode.VI` 只给了"基本按键编辑"（h/j/k/l、
词移动、进入插入模式），**没有操作符 + 文本对象**这一套真正让人快的东西 —— `ciw`、
`da"`、`d2w`、`y$` 这些才是 vim 用户的条件反射。这一层是纯文本变换：

- 全部纯函数：`(text, cursor) + 键序列 → (text, cursor, mode)`，不碰终端、不碰 Buffer；
- 支持 **计数**（`2w`、`d2w`、`2dd`）、**操作符 + motion**（`dw`/`c$`/`y0`）、
  **文本对象**（`iw`/`aw`/`i"`/`a"`/`i(`/`a(`/`ip`）、单键操作（`x`/`D`/`C`/`dd`/`cc`/`yy`）；
- 认不出的键**不猜**：返回 `note` 说明"这个键没绑"，调用方决定提示还是忽略。

不做的（也写在这里，免得下一版又纠结）：撤销栈、寄存器、宏、`. ` 重复、可视模式、
搜索 `/`。它们要么需要一整套状态机（寄存器/撤销），要么在"输入一行提示词"这个场景里
收益极低 —— 把上面这几条做对，已经覆盖日常输入的绝大多数动作。
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

__all__ = ["VimState", "VimError", "word_spans", "text_object",
           "move_cursor", "vim_apply", "vim_step", "MOTIONS", "TEXT_OBJECTS",
           "parse_command", "VimLineEditor"]

_WORD = re.compile(r"[A-Za-z0-9_]+")


class VimError(Exception):
    """键序列非法（未知键、不完整命令、motion 与 operator 不匹配）。"""


# 单字符边界：成对符号 + 引号（vim 的 text object 语义）
_PAIRS = {'"': '"', "'": "'", "`": "`", "(": ")", ")": "(", "[": "]", "]": "[",
          "{": "}", "}": "{", "<": ">", ">": "<"}


def word_spans(text: str) -> List[Tuple[int, int]]:
    """把文本切成"词"的区间（字母数字下划线一串 = 一个词；其余非空白各算一段）。

    与 vim 的 `w` 语义接近但不追求逐字节一致：这里是"一行提示词"的编辑，中文按字切、
    标点各算一段就够用了，而**边界一定要可预期**（否则 `ciw` 会删掉意料之外的东西）。
    """
    spans: List[Tuple[int, int]] = []
    i, n = 0, len(text or "")
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        m = _WORD.match(text, i)
        if m:
            spans.append((m.start(), m.end()))
            i = m.end()
        else:
            spans.append((i, i + 1))
            i += 1
    return spans


def text_object(text: str, cursor: int, obj: str) -> Optional[Tuple[int, int]]:
    """文本对象 → `(start, end)` 区间；找不到返回 None（调用方给提示，不静默删错东西）。

    支持：`iw`/`aw`（词，a 含尾随空白）、`i"`/`a"`（引号内/含引号）、`i(`/`a(`（括号内/含）、
    `ip`/`ap`（整行，一行提示词里等价于全选，保留给习惯用它的人）。
    """
    o = str(obj or "")
    if not o or len(o) < 2:
        return None
    inner = o[0] == "i"
    ch = o[1]
    n = len(text or "")
    cur = max(0, min(int(cursor), n))

    if ch == "p":
        return (0, n)
    if ch == "w":
        for s, e in word_spans(text):
            if s <= cur < e or (cur == e and s <= cur - 1 < e):
                if inner:
                    return (s, e)
                end = e
                while end < n and text[end].isspace():
                    end += 1
                return (s, end)
        return None
    if ch in _PAIRS:
        target = _PAIRS[ch]
        # 从光标处向两侧找最近的一对（多行/嵌套不做，一行提示词里没有嵌套的必要）
        left = text.rfind(ch, 0, cur + 1)
        right = text.find(target, cur if left < 0 else left + 1)
        if left < 0 or right < 0 or right <= left:
            return None
        if inner:
            return (left + 1, right)
        return (left, right + 1)
    return None


# motion：`(text, cursor, count) → 新光标位置`
def _m_h(t: str, c: int, n: int) -> int:
    return max(0, c - n)


def _m_l(t: str, c: int, n: int) -> int:
    return min(len(t), c + n)


def _m_0(t: str, c: int, n: int) -> int:
    return 0


def _m_dollar(t: str, c: int, n: int) -> int:
    return len(t)


def _m_w(t: str, c: int, n: int) -> int:
    pos = c
    for _ in range(max(1, n)):
        starts = [s for s, _e in word_spans(t) if s > pos]
        if not starts:
            return len(t)
        pos = starts[0]
    return pos


def _m_b(t: str, c: int, n: int) -> int:
    pos = c
    for _ in range(max(1, n)):
        starts = [s for s, _e in word_spans(t) if s < pos]
        if not starts:
            return 0
        pos = starts[-1]
    return pos


def _m_e(t: str, c: int, n: int) -> int:
    pos = c
    for _ in range(max(1, n)):
        ends = [e for _s, e in word_spans(t) if e > pos]
        if not ends:
            return len(t)
        pos = ends[0]
    return pos


MOTIONS: Dict[str, Callable[[str, int, int], int]] = {
    "h": _m_h, "l": _m_l, "0": _m_0, "$": _m_dollar,
    "w": _m_w, "b": _m_b, "e": _m_e,
    "gg": _m_0, "G": _m_dollar,
}

TEXT_OBJECTS = ("iw", "aw", 'i"', 'a"', "i'", "a'", "i(", "a(", "i[", "a[",
                "i{", "a{", "ip", "ap")

# 单键操作（vim 里它们自成一条命令，不需要先按 d/c）
ONE_KEY = {"x": ("d", "x"), "D": ("d", "D"), "C": ("c", "C"),
           "p": ("p", "p"), "P": ("p", "P")}

# 右向 motion 里**包含末字符**的（vim 语义）：`dl` 删光标下那个字符、`d$` 删到行尾；
# `dw` 则不包含下一个词的首字符。左向 motion 一律不含光标处字符（`dh` 删光标左边一个）。
_INCLUSIVE_RIGHT = frozenset(("e", "$", "G", "l"))


class VimState:
    """vim 编辑状态：文本、光标、待定计数/操作符。

    `pending` 里存的是"还没凑齐的命令"（计数 + 操作符 + 目标），
    `vim_step` 每次吃一个键并返回新状态（**不可变**，好断言也免得调用方漏抄字段）。
    """

    def __init__(self, text: str = "", cursor: int = 0, mode: str = "normal",
                 pending: str = "", count: int = 0, note: str = "") -> None:
        self.text = str(text)
        self.cursor = max(0, min(int(cursor), len(self.text)))
        self.mode = "insert" if mode == "insert" else "normal"
        self.pending = str(pending)          # 例如 "d2"
        self.count = int(count)
        self.note = str(note)

    def copy(self, **kw) -> "VimState":
        st = VimState(self.text, self.cursor, self.mode, self.pending,
                      self.count, self.note)
        for k, v in kw.items():
            setattr(st, k, v)
        return st

    def __repr__(self) -> str:
        return (f"VimState({self.text!r}, c={self.cursor}, {self.mode}, "
                f"pending={self.pending!r}, n={self.count})")


def _digits(pending: str) -> str:
    m = re.match(r"^(\d*)", pending or "")
    return m.group(1) if m else ""


def parse_command(keys: str) -> Tuple[int, str, str]:
    """键序列 → `(count, operator, target)`（不合法就抛 `VimError`）。

    认得的形状：`[count][operator][count][motion|textobj]`、`[count]motion`、
    `[count]operator`（`dd`/`cc`/`yy`/`x`/`D`/`C`）。
    """
    s = str(keys or "")
    m = re.match(r"^(\d*)([dcy]?)(\d*)(.*)$", s)
    if not m:
        raise VimError(f"看不懂的键序列: {keys!r}")
    c1, op, c2, rest = m.group(1), m.group(2), m.group(3), m.group(4)
    count = int(c1 or 1) * int(c2 or 1) if (c1 or c2) else 1
    count = count or 1
    if not op:
        if not rest:
            raise VimError("缺少动作")
        if rest not in MOTIONS:
            raise VimError(f"未绑定的动作: {rest}")
        return count, "", rest
    if not rest:
        if op in ("d", "c", "y"):
            return count, op, op            # dd / cc / yy（操作符后面没跟目标 = 整行）
        raise VimError(f"操作符 {op} 后面还缺一个动作")
    if rest == op:                          # `dd`/`cc`/`yy`：目标就是操作符本身
        return count, op, op
    if rest in MOTIONS:
        return count, op, rest
    if rest in TEXT_OBJECTS or rest in ("x", "D", "C", "p", "P"):
        return count, op, rest
    raise VimError(f"未绑定的目标: {rest}")


def move_cursor(text: str, cursor: int, target: str, count: int = 1) -> int:
    """纯光标移动（供 motion 与操作符共用）。"""
    if target in MOTIONS:
        return MOTIONS[target](text, max(0, min(cursor, len(text))), max(1, count))
    if target in TEXT_OBJECTS:
        span = text_object(text, cursor, target)
        if span is None:
            raise VimError(f"找不到文本对象: {target}")
        return span[0]
    raise VimError(f"未绑定的目标: {target}")


def _range_for(text: str, cursor: int, op: str, target: str,
               count: int) -> Optional[Tuple[int, int]]:
    """操作符 + 目标 → 作用区间 `(start, end)`；目标不存在时返回 None。

    返回 None（而不是抛异常）是有意的：`di"` 停在引号外、`dw` 已在行尾都是**正常情况**
    （vim 里也只是"什么都不做"），调用方需要的是"没做成 + 为什么"，不是一次异常。
    """
    n = len(text)
    cur = max(0, min(cursor, n))
    if target in TEXT_OBJECTS:
        return text_object(text, cur, target)
    if target in ("x", "D", "C"):
        if target == "x":
            return (cur, min(n, cur + max(1, count)))
        return (cur, n)                      # D / C：到行尾
    if target in ("p", "P"):
        return (cur, cur)                    # 粘贴位置（内容由调用方给，这里只定位）
    if target == op:                          # dd / cc / yy：整行
        return (0, n)
    if target not in MOTIONS:
        return None
    dest = MOTIONS[target](text, cur, max(1, count))
    if dest >= cur:
        end = dest + (1 if target in _INCLUSIVE_RIGHT and dest < n else 0)
        return (cur, min(n, max(cur, end)))
    return (dest, cur)                        # 向左：不含光标处字符


def vim_apply(state: VimState, operator: str, target: str, count: int = 1,
              register: str = "") -> VimState:
    """把一条完整命令作用到文本上（`operator` 为空 = 纯移动；`y` = 复制不删）。

    失败一律**不改文本**、只留 `note`：编辑一行提示词时"悄悄删错东西"比"没生效"坏得多。
    """
    text, cur = state.text, state.cursor
    if not operator:
        if target not in MOTIONS and target not in TEXT_OBJECTS:
            return state.copy(pending="", count=0, note=f"error:未绑定的动作: {target}")
        try:
            return state.copy(cursor=move_cursor(text, cur, target, count),
                              pending="", count=0, note="")
        except VimError as e:
            return state.copy(pending="", count=0, note=f"error:{e}")
    if operator == "p":
        if not register:
            return state.copy(pending="", count=0, note="register-empty")
        return state.copy(text=text[:cur] + register + text[cur:],
                          cursor=cur + len(register), pending="", count=0, note="")
    span = _range_for(text, cur, operator, target, count)
    if span is None:
        return state.copy(pending="", count=0, note=f"no-target:{target}")
    start, end = span
    if operator == "y":
        return state.copy(cursor=start, pending="", count=0,
                          note=f"yanked:{text[start:end]}")
    new_text = text[:start] + text[end:]
    if operator == "c":                      # c：删除后进插入模式（vim 的语义）
        return state.copy(text=new_text, cursor=min(start, len(new_text)),
                          mode="insert", pending="", count=0, note="")
    return state.copy(text=new_text, cursor=min(start, len(new_text)),
                      pending="", count=0, note="")


def vim_step(state: VimState, key: str, register: str = "") -> VimState:
    """吃一个键，返回新状态（vim 的核心小状态机）。

    - 插入模式：除 `Esc` 外一切原样交给调用方（这里只切换模式，不动文本）；
    - 普通模式：数字累加计数，`d/c/y` 挂起等目标，`x`/`D`/`C` 立即执行，
      其它键按 motion 走；凑不齐就停在 `pending` 上（**不猜、不提前动手**）。
    """
    k = str(key or "")
    st = state
    if st.mode == "insert":
        if k == "Escape":
            return st.copy(mode="normal", cursor=max(0, st.cursor - 1), note="")
        return st                              # 插入模式：调用方自己插字符

    if k == "Escape":
        return st.copy(pending="", count=0, note="")
    if k.isdigit() and not (k == "0" and not st.pending):
        return st.copy(pending=st.pending + k, note="")
    if k in ("d", "c", "y") and not st.pending.endswith(k):
        return st.copy(pending=st.pending + k, note="")
    if k in ("i", "a") and st.mode == "normal" and not st.pending:
        return st.copy(mode="insert", note="insert")
    if k == "A":
        return st.copy(mode="insert", cursor=len(st.text), note="insert")
    if k == "I":
        return st.copy(mode="insert", cursor=0, note="insert")
    # 单键操作（x / D / C / p / P）：vim 里它们自成命令，不必先按 d/c。
    # 带计数时（`3x`）pending 里是数字，也在这里一并处理。
    if k in ONE_KEY and (not st.pending or st.pending.isdigit()):
        op, target = ONE_KEY[k]
        count = int(st.pending) if st.pending.isdigit() else 1
        return vim_apply(st.copy(pending=""), op, target, count, register)

    seq = st.pending + k
    # 两位数 motion（gg）与 `i`/`a` 开头的文本对象：先看是不是前缀
    if seq in ("gg",) or seq.endswith("gg") or seq[-1] in ("i", "a"):
        if seq.endswith(("i", "a")) and len(seq) > 1 and not seq[-2].isdigit():
            return st.copy(pending=seq, note="")
        if seq.endswith("gg"):
            return vim_apply(st, "", "gg", 1)
    if seq[-1] in ("i", "a") and not re.search(r"[dcy]\d*$", seq[:-1] or ""):
        return st.copy(pending=seq, note="")
    try:
        count, op, target = parse_command(seq)
    except VimError as e:
        # 凑不齐（等下一个键）还是真不认识？只有"前缀"才继续等，其余如实报错
        if len(seq) <= 3 and re.match(r"^(\d*)([dcy]?)(\d*)$", seq):
            return st.copy(pending=seq, note="")
        return st.copy(pending="", count=0, note=f"error:{e}")
    if not op and target in ("i", "a"):
        return st.copy(pending=seq, note="")
    return vim_apply(st, op, target, count, register)

class VimLineEditor:
    """把 vim 子集接到**一条输入行**上（纯逻辑：喂键 → 文本/光标/模式）。

    接线方只做两件事：把按键喂进来、把 `text`/`cursor` 同步给真实输入框。
    这样"vim 键位怎么解析"和"prompt_toolkit 的 Buffer 怎么用"彻底分开 ——
    前者可以被断言（纯函数），后者只管搬字节。

    `enabled=False` 时等同普通插入模式（不拦截任何键），这样上层不用为"没开 vim"
    写第二条分支。
    """

    def __init__(self, text: str = "", cursor: int = 0, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self.state = VimState(text, cursor, "normal" if self.enabled else "insert")
        self.register = ""
        self.last_note = ""

    # ---- 只读视图 ----
    @property
    def text(self) -> str:
        return self.state.text

    @property
    def cursor(self) -> int:
        return self.state.cursor

    @property
    def mode(self) -> str:
        return self.state.mode if self.enabled else "insert"

    @property
    def pending(self) -> str:
        return self.state.pending

    # ---- 外部同步 ----
    def set_text(self, text: str, cursor: Optional[int] = None) -> None:
        """输入框改了内容（如粘贴、清空）时同步进来，避免两处状态漂。"""
        self.state = self.state.copy(
            text=str(text or ""),
            cursor=self.state.cursor if cursor is None else int(cursor))

    def reset(self) -> None:
        self.state = VimState("", 0, "normal" if self.enabled else "insert")
        self.last_note = ""

    # ---- 按键 ----
    def feed(self, key: str) -> bool:
        """吃一个键；返回 True = 文本或光标变了（接线方需要回写输入框）。

        插入模式下的普通字符由 `insert()` 处理（prompt_toolkit 自己会插），
        这里只认 `Escape`（回普通模式）—— 所以 feed 返回 False 时，
        接线方应当把该键交给输入框自己处理。
        """
        if not self.enabled:
            return False
        before = (self.state.text, self.state.cursor, self.state.mode)
        if self.state.mode == "insert" and key != "Escape":
            return False
        self.state = vim_step(self.state, key, self.register)
        if self.state.note.startswith("yanked:"):
            self.register = self.state.note.split(":", 1)[1]
        self.last_note = self.state.note
        return (self.state.text, self.state.cursor, self.state.mode) != before

    def insert(self, chars: str) -> None:
        """插入模式：在光标处插入文本（由接线方在把键交给输入框之后再同步）。"""
        s = str(chars or "")
        if not s:
            return
        t, c = self.state.text, self.state.cursor
        self.state = self.state.copy(text=t[:c] + s + t[c:], cursor=c + len(s))

    def backspace(self) -> bool:
        """插入模式退格（普通模式的 `x` 走 feed）。"""
        t, c = self.state.text, self.state.cursor
        if c <= 0:
            return False
        self.state = self.state.copy(text=t[:c - 1] + t[c:], cursor=c - 1)
        return True

    def status(self) -> str:
        """状态栏片段：`-- 普通 --` / `-- 插入 --`，带未完成命令（`d2`）。"""
        mode = "插入" if self.mode == "insert" else "普通"
        tail = f" {self.state.pending}" if self.state.pending else ""
        return f"-- {mode}{tail} --"
