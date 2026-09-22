#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_rules —— 持久授权规则：`allow` / `deny` + 作用域（项目本地 / 项目 / 用户）

为什么需要（用户的真实痛点）：`/permission rules` 只改**本次会话**的授权，关掉终端就没了。
于是"我知道这个工具要问十次"这件事，每次开新会话都得重来；反过来想**锁死**某个目录
（"这个仓库里别碰 .env"）此前根本没有表达方式 —— 只能靠沙箱与敏感文件清单那些粗粒度开关。

规则长这样（纯数据）：

```
{"tool": "terminal_exec", "pattern": "pytest:*", "action": "allow"}
{"tool": "file_write",    "pattern": "docs/",    "action": "deny"}
{"tool": "file_write",    "pattern": "",         "action": "allow"}   ← 该工具任意用法
```

三条纪律（都写在这里，因为它们是安全语义，不该散在实现里）：
1. **deny 永远赢**：同一目标既有 allow 又有 deny 时按 deny 处理。放宽要人明确做决定，
   收紧不需要 —— 反过来会让人以为"我明明拒了"。
2. **作用域优先级 本地 > 项目 > 用户**：越靠近当前仓库的规则越具体；同层冲突按 deny。
3. **外发工具只能 deny，不能 allow**：`api_post` 这类工具的"授权给谁"必须用
   `egress_allowlist` 指定目的地，规则里的 allow 会被丢弃并给出警告 —— 按工具名放行
   等于把出口整个打开（与 session grant 拒绝外发工具是同一条理由）。

纯函数 + 三个文件读写（读坏就当空，不炸），所以匹配与优先级都能穷举断言。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = ["Rule", "RULES_FILENAME", "LOCAL_RULES_FILENAME", "SCOPES",
           "parse_rule", "rule_matches", "match_rule", "load_rules",
           "load_rules_file", "save_rules", "describe_rule", "shadowed_rules",
           "rules_path", "suggest_rule", "parse_persist_answer"]

# 文件名与作用域（顺序 = 优先级，前面的赢）
RULES_FILENAME = "permissions.json"
LOCAL_RULES_FILENAME = "permissions.local.json"
SCOPES: Tuple[str, ...] = ("local", "project", "user")
ALLOW, DENY = "allow", "deny"

# 不能靠规则放行的工具（"授权给谁"≠"授权做什么"）：只允许被 deny
EGRESS_TOOL_PREFIXES = ("api_", "browser_", "notify_", "image_")
EGRESS_TOOL_NAMES = frozenset(("api_get", "api_post", "browser_open",
                               "browser_navigate", "notify_send", "image_generate",
                               "search", "web_fetch"))


def is_egress_tool(tool: str) -> bool:
    """是不是"会把数据发出去"的工具（只能被 deny，不能被 allow）。"""
    n = str(tool or "")
    return n in EGRESS_TOOL_NAMES or n.startswith(EGRESS_TOOL_PREFIXES)


class Rule:
    """一条规则：`工具 + 匹配模式 + 动作 + 作用域/来源文件`。

    `pattern` 的语义按工具类别：
    - 命令类（terminal_exec / code_execute…）：**命令前缀**匹配，`:*` 结尾表示前缀
      （`pytest:*` 命中 `pytest -q`，也命中 `pytest`）；不带 `:*` 则要求完全相同；
    - 文件类（file_write / file_read…）：**路径前缀**匹配，比较时统一成正斜杠相对路径；
    - 其它工具：留空表示"该工具任意用法"；非空则要求参数里有任意字段等于它（保守）。
    """

    def __init__(self, tool: str, pattern: str = "", action: str = ALLOW,
                 scope: str = "local", source: str = "") -> None:
        self.tool = str(tool or "").strip()
        self.pattern = str(pattern or "").strip()
        self.action = DENY if str(action).strip().lower() == DENY else ALLOW
        self.scope = scope if scope in SCOPES else "local"
        self.source = str(source or "")

    def as_dict(self) -> Dict[str, str]:
        return {"tool": self.tool, "pattern": self.pattern, "action": self.action}

    def __repr__(self) -> str:
        pat = self.pattern or "*"
        return f"Rule({self.action} {self.tool}:{pat} @{self.scope})"


def _norm_path(value: str) -> str:
    """路径归一：反斜杠→正斜杠、去掉开头的 ./、统一小写盘符。"""
    s = str(value or "").replace("\\", "/").strip()
    while s.startswith("./"):
        s = s[2:]
    return s


