#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_cards —— 工具调用卡片渲染（纯文本行，终端逐行滚动输出友好）

对标 OpenClaw 的 ToolExecutionComponent：一次工具调用渲染成一张卡片 ——
标题行（符号 + 工具名 + 状态标记 + 可选耗时）+ 参数摘要行 + 输出区
（默认折叠，只保留前 max_lines 行 + 一行折叠提示）。返回 List[str] 纯文本行，
直接 print("\\n".join(...)) 即可，不是 TUI 浮层 —— ACE 的 CLI 是逐行打印的。

设计决策：
1. 纯 stdlib 零依赖；中文注释；4 空格缩进。
2. 符号默认用 ASCII（TOOL_GLYPH）而不是 emoji（TOOL_EMOJI 保留作跨平台备选）：
   ACE 的 CLI 之前因 Windows GBK 控制台乱码去掉了 emoji，卡片标题沿用 ASCII 符号。
   tool_card(..., glyphs=TOOL_EMOJI) 可切回 emoji 版。
3. 三态底色：status_mark 返回 (标记, 颜色名) 元组，颜色名是 ANSI 名
   （'green'/'red'/'yellow'/'blue'），由调用方上色 —— 卡片本身保持纯文本，
   便于测试、日志落盘与管道传输。ANSI 表与 colorize() 是给调用方的现成工具。

用法示例：
    from ui.ace_cards import tool_card, status_mark, colorize
    for ln in tool_card("terminal_exec", "SUCCESS",
                        params={"command": "ls -la"},
                        output="drwxr-xr-x  foo", elapsed=0.32):
        print(ln)
