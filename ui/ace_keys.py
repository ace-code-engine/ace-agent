#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_keys —— 键位表：内置语义键 + 用户覆盖 + 冲突判定 + 展示

为什么需要单独一层：键位散在三处 —— `ui/ace_input.KEYMAP` 是"给人看的说明表"、
`ai_code` 里的 `RESERVED_KEYS`/`parse_keybindings` 是"校验"，真绑定又各自写在
prompt_toolkit 的 `@kb.add` 上。于是"用户把 `c-o` 绑到别处"这种事，没有任何地方说得清
结果是什么（两个处理器都跑一半，或者其中一个悄悄失效）。这里把三件事合成一份数据：

- **谁能被覆盖**：`RESERVED_KEYS`（回车/退出等保命键）与 `APP_BOUND_KEYS`
  （`c-s`/`c-l`/`c-o`/`F1`–`F4` 这些已经接了真功能的键）不许覆盖 —— 覆盖它们不是
  "改键位"，是"把功能弄坏一半"，所以直接拒绝并**说明原因**，而不是默默接受；
- **冲突警告**：非法键名、值不是斜杠命令、条数超限、重复绑定，都返回结构化警告
  （带 code，由调用方翻成用户能读的句子）—— 配置里写错了要有人说；
- **展示**：`render_key_table` 纯函数出"待打印行"，`/keys` 只负责喂数据和上色。

纯函数、不读配置、不打印 —— 所以每一条规则都能在没有终端的环境里断言。
"""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional, Sequence, Tuple

__all__ = [
    "RESERVED_KEYS", "APP_BOUND_KEYS", "BUILTIN_KEYS", "KeyBinding",
    "KeyResolution", "resolve_bindings", "render_key_table", "KeyWarning",
]

# 保命键：改掉它们等于把"发不出去/退不出来"写进配置（回车、Esc、Ctrl+C/D…）
RESERVED_KEYS = frozenset(("enter", "c-c", "c-d", "escape", "c-j", "s-enter", "c-m"))

# 已接真功能的键：用户覆盖会让"两件事各做一半"。想换键位可以换到别的键上，
# 但这些键本身不让（与 `/vim` 文档里"保留键不许覆盖"是同一条纪律）。
APP_BOUND_KEYS = frozenset(("c-s", "c-l", "c-o", "f1", "f2", "f3", "f4", "f5"))

# 内置语义键的展示表：(键, 说明 i18n 键)。与 `ui/ace_input.KEYMAP` 同源，
# 但这里不 import 它 —— 后者是"输入层"的说明表，本模块是"键位系统"的模型，
# 两边各有一份会漂，所以 KEYMAP 改为从这里拿（见 ace_input.keys_table 的委托）。
BUILTIN_KEYS: List[Tuple[str, str]] = [
    ("Enter", "keys_enter"),
    ("Alt+Enter / Ctrl+J", "keys_newline"),
    ("↑ / ↓", "keys_history"),
    ("Ctrl+R", "keys_search_history"),
    ("/history <词>", "keys_history_fuzzy"),
    ("F1 / F2 / F3", "keys_axes"),
    ("F4", "keys_thinking"),
    ("Ctrl+O", "keys_expand"),
    ("Ctrl+S", "keys_stash"),
    ("Ctrl+L", "keys_clear_screen"),
    ("Esc", "keys_escape"),
    ("Ctrl+C", "keys_ctrl_c"),
    ("! <命令>", "keys_bash"),
    ("? <回车>", "keys_help"),
]

_KEY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_USER_KEYS = 20


class KeyWarning:
    """一条键位警告：`code` 给调用方翻译，`detail` 是原始值（键名/命令/条数）。

    code 取值：
      reserved        想覆盖保命键（回车/Esc/Ctrl+C…）
      app_bound       想覆盖已接真功能的键（Ctrl+S/Ctrl+O/F1–F4…）
      invalid_key     键名写法不对（prompt_toolkit 的写法：`c-e`/`f5`/`c-s-f`）
      not_command     值不是斜杠命令（自定键位只能走命令，不能开新的执行面）
      too_many        条数超过上限
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail)

    def __repr__(self) -> str:
        return f"KeyWarning({self.code!r}, {self.detail!r})"

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, KeyWarning) and other.code == self.code
                and other.detail == self.detail)


