#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_prefix —— 前缀稳定性：指纹 / 归因 / drift / 恒等快路径（WP-3，纯逻辑）

## 为什么需要它

系统提示词**每轮重新拼串**，工具 schema 每次重新深拷贝，然后整包发给模型。做这两件事
的人（上游）真正想要的是一份**逐字节不变的前缀**：KV 缓存按前缀命中，前缀一变，整段
历史都要重新算。所以"前缀稳不稳"不是文风问题，是**每一轮的账单**问题。

但"稳"不能靠"别动它"来保证 —— 必须能回答三件事：变没变（指纹）、谁让它变的（归因）、
没人认领的变化是什么（drift）。这份模块就是回答这三件事的地方：

1. **pin / verify**：对不可变前缀（system + 工具 schema + scope）取 SHA-256 指纹，
   每请求前校验一次；
2. **attribute**：任何**打算**改变前缀的动作（`/model`、`/mode`、goal、MCP 重 pin …）
   必须带理由；空理由当场拒绝（"变化强制归因"）；
3. **drift**：没声明的变化如实上报（一次/每个新指纹），**原 pin 不丢** —— 不静默采纳；
4. **恒等快路径**：指纹不变则跳过 snapshot + stringify，调用方直接复用上一次那份快照。

## 三个最容易写错的地方

- **比解析后的 parameters，不比工具容器**。工具规格里的 `parameters` 可能是**活体
  getter**（`property`、无参函数、每次算一份新 schema 的对象）：容器身份一直没变，内容
  却每轮都不同。按容器身份/引用比 = 指纹永远"稳定"，而上游收到的是另一份 schema ——
  那是**假命中**，比不缓存更坏（缓存里躺着的是别人家的东西）。所以指纹只从
  `resolve_parameters()` 解析出来的值算，且**每次 verify 都重新解析**。
- **scope 也是指纹的一部分**。前缀缓存按模型/端点分桶：同样一份 system+tools 换个模型
  就是另一个缓存条目。`/model` 若不进指纹，就会"命中"一个根本不属于它的缓存。scope 由
  调用方拼（本仓库用 `model|base_url|permission|tools_ok`），本模块只当它是**不透明盐**。
- **drift 不更新 pin**。顺手采纳未声明的变化 = 把"没人认领的变化"洗成新基线，下一次就
  再也查不出是哪一步漂的。drift 只上报；要收敛，就补一条 `attribute(field, reason)`。

## 与工具面伸缩的关系（同属 WP-3）

42+ 个工具的 description 全部常驻是另一半账单。`ToolSurfaceBudget` 让常驻清单受预算
约束，超出的进 `DeferredToolCatalog`；模型用常驻的 `tool_search` 按需把它们找回来
（`activate()` 之后变成常驻，sticky —— 已经要过一次的工具不该让它再找一遍）。

`retrieve_tool_result` 本模块**只给接口**（`ResultStash` + schema），不注入常驻清单：
它的接线需要跨轮的结果留存与上限策略，那是另一件事（边界写在 `RETRIEVE_TOOL_RESULT_SPEC`
的注释里，不假装已经做了）。

本模块是**纯逻辑**：不读时钟、不读盘、不发请求、不 import 项目内其它模块
（`live_tool_specs()` 里那次 registry 读取是唯一的例外，而且是延迟导入）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

__all__ = [
    # 指纹
    "PREFIX_FINGERPRINT_VERSION", "resolve_parameters", "canonical_tool_payload",
    "canonical_prefix_payload", "prefix_fingerprint",
    "PrefixState", "PrefixEvent", "PrefixCheck", "PrefixStabilityManager",
    # 工具面
    "TOOL_SEARCH_NAME", "TOOL_SEARCH_SPEC", "DEFAULT_ALWAYS_ON",
    "SurfaceResult", "ToolSurfaceBudget", "DeferredToolCatalog", "live_tool_specs",
    "find_tool_search_call",
    # retrieve_tool_result（接口）
    "RETRIEVE_TOOL_RESULT_NAME", "RETRIEVE_TOOL_RESULT_SPEC", "StashedResult", "ResultStash",
]