def _command_matches(command: str, pattern: str) -> bool:
    """命令匹配：`pytest:*` = 前缀；否则要求完全相同（保守，别让 `rm` 命中 `rmdir`）。"""
    cmd = " ".join(str(command or "").split())
    pat = " ".join(str(pattern or "").split())
    if not pat:
        return True
    if pat.endswith(":*"):
        head = pat[:-2].strip()
        return cmd == head or cmd.startswith(head + " ")
    return cmd == pat


def rule_matches(rule: Rule, tool: str, params: Dict[str, Any]) -> bool:
    """规则是否命中这次调用（纯函数；所有匹配细节都在这里）。"""
    if not rule:
        return False
    if rule.tool not in ("*", str(tool or "")):
        return False
    params = params if isinstance(params, dict) else {}
    pat = rule.pattern
    if not pat:
        return True                                  # 该工具任意用法
    cmd = params.get("command") or params.get("code")
    if isinstance(cmd, str) and cmd:
        return _command_matches(cmd, pat)
    path = params.get("path") or params.get("dest") or params.get("target")
    if isinstance(path, str) and path:
        return _norm_path(path).startswith(_norm_path(pat))
    for key in ("query", "url", "pattern"):
        val = params.get(key)
        if isinstance(val, str) and val:
            return _command_matches(val, pat)
    return False                                     # 有模式但参数里没东西可比 → 不命中


def suggest_rule(tool: str, params: Dict[str, Any]) -> str:
    """从这次调用**猜一个**最小模式（给"顺手记成规则"用）。

    为什么是"最小"：规则是长期的，默认给太宽等于把整个工具放开。命令类取第一个词 +
    `:*`（`pytest -q --tb=short` → `pytest:*`）；文件类取所在目录（`ace/ui/x.py` →
    `ace/ui/`，避免把单个文件名记成规则）；其余工具给空前缀（该工具任意用法，用户自己改）。
    """
    p = params if isinstance(params, dict) else {}
    tool = str(tool or "")
    if tool in ("terminal_exec", "code_execute") or "command" in p or "code" in p:
        cmd = " ".join(str(p.get("command") or p.get("code") or "").split())
        if cmd:
            head = cmd.split(" ")[0]
            return f"{head}:*" if len(cmd.split(" ")) > 1 else head
        return ""
    path = p.get("path") or p.get("dest") or p.get("target")
    if isinstance(path, str) and path:
        norm = _norm_path(path)
        if "/" in norm:
            return norm.rsplit("/", 1)[0] + "/"
        return norm
    return ""


def match_rule(rules: Sequence[Rule], tool: str, params: Dict[str, Any]
               ) -> Optional[Rule]:
    """取生效的那条规则：**deny 永远赢**，同级之间按 `local > project > user`。

    返回 None = 没有规则命中（走原来的审批流程）。
    """
    hits = [r for r in (rules or []) if rule_matches(r, tool, params)]
    if not hits:
        return None
    denies = [r for r in hits if r.action == DENY]
    if denies:
        for scope in SCOPES:
            for r in denies:
                if r.scope == scope:
                    return r
        return denies[0]
    for scope in SCOPES:
        for r in hits:
            if r.scope == scope:
                return r
    return hits[0]


def rules_path(scope: str, project_root: str = ".",
               home: Optional[str] = None) -> str:
    """某个作用域的规则文件路径。"""
    home = home or os.path.expanduser("~")
    if scope == "user":
        return os.path.join(home, ".ace", RULES_FILENAME)
    name = LOCAL_RULES_FILENAME if scope == "local" else RULES_FILENAME
    return os.path.join(os.path.abspath(project_root), ".ace", name)


def parse_rule(raw: Any, scope: str = "local", source: str = ""
               ) -> Tuple[Optional[Rule], str]:
    """一条 JSON 记录 → `(Rule, 警告)`；非法记录返回 (None, 原因) —— 不静默丢。"""
    if not isinstance(raw, dict):
        return None, f"不是对象: {type(raw).__name__}"
    tool = str(raw.get("tool") or "").strip()
    if not tool:
        return None, "缺 tool"
    action = str(raw.get("action") or ALLOW).strip().lower()
    if action not in (ALLOW, DENY):
        return None, f"action 只能是 allow/deny: {action}"
    rule = Rule(tool, str(raw.get("pattern") or ""), action, scope, source)
    if rule.action == ALLOW and is_egress_tool(rule.tool):
        # 外发工具的"授权"必须指定目的地（egress_allowlist），不能按工具名放过
        return None, (f"{rule.tool} 是把数据发出去的工具，只允许 deny；"
                      f"要免问请用配置 egress_allowlist 指定域名")
    return rule, ""


