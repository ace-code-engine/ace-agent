#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_home —— 主页的**模型**：分区、条目、当前选中、渲染（纯逻辑）

## 主页该回答的三个问题（顺序就是分区的顺序）

1. **接着干什么** —— 继续上次 / 新对话 / 历史对话（并列出最近几条）；
2. **现在是什么状态、怎么改** —— 思考强度 · 联网思考 · 输出语言 · 权限档；
3. **我们独有的东西在哪** —— 回溯（退对话/回退文件）· 任务树 · 改动 · 报告。

顺序不是随手排的：**"继续"排在最前**是因为绝大多数人打开就是想接着上次说；
"能力开关"排第二是因为它们要在**开始之前**定好（改错了要重来）；
"特色"排最后 —— 它们是"需要时才找"的东西，常驻在眼前只会挤掉前两类。

## 为什么是"会话区里的一块"而不是独立全屏页

独立页意味着"进去—出来"两次切换，而且滚动会丢。做成会话区里的一块：
进来先看见它，打字/回车之后它自然滚上去 —— 与"聊天记录是主线"这件事一致。

纯逻辑：不读配置、不打印、不碰时钟。接线方给状态与最近会话，拿回待打印的行。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ui.ace_text import display_width, pad_width

__all__ = ["HomeItem", "HomeSection", "build_home", "render_home", "selectable",
           "move_selection", "HOME_KEYS", "action_for_key", "SECTIONS_ORDER",
           "title_line", "hint_line"]

# 分区顺序（改这里就是改主页的信息层级）
SECTIONS_ORDER: Tuple[str, ...] = ("resume", "start", "ability", "feature")

# 主页上的快捷键：这些键在主页里直接生效（不必先把光标移到那一行）
HOME_KEYS: Dict[str, str] = {
    "alt+n": "new", "alt+h": "history", "alt+r": "resume_last",
    "alt+t": "effort", "alt+w": "net", "alt+l": "lang",
    "shift+tab": "permission", "alt+m": "model",
    "escape escape": "rewind", "alt+k": "tasks",
}


class HomeItem:
    """主页上的一行：`action` 是语义动作名（不是命令字符串，便于测试断言）。"""

    __slots__ = ("action", "label_key", "value", "hint_key", "section", "enabled",
                 "fmt")

    def __init__(self, action: str, label_key: str, value: str = "",
                 hint_key: str = "", section: str = "", enabled: bool = True,
                 fmt: Optional[Dict[str, object]] = None) -> None:
        self.action = str(action)
        self.label_key = str(label_key)
        self.value = str(value)          # 已经是给人看的字面量（档位/开关/条数）
        self.hint_key = str(hint_key)
        self.section = str(section)
        self.enabled = bool(enabled)
        self.fmt = dict(fmt or {})

    def label(self, translate: Callable[[str], str]) -> str:
        try:
            return translate(self.label_key).format(**self.fmt)
        except Exception:      # noqa: BLE001 —— 少一个占位符不该把主页打崩
            return translate(self.label_key)

    def __repr__(self) -> str:
        return f"HomeItem({self.action!r}, {self.label_key!r}, value={self.value!r})"


class HomeSection:
    """一个分区：标题 + 若干条目（顺序即展示顺序）。"""

    __slots__ = ("key", "title_key", "items")

    def __init__(self, key: str, title_key: str,
                 items: Optional[Sequence[HomeItem]] = None) -> None:
        self.key = str(key)
        self.title_key = str(title_key)
        self.items: List[HomeItem] = list(items or [])

    def __repr__(self) -> str:
        return f"HomeSection({self.key!r}, n={len(self.items)})"


def _onoff(flag: bool) -> str:
    return "on" if flag else "off"


def build_home(state: Dict[str, object],
               sessions: Optional[Sequence[Dict[str, object]]] = None
               ) -> List[HomeSection]:
    """状态 + 最近会话 → 主页分区。

    `state` 用**普通字典**（不是某个类）：主页要显示的东西来自四个不同的地方
    （配置、执行层、i18n、会话记录），统一成一份只读快照，接线方一处组装、
    这里一处消费 —— 省得主页自己去翻五个对象。
    """
    st = dict(state or {})
    sess = list(sessions or [])
    out: List[HomeSection] = []

    # ① 接着干什么
    resume_items: List[HomeItem] = []
    if sess:
        newest = sess[0]
        _when = str(newest.get("when") or "").strip()
        _turns = int(newest.get("turns") or 0)
        _proj = str(newest.get("project") or "").strip()
        resume_items.append(HomeItem(
            "resume_last", "home_resume_last", "",
            "home_resume_last_hint", "resume",
            # 时间拿不到时**不留空括号**；有项目名就先报项目名（比时间更能认出是哪一段）
            fmt={"when": ((_proj + " · ") if _proj else "") + ((_when + " · ") if _when else ""),
                 "turns": _turns,
                 "label": str(newest.get("label") or "")[:40]}))
    else:
        resume_items.append(HomeItem(
            "resume_last", "home_resume_none", "", "home_resume_none_hint",
            "resume", enabled=False))
    out.append(HomeSection("resume", "home_sec_resume", resume_items))

    # ② 开始：新对话 / 历史对话
    out.append(HomeSection("start", "home_sec_start", [
        HomeItem("new", "home_new", "", "home_new_hint", "start"),
        HomeItem("history", "home_history", "", "home_history_hint",
                 "start", enabled=bool(sess), fmt={"n": len(sess)}),
        HomeItem("help", "home_help", "", "home_help_hint", "start"),
    ]))

    # ③ 能力开关（当前值直接显示在行里：主页的价值一半在"现在是什么"）
    out.append(HomeSection("ability", "home_sec_ability", [
        HomeItem("effort", "home_effort", str(st.get("effort") or ""),
                 "home_effort_hint", "ability"),
        HomeItem("net", "home_net", _onoff(bool(st.get("net"))),
                 "home_net_hint", "ability"),
        HomeItem("lang", "home_lang", str(st.get("lang") or ""),
                 "home_lang_hint", "ability"),
        HomeItem("permission", "home_permission", str(st.get("permission") or ""),
                 "home_permission_hint", "ability"),
        HomeItem("model", "home_model", str(st.get("model") or ""),
                 "home_model_hint", "ability"),
    ]))

    # ④ 特色：回溯是这一版的重点
    snaps = int(st.get("snapshots") or 0)
    out.append(HomeSection("feature", "home_sec_feature", [
        HomeItem("rewind", "home_rewind", "", "home_rewind_hint", "feature",
                 fmt={"n": snaps}),
        HomeItem("tasks", "home_tasks", "", "home_tasks_hint", "feature"),
        HomeItem("report", "home_report", "", "home_report_hint", "feature"),
    ]))
    return out