PREFIX_FINGERPRINT_VERSION = "ace-prefix/1"

# 声明式归因的字段名（谁让它变的）：只用于记录与展示，不参与判定口径 ——
# 判定口径永远只有"指纹比没比中"。
FIELD_SYSTEM = "system"
FIELD_TOOLS = "tools"
FIELD_SCOPE = "scope"
FIELD_MODEL = "model"
FIELD_MODE = "mode"
FIELD_GOAL = "goal"
FIELD_MCP = "mcp"
FIELD_TOOL_SURFACE = "tool_surface"


# ============================================================
# 一、指纹：解析 → 规范化 → SHA-256
# ============================================================

def _get_field(obj: Any, name: str) -> Any:
    """从 dict / 对象上取字段（工具规格允许两种形态：OpenAI 字典或 ToolSpec dataclass）。"""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _resolve_value(value: Any, _depth: int = 0, _seen: Optional[set] = None) -> Any:
    """把**活体 getter** 解析成值，再递归规范化成可 JSON 化的形状。

    解析规则刻意保守：只对**可调用**的形态求值一次（无参），解析不出来就退化成
    `repr`（稳定字符串）—— 宁可指纹偏保守（换一个进程也还是同一串），也不让
    "解析失败"变成"指纹不变"。
    """
    if _depth > 8:
        return repr(value)
    if callable(value):
        try:
            return _resolve_value(value(), _depth + 1, _seen)
        except Exception as e:      # noqa: BLE001 —— getter 炸了也要给出**稳定**的指纹
            return f"<unresolvable {type(value).__name__}: {type(e).__name__}>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    _seen = _seen if _seen is not None else set()
    if isinstance(value, dict):
        _id = id(value)
        if _id in _seen:
            return "<cycle>"
        _seen.add(_id)
        try:
            return {str(k): _resolve_value(v, _depth + 1, _seen) for k, v in value.items()}
        finally:
            _seen.discard(_id)
    if isinstance(value, (list, tuple, set, frozenset)):
        _id = id(value)
        if _id in _seen:
            return "<cycle>"
        _seen.add(_id)
        try:
            return [_resolve_value(v, _depth + 1, _seen) for v in value]
        finally:
            _seen.discard(_id)
    # 路径对象、枚举、自定义类……：repr 通常稳定且带类名（比 str 更不容易撞车）
    return repr(value)


def resolve_parameters(tool: Any) -> Any:
    """取出工具的 `parameters` —— **解析后的值**，不是容器里的那个引用。

    三种形态都要认：
      - OpenAI 容器 `{"type": "function", "function": {"parameters": {...}}}`；
      - 裸规格 `{"name": ..., "parameters": {...}}` / ToolSpec dataclass；
      - 上面任意一层里的 `parameters` 是**活体 getter**（callable / property）。
    这是本模块存在的理由之一 —— 见模块 docstring 第二条。
    """
    fn = _get_field(tool, "function")
    if fn is not None and not callable(fn):
        inner = _get_field(fn, "parameters")
        if inner is not None:
            return _resolve_value(inner)
    return _resolve_value(_get_field(tool, "parameters"))


def tool_identity(tool: Any) -> Tuple[str, str, Any]:
    """拆出一件工具的 (name, description, resolved parameters)。"""
    fn = _get_field(tool, "function")
    holder = fn if (fn is not None and not callable(fn)) else tool
    return tool_name(tool), tool_description(tool), resolve_parameters(holder)


def tool_name(tool: Any) -> str:
    """工具名（**不解析** parameters：名字与 schema 是两件事，别顺手把 getter 调起来）。"""
    fn = _get_field(tool, "function")
    holder = fn if (fn is not None and not callable(fn)) else tool
    name = _get_field(holder, "name") or _get_field(tool, "name") or ""
    return str(name)


