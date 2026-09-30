#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_agents —— agent 预设 / 自定义模式（`ROADMAP` §4 WP-6，立项卡
`docs/design/WP-6-AGENT-PRESETS.md`）

把 `CONFIRM_TOOLS` 从**全局常量**变成 **per-agent 权限规则**：`agents/<name>.md`
的 frontmatter（照 kilocode）：

```
---
name: reviewer
description: 只读审查
permission: {read: allow, edit: ask, webfetch: ask, bash: deny}
---
你是审查者……
```

## 三条纪律（本模块的全部内容就是这三条）

1. **S-1 硬约束：预设只能比全局更严或相等，绝不更松。**
   判定**复用 DL-04 的同一个判定处** —— `tools.status.assert_no_permission_relaxation`
   / `RelaxationForbidden`（与"学习产物不许放宽"共用一个异常类与一个文件），
   **不新开第二套**。放宽只能是人的动作：预设文件**不是**放宽入口。
2. **不新增第二套权限模型**：四维（`read`/`edit`/`webfetch`/`bash`）只是把**既有**
   `tools/registry.ToolSpec` 投影成四个"问题"，取值仍落到既有的 `CONFIRM_TOOLS`
   与权限档上；预设只会往**并集**里加确认、往**拒绝**里加东西，不会做任何差集。
3. **不静默**（HL-03②）：认不出的**字段** → 如实 warning，不阻塞启动；认不出的
   **取值**，或比全局更松的取值 → **红**（`RelaxationForbidden`），不是 warning。

## "字段"与"取值"为什么区别对待

- 认不出的**字段**（打错的顶层键、打错的维度名）最多让"这条预设没起作用"，
  结果仍不松于全局（该维度沿用全局姿态）⇒ 不阻塞启动，但**必须 warning**。
- 认不出的**取值**（`bash: denyy`）无法证明它不松 —— 放行等于"默认不问人"，
  方向朝松且静默 ⇒ 与 `allow` 一样**当场红**。判据在
  `tools.status.permission_relaxes`（认不出一律按"更松"算）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.status import (PERMISSION_ACTIONS,  # noqa: F401 —— 再导出/校验用
                          RelaxationForbidden,  # noqa: F401 —— 再导出：调用方只从一处 catch
                          assert_no_permission_relaxation)

__all__ = [
    "DIMENSIONS", "AGENTS_DIRNAME", "EVENT_AGENT_PRESET",
    "AgentPreset", "PresetScan", "PresetSwitch", "AgentPresetRegistry",
    "parse_agent_text", "scan_agents", "agent_dirs",
    "dimension_of", "global_baseline", "resolve_permission",
    "preset_gate", "effective_confirm_tools", "effective_denied_tools",
    "make_switch_event", "emit_switch", "RelaxationForbidden",
]

#: 四维（与立项卡 §一 的 frontmatter 一致）。顺序即文档顺序。
DIMENSIONS: Tuple[str, ...] = ("read", "edit", "webfetch", "bash")

AGENTS_DIRNAME = "agents"
MAX_PRESET_BYTES = 64 * 1024
#: 预设切换的**引擎侧事件**类型（登记在 `core/ace_events.py`，与 WP-0 同一个通道）。
EVENT_AGENT_PRESET = "agent_preset"

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-\u4e00-\u9fff]{1,60}$")
_TOP_KEYS = ("name", "description", "permission")
_INLINE_MAP = re.compile(r"^\{(.*)\}$", re.S)


# ============================================================
# ① frontmatter 解析（零依赖：不引入 YAML —— 与 core/ace_commands.py 同一姿态）
# ============================================================

def _parse_inline_map(text: str) -> Optional[Dict[str, str]]:
    """`{read: allow, edit: ask}` → dict；认不出返回 None。"""
    m = _INLINE_MAP.match((text or "").strip())
    if not m:
        return None
    out: Dict[str, str] = {}
    for part in m.group(1).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            return None
        k, _, v = part.partition(":")
        out[k.strip().lower()] = v.strip().strip('"').strip("'").lower()
    return out