"""

import json
from typing import Dict, List, Optional, Tuple

from ui.ace_text import truncate_width

__all__ = [
    "TOOL_EMOJI", "TOOL_GLYPH", "GLYPH_FALLBACK", "ANSI",
    "MESSAGE_PREFIX", "message_prefix", "group_tool_runs", "thinking_block",
    "tool_card", "status_mark", "collapse_lines", "colorize",
]

# 消息种类前缀：一眼分清"谁在说话"。之前只有用户行有符号（❯），助手与工具卡片
# 全靠颜色区分 —— 颜色在重定向到文件、或色弱终端里全丢了，符号不会。
MESSAGE_PREFIX: Dict[str, str] = {
    "user": "❯", "assistant": "◈", "tool": "⚙", "notice": "·",
    "error": "✗", "thinking": "…", "done": "✓",
}


def message_prefix(kind: str) -> str:
    """取消息前缀；未知种类退化为空串（宁可没有前缀，也不要猜一个符号）。"""
    return MESSAGE_PREFIX.get(str(kind or "").lower(), "")


# ============================================================
# 符号表
# ============================================================

# emoji 版（对照 OpenClaw 的图标方案；Windows GBK 控制台慎用，默认不启用）。
# 覆盖 tools/registry.py 的 TOOL_SPECS 全部 41 个名字（含两个未暴露的高危占位）。
TOOL_EMOJI: Dict[str, str] = {
    "terminal_exec": "⚡", "terminal_view": "👁", "file_write": "📝",
    "file_read": "📖", "file_delete": "🗑", "file_move": "📦",
    "code_execute": "🐍", "search": "🔍", "search_read": "🔍",
    "kb_search": "📚", "kb_add": "📚", "kb_list": "📚",
    "skill_load": "🎓", "skill_list": "🎓", "subagent": "🤖",
    "goal_create": "🎯", "goal_update": "🎯", "goal_status": "🎯",
    "api_get": "🌐", "api_post": "🌐",
    "browser_navigate": "🧭", "browser_click": "🖱", "browser_type": "⌨",
    "db_query": "🗄", "db_write": "🗄", "image_generate": "🖼",
    "notify_send": "🔔", "parse_document": "📄", "open_file": "🔗",
    "edit_file": "✏", "grep": "🔎", "glob": "📂", "math_calc": "🧮",
    "datetime_now": "🕐", "plan_propose": "📋", "request_permission": "🔑",
    "str_replace": "🔄", "todo_write": "☑",
    # 补齐 registry 里其余工具（browser_screenshot / browser_open / 高危占位）
    "browser_screenshot": "📸", "browser_open": "🌐",
    "terminal_dangerous": "☠", "db_drop": "💥",
}

# ASCII 符号版（默认）。按类别分组，同类工具共用符号，规避 Windows 乱码：
#   ">" 终端执行   "v" 终端查看   "+" 写文件   "r" 读文件   "x" 删除   "~" 移动
#   "p" 代码执行   "?" 搜索/检索  "k" 知识库    "s" 技能     "g" 目标
#   "*" 子代理/文件名匹配  "w" 网络请求  "b" 浏览器  "d" 数据库  "i" 图片
#   "!" 通知/授权  "@" 文档解析   "o" 打开     "e" 编辑     "=" 计算
#   "t" 时间      "#" 计划       "%" 片段替换
TOOL_GLYPH: Dict[str, str] = {
    "terminal_exec": ">", "terminal_view": "v",
    "file_write": "+", "file_read": "r", "file_delete": "x", "file_move": "~",
    "code_execute": "p",
    "search": "?", "search_read": "?",
    "kb_search": "k", "kb_add": "k", "kb_list": "k",
    "skill_load": "s", "skill_list": "s",
    "subagent": "*",
    "goal_create": "g", "goal_update": "g", "goal_status": "g",
    "api_get": "w", "api_post": "w",
    "browser_navigate": "b", "browser_click": "b", "browser_type": "b",
    "browser_screenshot": "b", "browser_open": "b",
    "db_query": "d", "db_write": "d",
    "image_generate": "i", "notify_send": "!",
    "parse_document": "@", "open_file": "o", "edit_file": "e",
    "grep": "?", "glob": "*",
    "math_calc": "=", "datetime_now": "t",
    "plan_propose": "#", "request_permission": "!",
    "str_replace": "%", "todo_write": "c",
    "terminal_dangerous": "!", "db_drop": "x",
}
GLYPH_FALLBACK: str = "*"  # 未知工具的回退符号

# 硬错误码（与 ai_code.py 的 ERROR_STATUSES 一致）：执行被拒，标红 ✗
HARD_ERRORS = frozenset({
    "403", "FORMAT_ERROR", "TOOL_BANNED", "GUARD_VIOLATION",
    "BAIT_TRIGGERED", "AST_FAILED",
})

# ============================================================
# ANSI 上色（调用方可选；卡片本身是纯文本）
# ============================================================

ANSI: Dict[str, str] = {
    "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m",
    "blue": "\033[34m", "dim": "\033[2m", "reset": "\033[0m",
}


def colorize(text: str, color: str = "") -> str:
    """给文本包 ANSI 色码（终端不支持 ANSI 时由调用方自行剥离）。

    color 取 'green'/'red'/'yellow'/'blue'/'dim'；空串原样返回。
    用法：print(colorize("✓ 成功", "green"))。
    """
    code = ANSI.get(color)
    if not code:
        return text
    return f"{code}{text}{ANSI['reset']}"


# ============================================================
# 状态标记
# ============================================================

def status_mark(status: str) -> Tuple[str, str]:
    """状态 → (标记, ANSI 颜色名)。

    - SUCCESS        → ("✓", "green")   成功
    - pending        → ("◌", "blue")    执行中（卡片先行占位）
    - 硬错误码        → ("✗", "red")     被拒/格式错/守卫拦下等
    - 其他（500 等）  → ("⚠", "yellow")  一般失败

    返回纯 (mark, color) 元组：标记由卡片标题直接用，颜色由调用方上色。
    大小写不敏感（"success"/"PENDING" 同样识别）。
    """
    s = str(status).strip().upper()
    if s == "SUCCESS":
        return "✓", "green"
    if s == "PENDING":
        return "◌", "blue"
    if s in HARD_ERRORS:
        return "✗", "red"
    return "⚠", "yellow"


# ============================================================
# 折叠与截断
# ============================================================

def collapse_lines(lines: List[str], max_lines: int) -> List[str]:
    """折叠长输出：保留前 max_lines 行，其余替换为一行折叠提示。

    纯函数、可单测。不超限时原样返回；空输入返回空列表。

    >>> collapse_lines(["a"] * 10, 4)
    ['a', 'a', 'a', 'a', '… 已折叠 6 行 (用 /expand 看完整)']
    """
    lines = list(lines)
    max_lines = int(max_lines)
    if len(lines) <= max_lines:
        return lines
    hidden = len(lines) - max_lines
    return lines[:max_lines] + [f"… 已折叠 {hidden} 行 (用 /expand 看完整)"]


PARAM_LIMIT = 80    # 参数摘要单行上限
MESSAGE_LIMIT = 60  # 失败原因上限（与 ai_code.py 的截断一致）


def _truncate(text: str, limit: int) -> str:
    """按**显示宽度**截断到 limit 列，超长尾部替换为 '…'。

    以前这里数的是 `len()`（码点）：中文参数/失败原因只按字数算，实际占两倍列宽，
    卡片尾巴会顶出终端宽度、把后面的对齐全部挤歪。宽度口径统一到 ui.ace_text。
    """
    return truncate_width(text, limit)


def _format_params(tool: str, params: Dict) -> str:
    """参数摘要：终端命令渲染成 '$ cmd'；其余渲染成 'k=v k=v' 单行。

    多行值（如 file_write 的 content）先折叠空白再截断，保证只占一行。
    """
    if tool in ("terminal_exec", "terminal_view") and "command" in params:
        return _truncate("$ " + str(params["command"]).strip(), PARAM_LIMIT)
    parts: List[str] = []
    for k, v in params.items():
        if isinstance(v, (dict, list, tuple)):
            v = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        elif v is None:
            v = "None"
        else:
            v = str(v)
        v = " ".join(v.split())  # 折叠换行/连续空白 → 单行
        parts.append(f"{k}={v}")
    return _truncate(" ".join(parts), PARAM_LIMIT)


# ============================================================
# 整卡渲染
# ============================================================

def tool_card(tool: str, status: str, params: Optional[Dict] = None,
              message: str = "", output: str = "",
              elapsed: float = 0.0, collapsed: bool = True,
              max_lines: int = 12, exit_code: Optional[int] = None,
              diff: str = "",
              glyphs: Optional[Dict[str, str]] = None) -> List[str]:
    """渲染一张工具调用卡片（纯文本行，可直接 print）。

    - tool:      工具名（查 glyphs 符号表，未知用 GLYPH_FALLBACK）
    - status:    "SUCCESS" / 错误码（"403" 等）/ "pending"
    - params:    参数 dict（渲染为一行摘要，截断 80 字符）
    - message:   失败原因（截断 60 字符）
    - output:    工具输出（collapsed 时只留前 max_lines 行 + 折叠提示）
    - elapsed:   耗时秒数（> 0 时在标题尾显示 "· 0.32s"）
    - exit_code: 进程退出码（命令类工具；None = 不显示）。非 0 也照样显示 ——
                 "命令跑完了"与"命令成功"是两件事，把 0/非 0 摆出来由人判断
    - diff:      unified diff 文本（写入类工具）。标题挂 `+3 -1` 统计，正文按
                 `+`/`-` 逐行展开（颜色由调用方按 ui.ace_diff.color_name 上）
    - collapsed: 是否折叠输出；False 则输出全部行
    - glyphs:    符号表，默认 TOOL_GLYPH（ASCII，Windows 安全）；
                 传 TOOL_EMOJI 切回 emoji 版

    返回形如：
      ["  > terminal_exec ✓ [SUCCESS] · 0.32s · exit 0",
       "    $ ls -la",                    # 参数摘要（dim，调用方可上色）
       "    drwxr-xr-x ...",              # output 前 N 行（缩进 4 空格）
       "    … 已折叠 40 行 (用 /expand 看完整)"]  # 折叠提示
    """
    glyph = (glyphs or TOOL_GLYPH).get(tool, GLYPH_FALLBACK)
    mark, _color = status_mark(status)
    title = f"  {glyph} {tool} {mark} [{status}]"
    if isinstance(elapsed, (int, float)) and elapsed > 0:
        title += f" · {elapsed:.2f}s"
    if exit_code is not None:
        title += f" · exit {int(exit_code)}"
    _stat = _diff_stat(diff)
    if _stat:
        title += f" · {_stat}"
    lines: List[str] = [title]
    if params:
        lines.append("    " + _format_params(tool, params))
    if message:
        lines.append(f"    {mark} {_truncate(str(message), MESSAGE_LIMIT)}")
    if output:
        out_lines = output.splitlines() if isinstance(output, str) else [str(output)]
        if collapsed:
            out_lines = collapse_lines(out_lines, max_lines)
        lines.extend("    " + ln for ln in out_lines)
    if diff:
        d_lines = [ln for ln in str(diff).splitlines() if ln.strip()]
        if collapsed:
            d_lines = collapse_lines(d_lines, max_lines)
        lines.extend("    " + ln for ln in d_lines)
    return lines


def _diff_stat(diff: str) -> str:
    """`+3 -1` 统计（没有改动就不显示）。import 放在函数里，避免卡片模块开局就拉 diff。"""
    if not diff:
        return ""
    from ui.ace_diff import stat_text
    return stat_text(diff)


def group_tool_runs(tools: List[Tuple[str, str, float, Optional[int]]]
                    ) -> List[Dict[str, object]]:
    """把**连续同名**工具调用合并成一段：`file_read ×3 ✓`

    为什么合并而不是逐个列：模型读三个文件时，时间线上写着 `file_read ✓ ·
    file_read ✓ · file_read ✓` —— 三份重复信息，把"这轮其实只做了一件事"讲了三遍。
    合并成 `file_read ×3 ✓` 之后，剩下的位置才留给真正不同的动作。

    只合并**连续**的：`read · write · read` 里两次 read 中间隔着一次写，
    合成一段会把顺序讲错。

    每段返回 `{tool, count, ok, fail, secs, last_status, exit_codes}`，
    顺序按首次出现；`last_status` 用于取状态标记（合并段是按最后一次调用定性的）。
    """
    runs: List[Dict[str, object]] = []
    for name, status, elapsed, rc in tools or []:
        _name, _status = str(name or ""), str(status)
        _secs = float(elapsed or 0.0)
        _ok = 1 if _status.upper() == "SUCCESS" else 0
        if runs and runs[-1]["tool"] == _name:
            cur = runs[-1]
            cur["count"] = int(cur["count"]) + 1
            cur["ok"] = int(cur["ok"]) + _ok
            cur["fail"] = int(cur["fail"]) + (1 - _ok)
            cur["secs"] = float(cur["secs"]) + _secs
            cur["last_status"] = _status
            if rc not in (None, 0):
                _codes = cur["exit_codes"]
                if isinstance(_codes, list):
                    _codes.append(rc)
            continue
        runs.append({"tool": _name, "count": 1, "ok": _ok, "fail": 1 - _ok,
                     "secs": _secs, "last_status": _status,
                     "exit_codes": [] if rc in (None, 0) else [rc]})
    return runs


def thinking_block(lines: List[str], max_lines: int = 6,
                   total: Optional[int] = None) -> List[str]:
    """思考过程框：`┌ 思考 (N 行)` / `│ …` / `└─`。

    为什么给框而不是逐行 `· 文本`：逐行打散之后，"这是模型的内部推理、不是回复"
    这件事只靠暗色表达；框把边界画出来，用户一眼知道框外的才是要读的东西。
    超过 `max_lines` 就折叠并说明总共多少行 —— 内部推理不该占满屏幕。
    """
    body = [str(x) for x in (lines or []) if str(x).strip()]
    total = len(body) if total is None else int(total)
    shown, extra = body[:max(1, int(max_lines))], max(0, total - len(body[:max(1, int(max_lines))]))
    head = f"┌ 思考 ({total} 行)"
    out = [head]
    out.extend("│ " + ln for ln in shown)
    if extra > 0:
        out.append(f"│ … 其余 {extra} 行已折叠（/thinking 控制显示）")
    out.append("└─")
    return out


# ============================================================
# 手工演示（python -m ui.ace_cards 直接看效果）
# ============================================================

if __name__ == "__main__":
    import sys

    # Windows GBK 控制台先切 UTF-8，保证中文/符号不花屏
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    demo = [
        tool_card("terminal_exec", "SUCCESS",
                  params={"command": "ls -la"},
                  output="drwxr-xr-x  .ace_kb\n-rw-r--r--  ace_cards.py\n"
                         + "\n".join(f"输出行 {i}" for i in range(20)),
                  elapsed=0.32),
        tool_card("file_write", "403",
                  params={"path": "C:\\tmp\\secret.txt",
                          "content": "x" * 200},
                  message="权限不足：写入路径超出项目根，已拦截", elapsed=0.01),
        tool_card("subagent", "pending", params={"prompt": "审查这段代码"}),
    ]
    for card in demo:
        _status = card[0].split("[", 1)[1].split("]", 1)[0]  # 从标题行取 [状态]
        _mark, _col = status_mark(_status)
        for ln in card:
            print(colorize(ln, _col))
        print()