def tool_description(tool: Any) -> str:
    """工具用途（同上，不解析 parameters）。"""
    fn = _get_field(tool, "function")
    holder = fn if (fn is not None and not callable(fn)) else tool
    return str(_get_field(holder, "description") or _get_field(tool, "description") or "")


def _canonical(obj: Any) -> str:
    """规范化 JSON：键排序 + 紧凑分隔符 + 非 ASCII 原样（同值必同串）。"""
    return json.dumps(_resolve_value(obj), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def canonical_tool_payload(tools: Iterable[Any]) -> str:
    """工具面的规范化 payload（stringify 的产物：既是哈希输入，也是审计物料）。"""
    rows = []
    for t in tools or []:
        name, desc, params = tool_identity(t)
        rows.append({"name": name, "description": desc, "parameters": params})
    rows.sort(key=lambda r: r["name"])
    return _canonical(rows)


def canonical_prefix_payload(system: str, tools_payload: str, scope: str = "") -> str:
    """整包前缀的规范化 payload（指纹的哈希输入，也是"模型看到了什么"的审计物料）。"""
    return _canonical({"system": str(system or ""), "tools": str(tools_payload or ""),
                       "scope": str(scope or "")})


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def tool_names(tools: Optional[Iterable[Any]]) -> Tuple[str, ...]:
    return tuple(sorted(tool_name(t) for t in (tools or [])))


def _fingerprint_from(system: str, tools_payload: str, names: Tuple[str, ...],
                      scope: str) -> "PrefixState":
    sys_txt = str(system or "")
    sys_d = _digest(sys_txt)
    tools_d = _digest(tools_payload)
    body = _canonical({"v": PREFIX_FINGERPRINT_VERSION, "system": sys_d,
                       "tools": tools_d, "scope": str(scope or "")})
    return PrefixState(digest=_digest(body), system_digest=sys_d, tools_digest=tools_d,
                       scope=str(scope or ""), system_len=len(sys_txt),
                       tool_names=names, tool_count=len(names))


def prefix_fingerprint(system: str, tools: Optional[Iterable[Any]] = None,
                       scope: str = "") -> "PrefixState":
    """算出前缀指纹（**不含** snapshot / payload：快路径比较只用这一半）。

    为什么要分成"指纹"与"快照"两次构造：恒等快路径的全部价值在于"没变就什么都别建"。
    如果指纹本身就顺带把整包 payload 拼出来，那快路径省下的只有一份字符串拷贝 ——
    把构造成本挪进比较里，等于没省。所以这里只算摘要，快照由 `_snapshot()` 单独建。

    反过来，**一次 verify 里只能解析一遍**工具规格（`_fingerprint_from` 的存在理由）：
    `parameters` 是活体 getter 时，解析两遍会拿到两个值 —— 摘要按第一遍算、payload 按
    第二遍存，那条 pin 自己就自相矛盾了。
    """
    tools_l = list(tools or [])
    return _fingerprint_from(system, canonical_tool_payload(tools_l),
                             tool_names(tools_l), scope)


@dataclass(frozen=True)
class PrefixState:
    """一份前缀的指纹；`system` / `tools_payload` 只在**pin 时**填（快照）。

    `tools_payload` 刻意存**字符串**而不是那份工具列表：pin 会活很久，而列表里可能
    挂着活体 getter 的容器 —— 攥着引用等于让"快照"随注册表一起变。字符串不会。
    """
    digest: str
    system_digest: str
    tools_digest: str
    scope: str = ""
    system_len: int = 0
    tool_names: Tuple[str, ...] = ()
    tool_count: int = 0
    system: str = ""
    tools_payload: str = ""

    @property
    def has_snapshot(self) -> bool:
        return bool(self.tools_payload) or bool(self.system)


@dataclass(frozen=True)
class PrefixEvent:
    """一条前缀事件（归因 / 重 pin / drift）—— 台账与回调的物料。"""
    seq: int
    kind: str                     # attribution | pin | repin | drift | declare_noop
    field: str = ""
    reason: str = ""
    detail: str = ""
    digest: str = ""              # 事件发生时**生效的 pin**（drift 时 = 原 pin，不丢）
    changed_fields: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "field": self.field,
                "reason": self.reason, "detail": self.detail, "digest": self.digest,
                "changed_fields": list(self.changed_fields)}