def _parse_permission_block(lines: Sequence[str], warnings: List[str],
                            where: str) -> Optional[Dict[str, str]]:
    """解析 `permission:` 之后**缩进**的块映射（每行 `维度: 取值`）。"""
    out: Dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            warnings.append(f"{where}: permission 里认不出的一行 {line!r}（已忽略）")
            continue
        k, _, v = line.partition(":")
        out[k.strip().lower()] = v.strip().strip('"').strip("'").lower()
    return out


@dataclass
class AgentPreset:
    """一个 agent 预设。`permission` 是**原始解析值**（可能含认不出的项）。

    原始值原样保留：`resolve_permission` 才是 S-1 的判定处 —— 扫描阶段不判，
    因为"扫到就抛"会变成"一个坏预设文件让整个会话起不来"（立项卡：不阻塞启动）。
    """
    name: str
    description: str = ""
    permission: Dict[str, str] = field(default_factory=dict)
    body: str = ""
    path: str = ""
    source: str = "project"          # project / project-hidden / user
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "permission": dict(self.permission), "path": self.path,
                "source": self.source, "warnings": list(self.warnings)}


def parse_agent_text(text: str, *, name: str = "", path: str = "",
                     source: str = "project") -> Optional[AgentPreset]:
    """Markdown 文本 → `AgentPreset`（纯函数，可单测）。

    没有 frontmatter / 没有名字 / 名字不合法 → 返回 None（调用方给一条 warning）。
    **本函数永不抛异常**：坏文件不该让会话起不来。
    """
    warnings: List[str] = []
    body = str(text or "")
    fields: Dict[str, str] = {}
    m = _FRONTMATTER.match(body)
    if not m:
        # 没有 frontmatter 就不是预设（与 `core/ace_commands.py` 的"没 frontmatter 也算命令"
        # 刻意不同：命令的正文自己就是提示词，而预设的**全部内容**就是 frontmatter
        # 那几行权限，没有它这个文件没有任何可执行的含义）。
        return None
    if m:
        pending_permission: Optional[List[str]] = None
        for raw in m.group(1).splitlines():
            line = raw.rstrip()
            if pending_permission is not None and (raw[:1].isspace() or not line.strip()):
                pending_permission.append(line)
                continue
            pending_permission = None
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                warnings.append(f"frontmatter 认不出的一行（已忽略）: {stripped!r}")
                continue
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            if key not in _TOP_KEYS:
                # 认不出的**字段**：warning，不阻塞（见模块 docstring 的分工）
                warnings.append(f"frontmatter 认不出的字段 {key!r}（已忽略）")
                continue
            if key == "permission" and not value.strip():
                pending_permission = []
                fields["\x00permission_block"] = ""
                continue
            fields[key] = value.strip().strip('"').strip("'")
        if "\x00permission_block" in fields:
            fields.pop("\x00permission_block")
            fields["permission"] = "\n".join(pending_permission or [])
        body = body[m.end():]
    else:
        warnings.append("没有 frontmatter（--- 块）：预设不可用")

    raw_name = str(fields.get("name") or name or "").strip()
    if not raw_name:
        return None
    if not str(fields.get("name") or "").strip():
        # 与 `/命令` 同姿态：文件名兜底。**但要说出来** —— 静默改名会让人
        # 在 `/agent` 里看到一个自己没写过的名字。
        warnings.append(f"frontmatter 没有 name，用文件名兜底为 {raw_name!r}")
    if not _NAME_RE.match(raw_name):
        return None

    permission: Dict[str, str] = {}
    raw_perm = str(fields.get("permission") or "").strip()
    if raw_perm:
        parsed = _parse_inline_map(raw_perm)
        if parsed is None:
            # 缩进块映射：每行 `维度: 取值`
            parsed = _parse_permission_block(raw_perm.splitlines(), warnings, raw_name)
            if not parsed:
                warnings.append(f"{raw_name}: permission 块读不出任何键值（已忽略）")
        for k, v in (parsed or {}).items():
            if k not in DIMENSIONS:
                warnings.append(f"{raw_name}: 认不出的权限维度 {k!r}"
                                f"（合法：{list(DIMENSIONS)}；已忽略）")
                continue
            permission[k] = v
            if v not in PERMISSION_ACTIONS:
                # 取值认不出：这里**只 warning**，真正的拦截在 `resolve_permission`
                # （`permission_relaxes` 对认不出的值一律判"更松" ⇒ 当场 `RelaxationForbidden`）。
                # 两处都要有：warning 让人在扫描阶段就看见，红保证它绝不被静默放行。
                warnings.append(f"{raw_name}: 权限取值 {v!r} 认不出"
                                f"（{k}；合法值 {list(PERMISSION_ACTIONS)}）——"
                                "激活该预设时会被 S-1 拒绝")

    return AgentPreset(
        name=raw_name,
        description=str(fields.get("description") or "").strip()[:200],
        permission=permission,
        body=body.strip(),
        path=str(path),
        source=source,
        warnings=warnings,
    )