def load_rules_file(path: str, scope: str) -> Tuple[List[Rule], List[str]]:
    """读一个规则文件 → `(规则列表, 警告列表)`。文件不存在/读坏都返回空 + 警告。"""
    out: List[Rule] = []
    warns: List[str] = []
    if not path or not os.path.isfile(path):
        return out, warns
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001 —— 规则读不出来不该让会话起不来
        return out, [f"{path}: 读不动（{type(e).__name__}）"]
    items = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return out, [f"{path}: 结构不是规则数组"]
    for i, raw in enumerate(items):
        rule, why = parse_rule(raw, scope, path)
        if rule is None:
            warns.append(f"{path}[{i}]: {why}")
        else:
            out.append(rule)
    return out, warns


def load_rules(project_root: str = ".", home: Optional[str] = None,
               scopes: Sequence[str] = SCOPES) -> Tuple[List[Rule], List[str]]:
    """加载三个作用域的规则（按优先级顺序拼接）→ `(规则, 警告)`。

    同一个文件被两个作用域指到（例如 `home == project_root`）时只读一次 ——
    否则同一条规则会出现两遍，`/rules` 看起来像重复添加了。
    """
    rules: List[Rule] = []
    warns: List[str] = []
    seen: set = set()
    for scope in scopes:
        path = rules_path(scope, project_root, home)
        key = os.path.abspath(path)
        if key in seen:
            continue
        seen.add(key)
        r, w = load_rules_file(path, scope)
        rules.extend(r)
        warns.extend(w)
    return rules, warns


def save_rules(rules: Sequence[Rule], path: str) -> bool:
    """写回某个作用域的规则文件（只写该作用域自己的条目）。"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        payload = {"version": 1, "rules": [r.as_dict() for r in rules or []]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:  # noqa: BLE001 —— 写不进去由调用方如实报告
        return False


def describe_rule(rule: Rule) -> str:
    """规则 → 一句人话（给 `/rules` 用；不含 i18n，调用方自己套）。"""
    pat = rule.pattern or "*"
    if rule.tool.startswith(("terminal", "code_")):
        what = f"命令以 {pat[:-2]!r} 开头" if pat.endswith(":*") else f"命令恰为 {pat!r}"
    elif rule.pattern:
        what = f"路径在 {pat!r} 下"
    else:
        what = "任意用法"
    verb = "允许免问" if rule.action == ALLOW else "直接拒绝"
    return f"{rule.tool}: {verb}（{what}）"


def parse_persist_answer(text: str, suggested: str,
                         default_scope: str = "local"
                         ) -> Tuple[Optional[Rule], str]:
    """解析"顺手记成规则"的回答 → `(Rule 或 None, 提示)`。

    接受的写法（**回车 = 不记**，最省事的路径永远是不做额外的事）：
      `y`                     → 用建议的模式 + 默认作用域
      `y <模式>`               → 自定义模式
      `y <模式> <作用域>`       → 自定义模式与作用域
      `!`                     → 记成 deny（用建议的模式）
      `! <模式> <作用域>`       → 自定义的 deny
    写法不对时返回 (None, 原因) —— 调用方如实说出来，而不是默默不记。
    """
    raw = str(text or "").strip()
    if not raw:
        return None, ""
    parts = raw.split()
    head = parts[0].lower()
    action = ALLOW
    if head.startswith("!"):
        action = DENY
        parts[0] = head[1:]
        head = parts[0] or "y"
    if head not in ("y", "yes", "记", "是"):
        return None, f"unrecognized:{raw[:20]}"
    rest = [p for p in parts[1:] if p]
    pattern = rest[0] if rest else suggested
    scope = rest[1] if len(rest) > 1 else default_scope
    if scope not in SCOPES:
        return None, f"bad_scope:{scope}"
    # 这里**不**走 parse_rule：工具名由调用方补（他知道是哪个工具在请求），
    # 所以不能因为"缺 tool"把一条合法回答判死（探针里当场踩到过）。
    return Rule("", pattern, action, scope), ""


def shadowed_rules(rules: Sequence[Rule]) -> List[Tuple[int, int]]:
    """找出被遮挡的规则：`[(被遮挡的下标, 遮挡它的下标)]`。

    典型情形：用户先加了 `docs/:allow`，又加了更宽的 `:deny` —— 前者永远轮不到。
    提交后提示一句，免得他以为"我明明放行了却没生效"。
    """
    out: List[Tuple[int, int]] = []
    for i, a in enumerate(rules or []):
        for j, b in enumerate(rules or []):
            if i == j or a.tool != b.tool:
                continue
            # 更宽的模式（空前缀）且动作不同 → 窄的那条可能被挡
            if b.pattern == "" and a.pattern and b.action == DENY and a.action == ALLOW:
                out.append((i, j))
            elif (b.pattern == a.pattern and b.action == DENY and a.action == ALLOW):
                out.append((i, j))
    return out