@dataclass(frozen=True)
class PrefixCheck:
    """一次校验的结论。

    `state`：本次算出来的指纹；**命中快路径时就是 pin 的那份快照**（可直接复用）。
    `pin`：校验之后**仍生效**的 pin —— drift 时是原 pin（这一条是硬要求）。
    `reported`：这次 drift 是不是**新**上报的（同一指纹只报一次，不刷屏）。
    """
    state: PrefixState
    pin: Optional[PrefixState]
    fast_path: bool = False
    changed: bool = False
    drift: bool = False
    declared_by: str = ""
    reason: str = ""
    changed_fields: Tuple[str, ...] = ()
    reported: bool = False


def _changed_fields(before: Optional[PrefixState], after: PrefixState) -> Tuple[str, ...]:
    if before is None:
        return ()
    out = []
    if before.system_digest != after.system_digest:
        out.append(FIELD_SYSTEM)
    if before.tools_digest != after.tools_digest:
        out.append(FIELD_TOOLS)
    if before.scope != after.scope:
        out.append(FIELD_SCOPE)
    return tuple(out)


class PrefixStabilityManager:
    """前缀稳定性的全部状态（pin / 待消费的声明 / 事件环 / 计数）。

    一次典型会话：

        mgr.attribute("model", "用户 /model 切到 X")     # 先声明（带理由）
        chk = mgr.verify(system, tools, scope=...)      # 每请求前校验一次
        if chk.fast_path:
            ... 复用 chk.state.system / chk.state.tools_payload（不重算）
        elif chk.drift:
            ... 如实上报；chk.pin 还是原来那份

    线程模型：CLI 是单线程请求路径，本类**不加锁**（纯逻辑、可单测）。
    """

    def __init__(self, on_event: Optional[Callable[[PrefixEvent], None]] = None) -> None:
        self._pin: Optional[PrefixState] = None
        self._pending: Optional[Tuple[str, str, str]] = None   # (field, reason, detail)
        self._events: List[PrefixEvent] = []
        self._drift_seen: set = set()
        self._seq = 0
        self._on_event = on_event
        self._stats = {"verifies": 0, "fingerprints_computed": 0, "fast_path_hits": 0,
                       "snapshots_taken": 0, "payloads_built": 0, "pins": 0,
                       "repins": 0, "attributions": 0, "drifts": 0,
                       "declared_noops": 0}

    # ---------- 只读视图 ----------

    @property
    def pin(self) -> Optional[PrefixState]:
        return self._pin

    def events(self) -> List[PrefixEvent]:
        return list(self._events)

    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def pending(self) -> Optional[Tuple[str, str, str]]:
        return self._pending

    # ---------- 事件 ----------

    def _emit(self, kind: str, *, field_: str = "", reason: str = "", detail: str = "",
              changed_fields: Tuple[str, ...] = ()) -> PrefixEvent:
        self._seq += 1
        ev = PrefixEvent(seq=self._seq, kind=kind, field=field_, reason=reason,
                         detail=detail, changed_fields=changed_fields,
                         digest=(self._pin.digest if self._pin else ""))
        self._events.append(ev)
        if self._on_event is not None:
            try:
                self._on_event(ev)
            except Exception:       # noqa: BLE001 —— 台账写不进去不该让请求挂掉
                pass
        return ev

    # ---------- 归因 ----------

    def attribute(self, field: str, reason: str, *, detail: str = "",
                  system: Optional[str] = None, tools: Optional[Iterable[Any]] = None,
                  scope: Optional[str] = None) -> PrefixEvent:
        """声明一次前缀变化 —— **带理由**；同时记一条归因事件。

        空理由抛 `ValueError`：这条纪律如果允许"忘了写"，一个月后日志里就全是
        `reason=""`，而那时没人记得住当时为什么变。宁可当场炸。

        给了 `system`（以及 `tools`/`scope`）就**立刻重 pin**（本方法名副其实）；
        没给就只登记，由下一次 `verify()` 消费 —— 因为 `/model` 那一刻新的系统提示词
        还没拼出来，硬拼一份只会把"声明"和"事实"错开一拍。
        """
        if not str(reason or "").strip():
            raise ValueError("前缀变化必须带理由（attribute 的 reason 不能为空）")
        if not str(field or "").strip():
            raise ValueError("前缀变化必须指明来源字段（attribute 的 field 不能为空）")
        self._stats["attributions"] += 1
        ev = self._emit("attribution", field_=str(field), reason=str(reason),
                        detail=str(detail or ""))
        if system is not None:
            tools_l = list(tools or [])
            return self._repin(system, canonical_tool_payload(tools_l), tool_names(tools_l),
                               self._pin.scope if scope is None else str(scope),
                               field_=str(field), reason=str(reason),
                               detail=str(detail or ""), attributed=True)
        self._pending = (str(field), str(reason), str(detail or ""))
        return ev

    def _repin(self, system: str, payload: str, names: Tuple[str, ...], scope: str, *,
               field_: str = "", reason: str = "", detail: str = "",
               changed_fields: Tuple[str, ...] = (), attributed: bool = False) -> PrefixEvent:
        """把指纹升级成**快照**并立为新 pin（唯一会写 `_pin` 的地方）。

        接收**已经算好的** payload/names（而不是工具列表）：一次校验里工具规格只解析
        一遍 —— 见 `prefix_fingerprint` 的说明（活体 getter 解析两遍会自相矛盾）。
        """
        state = _fingerprint_from(system, payload, names, scope)
        self._stats["snapshots_taken"] += 1
        self._stats["payloads_built"] += 1
        self._pin = PrefixState(digest=state.digest, system_digest=state.system_digest,
                                tools_digest=state.tools_digest, scope=state.scope,
                                system_len=state.system_len, tool_names=state.tool_names,
                                tool_count=state.tool_count, system=str(system or ""),
                                tools_payload=payload)
        if attributed:
            self._stats["repins"] += 1
            kind = "repin"
        else:
            self._stats["pins"] += 1
            kind = "pin"
        return self._emit(kind, field_=field_, reason=reason, detail=detail,
                          changed_fields=changed_fields)

    # ---------- 校验 ----------

    def verify(self, system: str, tools: Optional[Iterable[Any]] = None,
               scope: str = "") -> PrefixCheck:
        """每请求前校验一次：命中快路径 / 带理由重 pin / drift 上报（原 pin 不丢）。"""
        tools_l = list(tools or [])
        self._stats["verifies"] += 1
        self._stats["fingerprints_computed"] += 1
        payload = canonical_tool_payload(tools_l)
        cur = _fingerprint_from(system, payload, tool_names(tools_l), scope)
        prev = self._pin

        # 1) 恒等快路径：指纹没变 → 什么都不建，直接把上一次那份快照交回去
        if prev is not None and cur.digest == prev.digest:
            self._stats["fast_path_hits"] += 1
            if self._pending is not None:
                _f, _r, _d = self._pending
                self._pending = None
                self._stats["declared_noops"] += 1
                self._emit("declare_noop", field_=_f, reason=_r, detail=_d)
            return PrefixCheck(state=prev, pin=prev, fast_path=True, changed=False)

        # 2) 首次 pin（有声明就挂在这一次上，而不是记成"声明了却没变"）
        if prev is None:
            names = tool_names(tools_l)
            if self._pending is not None:
                _f, _r, _d = self._pending
                self._pending = None
                self._repin(system, payload, names, scope, field_=_f, reason=_r,
                            detail=_d, attributed=True)
                return PrefixCheck(state=self._pin, pin=self._pin, changed=True,
                                   declared_by=_f, reason=_r)
            self._repin(system, payload, names, scope)
            return PrefixCheck(state=self._pin, pin=self._pin, changed=True)

        fields = _changed_fields(prev, cur)

        # 3) 有声明 → 带理由的 re-pin（这是**正常路径**，不是 drift）
        if self._pending is not None:
            _f, _r, _d = self._pending
            self._pending = None
            self._repin(system, payload, tool_names(tools_l), scope, field_=_f, reason=_r,
                        detail=_d, changed_fields=fields, attributed=True)
            return PrefixCheck(state=self._pin, pin=self._pin, changed=True,
                               declared_by=_f, reason=_r, changed_fields=fields)

        # 4) 没人声明 → drift：如实上报，**原 pin 保留**（顺手采纳 = 把漂移洗成基线）
        self._stats["snapshots_taken"] += 1
        self._stats["payloads_built"] += 1
        snap = PrefixState(digest=cur.digest, system_digest=cur.system_digest,
                           tools_digest=cur.tools_digest, scope=cur.scope,
                           system_len=cur.system_len, tool_names=cur.tool_names,
                           tool_count=cur.tool_count, system=str(system or ""),
                           tools_payload=payload)
        reported = cur.digest not in self._drift_seen
        if reported:
            self._drift_seen.add(cur.digest)
            self._stats["drifts"] += 1
            self._emit("drift", detail=f"未声明的变化：{'+'.join(fields) or '未知'}",
                       changed_fields=fields)
        return PrefixCheck(state=snap, pin=prev, changed=True, drift=True,
                           changed_fields=fields, reported=reported)

    def reset(self) -> None:
        """丢掉 pin（`/clear`、换会话）：下一次 verify 会重新立基线。"""
        self._pin = None
        self._pending = None
        self._drift_seen.clear()