# ============================================================
# ② 分层发现：project/agents → project/.ace/agents → ~/.ace/agents
# ============================================================

def agent_dirs(project_root: Any, home: Optional[Any] = None
               ) -> List[Tuple[Path, str]]:
    """分层发现目录（**前面的赢**：项目级覆盖用户级，与 rules 的作用域同向）。"""
    root = Path(project_root).expanduser()
    dirs: List[Tuple[Path, str]] = [(root / AGENTS_DIRNAME, "project"),
                                    (root / ".ace" / AGENTS_DIRNAME, "project-hidden")]
    try:
        home_dir = Path(home).expanduser() if home else Path.home()
    except (RuntimeError, OSError):
        home_dir = None
    if home_dir is not None:
        dirs.append((home_dir / ".ace" / AGENTS_DIRNAME, "user"))
    return dirs


@dataclass
class PresetScan:
    """一次扫描的结果：预设 + **全局**警告（坏文件、缺名字、工具投影未归类…）。

    `warnings` 是给人和测试看的**声明出口**（HL-03②）：不静默。
    """
    presets: List[AgentPreset] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    by_name: Dict[str, AgentPreset] = field(default_factory=dict)

    def names(self) -> List[str]:
        return [p.name for p in self.presets]


def scan_agents(project_root: Any = ".", *, home: Optional[Any] = None,
                dirs: Optional[Sequence[Any]] = None) -> PresetScan:
    """扫描 `agents/*.md`。**永不抛异常**（坏 frontmatter 只 warning）。"""
    scan = PresetScan()
    pairs = ([(Path(d), f"extra{i}") for i, d in enumerate(dirs)]
             if dirs is not None else agent_dirs(project_root, home))
    seen: Dict[str, str] = {}
    for directory, source in pairs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for f in sorted(directory.glob("*.md")):
            try:
                if f.stat().st_size > MAX_PRESET_BYTES:
                    scan.warnings.append(f"{f.name}: 预设文件超过 {MAX_PRESET_BYTES} 字节，已跳过")
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                scan.warnings.append(f"{f.name}: 读不动（{type(e).__name__}），已跳过")
                continue
            preset = parse_agent_text(text, name=f.stem, path=str(f), source=source)
            if preset is None:
                scan.warnings.append(f"{f.name}: 没有合法的 name（或缺 frontmatter），已跳过")
                continue
            scan.warnings.extend(f"{f.name}: {w}" for w in preset.warnings)
            if preset.name in seen:
                # 前面的赢（项目级覆盖用户级）—— 但要说出来，不静默吞掉同名预设
                scan.warnings.append(
                    f"{preset.name}: 同名预设已由 {seen[preset.name]} 提供，"
                    f"忽略 {f}（项目级优先于用户级）")
                continue
            seen[preset.name] = str(f)
            scan.presets.append(preset)
            scan.by_name[preset.name] = preset
    return scan