class KeyBinding:
    """一条实际生效的键位：`key`（prompt_toolkit 写法）→ `command`（斜杠命令）。"""

    def __init__(self, key: str, command: str, source: str = "user") -> None:
        self.key = str(key)
        self.command = str(command)
        self.source = str(source)

    def __repr__(self) -> str:
        return f"KeyBinding({self.key!r} → {self.command!r}, {self.source})"

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, KeyBinding) and other.key == self.key
                and other.command == self.command and other.source == self.source)


class KeyResolution:
    """解析结果：生效的键位 + 结构化警告（调用方负责翻译与打印）。"""

    def __init__(self, bindings: Sequence[KeyBinding] = (),
                 warnings: Sequence[KeyWarning] = ()) -> None:
        self.bindings = list(bindings)
        self.warnings = list(warnings)

    @property
    def ok(self) -> bool:
        return not self.warnings

    def commands(self) -> List[str]:
        return [b.command for b in self.bindings]

    def __repr__(self) -> str:
        return f"KeyResolution({self.bindings!r}, warn={len(self.warnings)})"


def resolve_bindings(raw: Any,
                     reserved: Sequence[str] = tuple(RESERVED_KEYS),
                     app_bound: Sequence[str] = tuple(APP_BOUND_KEYS),
                     limit: int = MAX_USER_KEYS) -> KeyResolution:
    """配置里的 `keybindings` → 生效键位 + 警告（**先拒绝再接受**，理由见模块说明）。

    `raw` 非 dict（写成了列表/字符串/数字）时返回空结果 + 一条 `invalid_key`：
    配置写错类型时最坏的结果是"键位没生效但没人知道"，所以这里必须留痕。
    """
    out: List[KeyBinding] = []
    warns: List[KeyWarning] = []
    if raw in (None, "", {}, []):
        return KeyResolution()
    if not isinstance(raw, dict):
        return KeyResolution([], [KeyWarning("invalid_key", type(raw).__name__)])

    _res, _app = set(reserved), set(app_bound)
    items = [(str(k or "").strip().lower(), str(v or "").strip())
             for k, v in raw.items()]
    if len(items) > int(limit):
        warns.append(KeyWarning("too_many", str(len(items))))
        items = items[:int(limit)]
    for key, cmd in items:
        if not key or not cmd:
            warns.append(KeyWarning("invalid_key", key or "<空>"))
            continue
        if not cmd.startswith("/"):
            warns.append(KeyWarning("not_command", f"{key}={cmd}"))
            continue
        if not _KEY_RE.match(key):
            warns.append(KeyWarning("invalid_key", key))
            continue
        if key in _res:
            warns.append(KeyWarning("reserved", key))
            continue
        if key in _app:
            warns.append(KeyWarning("app_bound", key))
            continue
        binding = KeyBinding(key, cmd, "user")
        if binding in out:
            continue
        out.append(binding)
    return KeyResolution(out, warns)


def render_key_table(bindings: Sequence[KeyBinding], width: int = 0,
                     translate: Optional[Callable[[str], str]] = None,
                     builtin: Optional[Sequence[Tuple[str, str]]] = None
                     ) -> List[str]:
    """键位表 → 待打印行：先内置（说明来自 i18n 键），再用户自定义。

    `translate` 缺省时直接显示 i18n 键名（测试里断言用），有它才翻成人话 ——
    本模块不碰 i18n，翻不翻由调用方决定。
    """
    tr = translate or (lambda k: k)
    rows = list(builtin if builtin is not None else BUILTIN_KEYS)
    lines = [tr("keys_header"), f"  {tr('keys_builtin')}"]
    for key, desc_key in rows:
        lines.append(f"    {key:<22}{tr(desc_key)}")
    lines.append(f"  {tr('keys_custom')}")
    if not bindings:
        lines.append(f"    {tr('keys_none')}")
    for b in bindings:
        lines.append(f"    {b.key:<22}{b.command}")
    lines.append(tr("keys_hint"))
    return lines