# ============================================================
# 二、工具面伸缩：ToolSurfaceBudget + 延迟工具目录
# ============================================================

TOOL_SEARCH_NAME = "tool_search"

#: 常驻优先的工具（预算吃紧时也不折叠）：一个会话"起步就要用"的那几个。
#: 这张表是**声明**，不是判据 —— 真正的判据只有预算与 `always_on` 的交集。
DEFAULT_ALWAYS_ON: Tuple[str, ...] = (
    "file_read", "file_write", "str_replace", "grep", "glob",
    "terminal_exec", "plan_propose", "request_permission", "todo_write", "ask_user",
)

TOOL_SEARCH_SPEC: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_SEARCH_NAME,
        "description": ("按需检索本会话**被折叠**的工具。工具太多时只有一部分常驻；"
                        "这里可以用关键词（如 git / 数据库 / 邮件 / 图片 / 知识库）"
                        "查到剩下的工具的名字、用途与参数；命中的工具在下一轮变成"
                        "可直接调用的常驻工具。"),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "关键词；留空 = 列出被折叠工具的目录（有上限）"},
            },
            "required": ["query"],
        },
    },
}

#: `retrieve_tool_result` 的 schema —— **只登记接口，不注入常驻清单**。
#: 边界（如实说）：它要把"被折叠的工具输出"存起来、跨轮取回，需要一条留存与上限策略
#: （谁能取、留多久、多大），并且要和现有的 `/expand` 折叠路径统一 —— 那是另一件事。
#: 在接线之前把它塞进模型能看到的清单，等于承诺一个调用就 400 的工具。
RETRIEVE_TOOL_RESULT_NAME = "retrieve_tool_result"
RETRIEVE_TOOL_RESULT_SPEC: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RETRIEVE_TOOL_RESULT_NAME,
        "description": ("取回此前被折叠/截断的工具结果原文（按 id）。"
                        "本版本只登记接口，未接入请求路径。"),
        "parameters": {"type": "object",
                       "properties": {"id": {"type": "string"}},
                       "required": ["id"]},
    },
}