# ============================================================
# ③ 四维投影：既有 ToolSpec → read/edit/webfetch/bash（**投影**，不是第二套模型）
# ============================================================
#
# 判据只用注册表**已有的标记**（`permission` / `confirm` / `egress` / `control`
# / `expose`），所以新工具进注册表就自动归位，不会与这里漂移。
#
# 只有两条是推不出来的（它们能跑任意代码/起进程，但注册表里只是 `permission=write`），
# 单列在下面并写明理由；`scan` 会对"没归类的暴露工具" warning 提醒（不静默）。

#: 推不出来的那两条：能跑任意代码 / 起子代理。
#: 若按权限推，它们会落到 `edit` —— 那样预设写 `bash: deny`（声明"不跑 shell"）
#: 却仍能跑 python 或起子代理，是**同一个洞**。
DIMENSION_OVERRIDES: Dict[str, str] = {
    "code_execute": "bash",
    "subagent": "bash",
}


def dimension_of(spec: Any) -> str:
    """一个 `ToolSpec` 属于哪一维；`""` = 不归预设管（控制工具 / 未暴露 / high_risk）。"""
    name = str(getattr(spec, "name", "") or "")
    if not name or not bool(getattr(spec, "expose", True)):
        return ""
    if bool(getattr(spec, "control", False)):
        return ""                       # 控制工具（计划/提问/申请权限）不归预设管
    if name in DIMENSION_OVERRIDES:
        return DIMENSION_OVERRIDES[name]
    if bool(getattr(spec, "egress", False)) or name.startswith("browser_"):
        return "webfetch"               # 既有 EGRESS_TOOLS + 整个 browser_* 家族
    if bool(getattr(spec, "confirm", False)):
        return "bash"                   # 要逐次点头的进程/命令类：terminal_exec /
                                        # edit_file（起外部编辑器）/ git_commit_plan …
    perm = str(getattr(spec, "permission", "") or "")
    if perm == "read":
        return "read"
    if perm == "write":
        return "edit"
    return ""


def _exposed_specs() -> List[Any]:
    from tools.registry import TOOL_SPECS
    return [s for s in TOOL_SPECS if bool(getattr(s, "expose", True))]


def projection_warnings() -> List[str]:
    """投影的**漂移守卫**：暴露的工具没归到任何一维 → warning（不静默）。"""
    out: List[str] = []
    for spec in _exposed_specs():
        if dimension_of(spec) == "" and not bool(getattr(spec, "control", False)):
            out.append(f"工具 {spec.name!r} 没被归到四维之一（预设管不到它）")
    names = {getattr(s, "name", "") for s in _exposed_specs()}
    for name in DIMENSION_OVERRIDES:
        if name not in names:
            out.append(f"DIMENSION_OVERRIDES 里的 {name!r} 已不在注册表（投影表漂移了）")
    return out


def _dimension_tools() -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {d: [] for d in DIMENSIONS}
    for spec in _exposed_specs():
        d = dimension_of(spec)
        if d:
            buckets[d].append(str(spec.name))
    return buckets


# ============================================================
# ④ 全局基线 + S-1 判定
# ============================================================

def global_baseline() -> Dict[str, str]:
    """**无预设时**四维的全局姿态，从既有集合**派生**（不写死第二份）。

    派生规则：某一维里有任何工具落在既有的全局闸门里（`CONFIRM_TOOLS` 的逐次确认
    或 `EGRESS_TOOLS` 的外发确认）⇒ 该维全局姿态是 `ask`；否则 `allow`。

    为什么这样派生就够：基线的用途只有一个 —— 回答"预设想写的值算不算放宽"。
    既有闸门已经在问人的维度，预设写 `ask` 是相等、写 `deny` 是更严；既有闸门
    不问人的维度，预设写 `ask`/`deny` 都是更严。基线写死的第二份必然与
    `CONFIRM_TOOLS` 漂移，那正是 S-1 会被绕开的地方。
    """
    from execution_layer import CONFIRM_TOOLS, EGRESS_TOOLS
    gated = set(CONFIRM_TOOLS) | set(EGRESS_TOOLS)
    base = {d: "allow" for d in DIMENSIONS}
    for dim, tools in _dimension_tools().items():
        if any(t in gated for t in tools):
            base[dim] = "ask"
    return base