def selectable(sections: Sequence[HomeSection]) -> List[HomeItem]:
    """能选中的条目（平铺，顺序与渲染一致）—— 上下键就在这上面走。"""
    return [it for sec in sections for it in sec.items if it.enabled]


def move_selection(items: Sequence[HomeItem], index: int, delta: int) -> int:
    """选中项移动（循环）——空列表返回 0，调用方不必自己判。"""
    if not items:
        return 0
    return (int(index) + int(delta)) % len(items)


def action_for_key(key: str) -> str:
    """主页里的快捷键 → 动作名（没登记返回空串，调用方照常处理这个键）。"""
    return HOME_KEYS.get(str(key or "").strip().lower(), "")


def title_line(version: str, model: str, permission: str, sandbox: str = "",
               styler: Optional[Callable[[str, str], str]] = None,
               folder: str = "", folder_label: str = "") -> str:
    """主页顶行：`ACE 3.39.0 · 模型 · 权限 · 沙箱`。

    顶行只放"一眼要确认的三件事"，其余状态归底栏 —— 主页不该是仪表盘。
    """
    st = styler or (lambda _k, x: x)
    bits = [st("bold", f"ACE {version}")]
    if folder:
        # **不用 emoji**：中文 Windows 控制台是 cp936，📁 印不出来会变成乱码
        # （这正是本项目早期就写下的纪律："刻意不用 emoji"）。用文字标签代替。
        label = f"{folder_label} " if folder_label else ""
        bits.append(st("cyan", f"{label}{folder}"))   # 在哪个文件夹里 —— 一眼要确认的第四件事
    bits.extend([st("dim", str(model or "?")), st("dim", str(permission or "?"))])
    if sandbox and sandbox != "off":
        bits.append(st("warn", f"沙箱 {sandbox}"))
    return " · ".join(bits)


def hint_line(translate: Callable[[str], str],
              styler: Optional[Callable[[str, str], str]] = None) -> str:
    """主页底部一行：告诉人"这里怎么操作"。"""
    st = styler or (lambda _k, x: x)
    return st("dim", translate("home_hint"))


def render_home(sections: Sequence[HomeSection],
                translate: Callable[[str], str],
                width: int = 80,
                selected: int = 0,
                styler: Optional[Callable[[str, str], str]] = None,
                header: str = "",
                meta: str = "",
                footer: str = "") -> List[str]:
    """主页 → 待打印行（纯文本；`styler(kind, text)` 可注入，测试传 no-op）。

    选中标记只在**可选中**的条目上走，并且不会因为禁用的条目而错位 ——
    "看得见的行"和"能选的行"是两件事，这里明确分开。

    `meta`：标题下面的一行**背景度量**（跨会话累计用量）。刻意做成一行纯文本而不是
    一个分区条目 —— 它不需要被选中、也不该挤进"接着干什么"的选择序列。
    """
    st = styler or (lambda _k, x: x)
    lines: List[str] = []
    if header:
        lines.append(header)
    if meta:
        lines.append(meta)
    if header or meta:
        lines.append("")
    cursor = 0
    for sec in sections:
        # 标签列宽：同一个分区里对齐（值/说明排成一列才好扫）。太宽也不好，
        # 会把人眼从标签拽到空白上 —— 所以封顶 20 列。
        labels = [it.label(translate) for it in sec.items]
        pad = min(20, max([display_width(x) for x in labels] + [10])) + 2
        # 值列也要对齐：`auto` / `on` / `zh` 宽度不同，不对齐的话说明列会参差
        vals = [it.value for it in sec.items if it.value]
        vpad = (min(12, max([display_width(x) for x in vals])) + 2) if vals else 0
        rows: List[str] = []
        for item, label in zip(sec.items, labels):
            take = item.enabled
            # 标记也走降级：cp936 印不出 ▶/·，换 `>`/`.`（同 core/ace_io.py 的表）
            from core import ace_io as _io
            if take:
                mark = st("cyan", _io.glyph("▶")) if cursor == selected else " "
                cursor += 1
            else:
                mark = st("dim", _io.glyph("·"))
            text = f"  {mark} {pad_width(label, pad)}"
            if item.value:
                text += st("cyan", pad_width(item.value, vpad))
            if item.hint_key:
                text += st("dim", translate(item.hint_key))
            rows.append(text.rstrip())
        if not rows:
            continue
        lines.append(st("bold", f"  {translate(sec.title_key)}"))
        lines.extend(rows)
        lines.append("")
    if footer:
        lines.append(footer)
    return lines