def live_tool_specs() -> List[Dict[str, Any]]:
    """**现算**工具规格（不是导入期快照）。

    为什么必须现算：MCP / 插件在运行时 `registry.register()`，而 `agent_runner.TOOLS`
    是导入期拷的一份。快照口径下，运行时注册的工具**永远进不了请求清单** ——
    配置文档承诺的"模型看到的工具列表里就能直接调用它们"于是不成立。
    """
    from tools.registry import openai_tools      # noqa: PLC0415 —— 延迟导入：纯逻辑模块不背项目依赖
    return list(openai_tools())


@dataclass(frozen=True)
class SurfaceResult:
    """一次工具面装配的结果。"""
    resident: List[Dict[str, Any]]
    folded: Tuple[str, ...]
    budget: int
    search_available: bool

    @property
    def resident_names(self) -> Tuple[str, ...]:
        return tool_names(self.resident)

    @property
    def folded_count(self) -> int:
        return len(self.folded)


class DeferredToolCatalog:
    """被折叠工具的目录：按关键词检索（`tool_search` 的数据面）。

    打分保守且可解释：名字命中 > 描述命中；同分按名字排序（同输入必同输出，
    便于断言与重放）。空查询 = 列目录（有上限），不是"没结果"。
    """

    def __init__(self, entries: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        self._entries: Dict[str, Dict[str, str]] = dict(entries or {})
        self._folded: List[str] = []

    def set_entries(self, entries: Dict[str, Dict[str, str]]) -> None:
        self._entries = dict(entries or {})

    def set_folded(self, names: Iterable[str]) -> None:
        self._folded = [n for n in names if n in self._entries]

    def folded_names(self) -> Tuple[str, ...]:
        return tuple(self._folded)

    def search(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        toks = [x for x in re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+",
                                    str(query or "").lower()) if x]
        out: List[Dict[str, Any]] = []
        for name in self._folded:
            entry = self._entries.get(name) or {}
            desc = str(entry.get("description") or "").lower()
            low = name.lower()
            score = 1 if not toks else 0
            for tk in toks:
                if low == tk:
                    score += 100
                elif tk in low:
                    score += 40
                elif tk in desc:
                    score += 10
            if score > 0:
                out.append({"name": name, "description": entry.get("description") or "",
                            "score": score, "folded": True})
        out.sort(key=lambda d: (-int(d["score"]), str(d["name"])))
        return out[:max(1, int(top_k))]


class ToolSurfaceBudget:
    """把"全部工具常驻"换成"预算内的常驻 + 按需检索"。

    语义（三条，都是刻意的）：
      - `budget <= 0` = **不折叠**（与改动前逐字相同）；
      - 常驻数**不超过** `budget`，`tool_search` 自己占一个名额（它也得先被模型看见，
        否则折叠的工具永远找不回来）；
      - 折叠是**有目录的折叠**：只有真的折了东西才注入 `tool_search`
        （没折就注入，等于让模型去查一个空目录 —— 那是不诚实的面）。
      - 激活是 **sticky**：模型要过一次的工具不再折回去（让它反复搜同一件事，比
        多常驻几个工具更贵）。
    """

    def __init__(self, budget: int = 0, *, always_on: Optional[Iterable[str]] = None,
                 search_tool: bool = True) -> None:
        self.budget = int(budget or 0)
        self.always_on: Tuple[str, ...] = tuple(always_on if always_on is not None
                                                else DEFAULT_ALWAYS_ON)
        self.search_tool = bool(search_tool)
        self._activated: List[str] = []
        self.catalog = DeferredToolCatalog()

    # ---------- 激活 ----------

    def activate(self, names: Iterable[str]) -> List[str]:
        """把折叠的工具提为常驻（sticky）。返回**新**激活的名字。"""
        folded = set(self.catalog.folded_names())
        newly = []
        for n in names or []:
            n = str(n)
            if n in folded and n not in self._activated:
                self._activated.append(n)
                newly.append(n)
        return newly

    def activated(self) -> Tuple[str, ...]:
        return tuple(self._activated)

    def search(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        return self.catalog.search(query, top_k=top_k)

    # ---------- 装配 ----------

    def apply(self, tools: Iterable[Any]) -> SurfaceResult:
        specs = [t for t in (tools or []) if tool_name(t) != TOOL_SEARCH_NAME]
        by_name: Dict[str, Any] = {}
        order: List[str] = []
        for t in specs:
            n = tool_name(t)
            if n in by_name:
                continue
            by_name[n] = t
            order.append(n)
        self.catalog.set_entries({n: {"description": tool_description(by_name[n])}
                                  for n in order})

        # budget<=0 或装得下：全量常驻（不建目录、不注入检索工具）
        if self.budget <= 0 or len(order) <= self.budget:
            self.catalog.set_folded([])
            return SurfaceResult(resident=[by_name[n] for n in order], folded=(),
                                 budget=self.budget, search_available=False)

        slots = self.budget - (1 if self.search_tool else 0)
        if slots <= 0:              # 预算小到只剩检索工具：如实（不偷偷多发工具）
            slots = 0
        picked: List[str] = []
        for src in (self._activated, list(self.always_on)):
            for n in src:
                if n in by_name and n not in picked:
                    picked.append(n)
        for n in order:
            if len(picked) >= slots:
                break
            if n not in picked:
                picked.append(n)
        picked = picked[:slots]
        folded = tuple(n for n in order if n not in picked)
        self.catalog.set_folded(folded)

        resident = [by_name[n] for n in picked]
        search_available = bool(self.search_tool and folded)
        if search_available:
            resident = [TOOL_SEARCH_SPEC] + resident
        return SurfaceResult(resident=resident, folded=folded, budget=self.budget,
                             search_available=search_available)


# ============================================================
# 三、tool_search 的**调用**识别（它不在注册表里，由工具面自己回答）
# ============================================================

def find_tool_search_call(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出里认出一次 `tool_search` 调用（两种协议形态都认）。

    为什么不能靠执行层：`tool_search` 是**工具面的工具**，没进 registry —— 执行层看到
    它只会回"未知工具 400"。所以要在分发之前截住（调用点在 ai_code.converse）。
    认不出就返回 None（调用方照常走执行层）—— 宁可漏截一次，也不误截别的工具。
    """
    s = str(text or "")
    if TOOL_SEARCH_NAME not in s:
        return None
    for m in re.finditer(r"\{[^{}]*\}", s):
        try:
            obj = json.loads(m.group(0))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        if str(obj.get("tool") or obj.get("name") or "") != TOOL_SEARCH_NAME:
            continue
        args = {k: v for k, v in obj.items() if k not in ("tool", "name")}
        args.setdefault("query", "")
        return args
    return None


# ============================================================
# 四、retrieve_tool_result：只留接口（边界见 RETRIEVE_TOOL_RESULT_SPEC）
# ============================================================

@dataclass(frozen=True)
class StashedResult:
    rid: str
    tool: str
    text: str
    truncated: bool
    chars: int


class ResultStash:
    """被折叠工具结果的**留存接口**（本 WP 不接线，见模块 docstring 末段）。

    上限是行为的一部分：装不下时丢**最旧**的，并在 `get()` 拿不到时如实返回 None
    —— 不返回"看起来像原文"的空串。
    """

    def __init__(self, max_entries: int = 8, max_chars: int = 200_000) -> None:
        self.max_entries = max(1, int(max_entries))
        self.max_chars = max(1000, int(max_chars))
        self._items: List[StashedResult] = []
        self._seq = 0

    def put(self, tool: str, text: str) -> str:
        body = str(text or "")
        truncated = len(body) > self.max_chars
        if truncated:
            body = body[:self.max_chars]
        self._seq += 1
        rid = f"tr{self._seq}"
        self._items.append(StashedResult(rid=rid, tool=str(tool or ""), text=body,
                                         truncated=truncated, chars=len(body)))
        while len(self._items) > self.max_entries:
            self._items.pop(0)
        return rid

    def get(self, rid: str) -> Optional[str]:
        for it in self._items:
            if it.rid == str(rid):
                return it.text
        return None

    def entry(self, rid: str) -> Optional[StashedResult]:
        for it in self._items:
            if it.rid == str(rid):
                return it
        return None

    def ids(self) -> Tuple[str, ...]:
        return tuple(it.rid for it in self._items)