def resolve_permission(preset: Optional[AgentPreset],
                       baseline: Optional[Dict[str, str]] = None
                       ) -> Dict[str, str]:
    """预设 → **生效的四维姿态**；`None` = 无预设（逐字返回全局基线）。

    S-1 判定就在这里：任何一维比基线更松 ⇒ `assert_no_permission_relaxation`
    当场抛 `RelaxationForbidden`（**红，不是 warning**）。
    """
    base = dict(baseline or global_baseline())
    if preset is None:
        return base
    out: Dict[str, str] = {}
    for dim in DIMENSIONS:
        want = str(preset.permission.get(dim, base[dim]) or "").strip().lower()
        if dim not in preset.permission:
            out[dim] = base[dim]          # 没写 = 沿用全局（相等，不是放宽）
            continue
        assert_no_permission_relaxation(f"permission.{dim}", want, base[dim])
        out[dim] = want
    return out


def preset_gate(preset: Optional[AgentPreset], tool_name: str,
                resolved: Optional[Dict[str, str]] = None) -> Optional[str]:
    """把预设翻译成**对这一次调用**的加严裁决：`"deny"` / `"ask"` / `None`。

    - `None`（含无预设）：预设不加严，调用方走**既有**全局判定（逐字不变）。
    - `"deny"`：这一维被预设关掉 ⇒ 拒绝本次调用。
    - `"ask"`：这一维要人点头**且既有闸门不会问**（`CONFIRM_TOOLS` 里没有它）
      ⇒ 由调用方插一次逐次确认。

    本函数只可能**加严**：`allow` 永远返回 `None`（不碰既有闸门），
    也不构造任何"放行"结果。
    """
    if preset is None:
        return None
    from tools.registry import SPEC_BY_NAME
    spec = SPEC_BY_NAME.get(tool_name)
    if spec is None:
        return None
    dim = dimension_of(spec)
    if not dim:
        return None
    act = (resolved or resolve_permission(preset)).get(dim, "allow")
    if act == "deny":
        return "deny"
    if act == "ask":
        from execution_layer import CONFIRM_TOOLS
        return None if tool_name in CONFIRM_TOOLS else "ask"
    return None


def effective_confirm_tools(preset: Optional[AgentPreset],
                            resolved: Optional[Dict[str, str]] = None) -> set:
    """预设生效后"必须逐次确认"的工具集 = 既有 `CONFIRM_TOOLS` **并上**新增的。

    只做并集（更严）。无预设时**逐字等于** `CONFIRM_TOOLS`。
    """
    from execution_layer import CONFIRM_TOOLS
    out = set(CONFIRM_TOOLS)
    if preset is None:
        return out
    act = resolved or resolve_permission(preset)
    for dim, tools in _dimension_tools().items():
        if act.get(dim) == "ask":
            out.update(tools)
    return out


def effective_denied_tools(preset: Optional[AgentPreset],
                           resolved: Optional[Dict[str, str]] = None) -> set:
    """预设生效后被**关掉**的工具集（四维里值为 `deny` 的那些）。无预设 = 空集。"""
    if preset is None:
        return set()
    act = resolved or resolve_permission(preset)
    out: set = set()
    for dim, tools in _dimension_tools().items():
        if act.get(dim) == "deny":
            out.update(tools)
    return out


# ============================================================
# ⑤ 注册表 + 切换 + 引擎侧事件（四壳广播）
# ============================================================

@dataclass
class PresetSwitch:
    """一次预设切换的**事实**（给外壳广播/状态行/审计用）。"""
    name: str = ""
    previous: str = ""
    permission: Dict[str, str] = field(default_factory=dict)
    changed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "previous": self.previous,
                "permission": dict(self.permission), "changed": list(self.changed),
                "warnings": list(self.warnings)}


