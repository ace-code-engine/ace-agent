#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_styles —— 输出风格预设：一份预设同时管"提示词"和"界面怎么显示"

为什么要有它：想"回答再短一点"的用户，会去改系统提示词；想"少刷屏"的用户，会去关
思考显示/折叠卡片 —— 这两件事在我这里本来是分开的旋钮，可**它们是同一件事的两面**：
选了"简洁"，就该同时（a）让模型少铺垫、去客套，（b）界面别把推理过程与整卡片铺开。
所以预设绑三样东西：

- `prompt`：追加到系统提示词的风格段（**写给模型看的**，所以是英文、短、可执行）；
- `render`：界面旗标（思考显示 / diff 行数上限 / 卡片默认折叠 / 是否只留摘要行）；
- i18n 键：给人看的名字与说明（`style_<id>` / `style_<id>_desc`）。

预设是**数据**，加一档不过是加一条；`resolve_style()` 负责"认不出来就回到默认并如实
报出来"，不静默吞掉用户写错的名字。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

__all__ = ["OutputStyle", "STYLES", "DEFAULT_STYLE", "resolve_style",
           "style_menu", "apply_render_flags"]


class OutputStyle:
    """一档风格：提示词片段 + 界面旗标 + 展示用的 i18n 键。"""

    def __init__(self, sid: str, prompt: str = "", render: Optional[Dict[str, Any]] = None,
                 name_key: str = "", desc_key: str = "") -> None:
        self.id = str(sid)
        self.prompt = str(prompt)
        self.render: Dict[str, Any] = dict(render or {})
        self.name_key = str(name_key or f"style_{self.id}")
        self.desc_key = str(desc_key or f"style_{self.id}_desc")

    def flag(self, name: str, default: Any = None) -> Any:
        return self.render.get(name, default)

    def __repr__(self) -> str:
        return f"OutputStyle({self.id!r}, render={self.render})"


# 三档预设。`prompt` 是给模型的英文指令（短、可执行）；中文名字/说明走 i18n。
STYLES: Dict[str, OutputStyle] = {
    "default": OutputStyle("default", "", {
        "show_thinking": None,        # None = 由 /thinking（F4）自己决定，预设不插手
        "diff_max_lines": 200,
        "collapse_cards": True,
        "summary_only": False,
    }),
    "concise": OutputStyle(
        "concise",
        "Output style — concise: answer in the fewest words that fully answer the "
        "question. No preamble, no restating the question, no closing pleasantries. "
        "Prefer short sentences and code over prose. Skip explanations the user did "
        "not ask for; offer a one-line follow-up instead of elaborating.",
        {"show_thinking": False, "diff_max_lines": 40, "collapse_cards": True,
         "summary_only": True}),
    "explanatory": OutputStyle(
        "explanatory",
        "Output style — explanatory: teach while doing. State what you are about to "
        "do and why in one line before each action, explain non-obvious choices, and "
        "call out trade-offs and pitfalls the user is likely to hit. Keep it tight — "
        "explanation is not padding.",
        {"show_thinking": True, "diff_max_lines": 200, "collapse_cards": False,
         "summary_only": False}),
    "strict": OutputStyle(
        "strict",
        "Output style — strict: only report what you actually verified. Never claim "
        "an action succeeded unless a tool result in this turn shows it. Mark "
        "unverified statements as unverified, and say plainly when something was not "
        "done or could not be checked.",
        {"show_thinking": False, "diff_max_lines": 200, "collapse_cards": True,
         "summary_only": False}),
}
DEFAULT_STYLE = "default"


def resolve_style(raw: Any) -> Tuple[OutputStyle, str]:
    """配置里的 `output_style` → `(预设, 警告)`；认不出就回默认并**说明**。"""
    name = str(raw or "").strip().lower()
    if not name:
        return STYLES[DEFAULT_STYLE], ""
    if name in STYLES:
        return STYLES[name], ""
    return STYLES[DEFAULT_STYLE], f"unknown_style:{name}"


def style_menu() -> List[Tuple[str, str, str]]:
    """`[(id, 名字 i18n 键, 说明 i18n 键)]`，顺序固定（默认在最前）。"""
    order = [DEFAULT_STYLE] + sorted(k for k in STYLES if k != DEFAULT_STYLE)
    return [(k, STYLES[k].name_key, STYLES[k].desc_key) for k in order]


def apply_render_flags(style: OutputStyle, cfg: Dict[str, Any],
                       show_thinking: bool) -> Dict[str, Any]:
    """把风格旗标落到"这次渲染怎么显示"上（返回一份明确的运行时设置）。

    规则写在这里而不是散在调用点：**用户显式开关 > 预设**。例如预设说"简洁→不显示思考"，
    但用户按了 F4 明确要开，那就该听用户的（`cfg["thinking_forced"]` 记录"用户点过"）。
    """
    forced = bool(cfg.get("thinking_forced"))
    st = style.flag("show_thinking", None)
    return {
        "show_thinking": bool(show_thinking) if (forced or st is None) else bool(st),
        "diff_max_lines": int(style.flag("diff_max_lines", 200) or 200),
        "collapse_cards": bool(style.flag("collapse_cards", True)),
        "summary_only": bool(style.flag("summary_only", False)),
        "style": style.id,
    }