def make_switch_event(switch: PresetSwitch) -> Dict[str, Any]:
    """把切换做成**引擎侧事件**（复用 WP-0 的既有通道：`core/ace_events`）。"""
    from core import ace_events
    return ace_events.make_event(
        EVENT_AGENT_PRESET, name=switch.name, previous=switch.previous,
        permission=dict(switch.permission), changed=list(switch.changed))


def emit_switch(switch: PresetSwitch, emitter: Any = None) -> Optional[Dict[str, Any]]:
    """广播一次切换：`emitter.emit("agent_preset", …)`。

    `emitter` 是 `core.ace_events.EventEmitter`（`--json` / `--serve` 那条通道）。
    没给 emitter 就**只构造不发送**（调用方自己决定去哪；事件仍可校验）。
    """
    ev = make_switch_event(switch)
    if emitter is None:
        return ev
    return emitter.emit(EVENT_AGENT_PRESET, **{k: v for k, v in ev.items()
                                               if k not in ("type", "ts")})


class AgentPresetRegistry:
    """预设的加载 / 激活 / 切换（**引擎侧**；四壳消费事件是外壳的活）。

    - `reload()` 只扫描（坏文件 → warning，不抛）
    - `activate(name)` 才做 S-1 判定（比全局更松 ⇒ `RelaxationForbidden`）
    - `switch(name)` 返回 `PresetSwitch` 并可经 `emit_switch` 广播

    构造即扫描一次（`reload` 幂等）：忘了先 `reload()` 就拿不到预设，
    是那种"看起来配上了其实没有"的假功能。
    """

    def __init__(self, project_root: Any = ".", *, home: Optional[Any] = None,
                 dirs: Optional[Sequence[Any]] = None) -> None:
        self.project_root = project_root
        self.home = home
        self.dirs = dirs
        self.warnings: List[str] = []
        self.presets: List[AgentPreset] = []
        self.by_name: Dict[str, AgentPreset] = {}
        self.current: Optional[AgentPreset] = None
        self.last_switch: Dict[str, Any] = {}
        self._baseline: Optional[Dict[str, str]] = None
        self.reload()                    # 构造即扫描（幂等；见类 docstring）

    def reload(self) -> "AgentPresetRegistry":
        scan = scan_agents(self.project_root, home=self.home, dirs=self.dirs)
        self.presets = scan.presets
        self.by_name = scan.by_name
        self.warnings = list(scan.warnings) + list(projection_warnings())
        return self

    def baseline(self) -> Dict[str, str]:
        if self._baseline is None:
            self._baseline = global_baseline()
        return dict(self._baseline)

    def get(self, name: str) -> Optional[AgentPreset]:
        return self.by_name.get(str(name or "").strip())

    def activate(self, name: str) -> Optional[AgentPreset]:
        """选中一个预设；名字为空/不存在 ⇒ `None`（= 无预设，行为逐字不变）。"""
        key = str(name or "").strip()
        if not key:
            self.current = None
            return None
        preset = self.get(key)
        if preset is None:
            self.current = None
            return None
        resolve_permission(preset, self.baseline())    # S-1：更松在这里当场抛
        self.current = preset
        return preset

    def switch(self, name: str, emitter: Any = None) -> PresetSwitch:
        """激活并**广播**（HL-03②：切换要有可观测声明）。"""
        previous = self.current.name if self.current else ""
        preset = self.activate(name)
        resolved = resolve_permission(preset, self.baseline())
        changed = [d for d in DIMENSIONS
                   if resolved.get(d) != self.baseline().get(d)]
        sw = PresetSwitch(
            name=(preset.name if preset else ""), previous=previous,
            permission=resolved, changed=changed,
            warnings=(list(preset.warnings) if preset else list(self.warnings)),
        )
        self.last_switch = sw.as_dict()
        emit_switch(sw, emitter)
        return sw

    def describe(self) -> str:
        """状态行/审计用的一行（人看的渲染由外壳做，这里给事实）。"""
        if self.current is None:
            return "agent: (none)"
        return f"agent: {self.current.name}"
