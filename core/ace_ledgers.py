#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_ledgers —— 三层共用的**两个账本**（`THREE-LAYERS` §4 的枢纽）

    ┌────────────────────┬──────────────────────────┬──────────────────────────┐
    │                    │ 拒绝账本 RefusalLedger   │ 失败账本 FailureLedger   │
    ├────────────────────┼──────────────────────────┼──────────────────────────┤
    │ 回答               │ "这个意图是不是此路不通" │ "现在该升到哪一级"       │
    │ 键                 │ (goal_id, fingerprint,   │ 同一键空间（这是设计，   │
    │                    │  class)                  │ 不是巧合 —— 见 §8 TH-R2）│
    │ 寿命               │ **长期 / 跨会话**（知识）│ **短期 / 本会话**（状态）│
    │ 出口               │ 提议固化规则 / 上报缺陷  │ 熔断 / 降级 / 上报       │
    └────────────────────┴──────────────────────────┴──────────────────────────┘

**为什么必须分开**：它们的时效不同。
把"被拒过"当状态会**丢掉知识**（每次重学）；把"失败过"当知识会**污染规则**
（一次截断就永久禁掉一个工具 —— 这正是 H-19 的 bug，见 `agent_runner.py:96-103`）。
`test_all` 的 `[10]`/`[79]` 钉住了其中一半（MALFORMED 永不计入熔断），
本模块把另一半（拒绝 ≠ 失败）也变成结构：**拒绝账本从不熔断**，
它的学习出口只有"提议固化（人确认）"与"上报缺陷（人裁决）"。

## 三个纪律

1. **键空间只有一个**：`LedgerKey(goal_id, fingerprint, refusal_class)`。
   `fingerprint` 是**关键参数归一化后的哈希** —— 同一意图的不同写法落到同一指纹，
   于是"熔断的是那条路，不是整个工具"（HL-01）。
2. **拒绝账本是知识，失败账本是状态**：前者可 `save`/`load`（跨会话），
   后者只有 `record`/`clear`（会话结束即清，**故意没有**落盘 API）。
3. **DL-04：学习只能让人更严，不能自动放宽**：学习动作是闭集
   （`no_resend` / `alternatives` / `propose_rule` / `report_defect`），
   规则提议**只允许 `deny`** 且**必须由人确认**；任何放宽动作当场抛
   `RelaxationForbidden`（`tools.status.assert_no_relaxation`）。

纯逻辑 + 一次落盘，所以两个账本可以脱离执行层、脱离磁盘单测（`.test_tmp/ledger_check.py`）。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core import ace_rules
from tools.status import (
    LADDER_BREAKER_N,
    LADDER_CROSS_GOAL_N,
    LADDER_DEGRADE_TOOL_N,
    LADDER_L0_RETRY,
    LADDER_L1_REROUTE,
    LADDER_L2_BREAKER,
    LADDER_L3_DEGRADE,
    LADDER_L4_ESCALATE,
    LEARNING_ACTION_ALTERNATIVES,
    LEARNING_ACTION_NO_RESEND,
    LEARNING_ACTION_ORDER,
    LEARNING_ACTION_PROPOSE_RULE,
    LEARNING_ACTION_REPORT_DEFECT,
    REFUSAL_CLASS_AUTH_PENDING,
    REFUSAL_CLASS_BOUNDARY,
    REFUSAL_CLASS_CAPABILITY,
    REFUSAL_CLASS_MALFORMED,
    REFUSAL_CLASS_POLICY,
    REFUSAL_CLASS_TRANSIENT,
    RULE_PROPOSABLE_CLASSES,
    RelaxationForbidden,
    assert_no_relaxation,
    class_closes_path,
    driver_action,
    ladder_highest,
)

__all__ = [
    "CROSS_GOAL_N", "FingerprintOf", "FailureEntry", "FailureLedger",
    "LearningAction", "LedgerKey", "BannedToolsView", "RefusalEntry",
    "RefusalLedger", "RepeatFailView", "RULE_PROPOSAL_N", "RuleDefectReport",
    "RuleProposal", "defect_producer", "fingerprint_call", "hint_for",
    "ladder_step",
]

#: 同 `(goal_id, fingerprint, class)` 被拒 N 次 → 提议固化成规则（DL-03 动作③）。
#: 与阶梯的 L2 阈值同一个数：第 3 次既"熔断这条路"（状态），也"值得提议固化"
#: （知识）—— 两条出口各自独立，这正是"同键不同命"。
RULE_PROPOSAL_N = LADDER_BREAKER_N
#: 同 class 跨目标 ≥N → 上报规则缺陷（DL-03 动作④ / HL-L4）。
CROSS_GOAL_N = LADDER_CROSS_GOAL_N

#: 归一化时**丢掉**的键：它们不是"意图"，是这一轮的说法/上下文。
#: 丢多了会把两次不同的调用并成一条路（错压比少压更坏），所以只丢确定不属于意图的。
_VOLATILE_PARAMS = frozenset({"tool", "reason", "comment", "note", "user_input", "task_id"})

#: 路径类键：Windows 下折大小写**只对它们**（`C:\\X` 与 `c:/x` 是同一个文件）。
#: 为什么不对所有字符串折：`content="A"` 与 `content="a"` 是两次**不同**的写入意图，
#: 折了就会把两条无关的路并成一条（虽然方向仍是变严，但会误伤合法调用）。
_PATH_KEYS = frozenset({"path", "dest", "source", "target", "dir", "cwd", "root",
                        "file", "output", "input"})

#: 账本内存上限：超过就按 `last_at` 淘汰最旧的。
#: 为什么要有：长期账本会随会话次数单调增长。这是一个**有损**边界（淘汰即丢知识），
#: 所以给得很大；真要无限的持久账本该上数据库，不该拿内存 dict 硬撑。
_MAX_ENTRIES = 5000


# ============================================================
# 共用键类型 + 指纹
# ============================================================

@dataclass(frozen=True)
class LedgerKey:
    """两个账本共用的键：`(goal_id, fingerprint, refusal_class)`。

    `goal_id` 空串 = 当前没有活动目标（会话级）。空串不是"第 0 个目标"，
    所以它**不算一个跨目标证据**（见 `RefusalLedger.distinct_goals`）。
    """

    goal_id: str = ""
    fingerprint: str = ""
    refusal_class: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", str(self.goal_id or ""))
        object.__setattr__(self, "fingerprint", str(self.fingerprint or ""))
        object.__setattr__(self, "refusal_class",
                           str(self.refusal_class or "").strip().upper())

    def as_tuple(self) -> Tuple[str, str, str]:
        return (self.goal_id, self.fingerprint, self.refusal_class)

    def as_dict(self) -> Dict[str, str]:
        return {"goal_id": self.goal_id, "fingerprint": self.fingerprint,
                "refusal_class": self.refusal_class}

    def __str__(self) -> str:
        return f"{self.goal_id or '-'}|{self.fingerprint or '-'}|{self.refusal_class or '-'}"


def _norm_piece(value: Any, key: str = "") -> Any:
    """一个参数值的归一：字符串去空白/折叠空白、反斜杠→正斜杠；路径类键在 Windows
    上再折大小写（与 `core.ace_rules._norm_path` 同一口径：同一个文件不该因为写
    `C:\\X` 还是 `c:/x` 变成两条路）。
    """
    if isinstance(value, str):
        s = " ".join(value.replace("\\", "/").split())
        if os.name == "nt" and (_looks_like_path(s) or key.lower() in _PATH_KEYS):
            s = s.lower()
        return s
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_norm_piece(v, key) for v in value]
    if isinstance(value, dict):
        return {str(k): _norm_piece(v, str(k))
                for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return str(value)


def _looks_like_path(s: str) -> bool:
    """`/x` 或 `C:/x` 这类明显是路径的值（即便键名不在 `_PATH_KEYS` 里）。"""
    if s.startswith("/"):
        return True
    return len(s) > 2 and s[1] == ":" and s[2] == "/"


def fingerprint_call(tool: str, params: Optional[Dict[str, Any]] = None) -> str:
    """一次工具调用**关键参数归一化**后的指纹（两个账本的键中间那截）。

    同一意图的不同写法必须落到同一指纹，否则"熔断这条路"就退化成"熔断这次写法"：
    反斜杠/正斜杠、首尾空白、Windows 路径大小写、参数顺序、`reason` 这类说法 —— 全部归一。

    截 16 个十六进制字符（64 bit）：单会话/单项目的键数量级远达不到碰撞风险，
    而短指纹要进摘要行（RL-03 的 `fp=a3f2`）给人看。
    """
    raw = params if isinstance(params, dict) else {}
    payload = {str(k): _norm_piece(v, str(k)) for k, v in raw.items()
               if str(k) not in _VOLATILE_PARAMS}
    blob = json.dumps({"tool": str(tool or ""), "params": payload},
                      ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


#: 类型别名：指纹就是上面那个短十六进制串（写在这里免得调用方各自猜格式）。
FingerprintOf = str


# ============================================================
# 替代路径（DL-03 学习动作②的素材）
# ============================================================

#: 每一类拒绝的**默认替代路径**：拒绝不是终点，必须带上"还能怎么走"。
#: 执行层/工具给了 `ExecutionResult.hint` 时以那个为准（这里只是兜底）。
_DEFAULT_HINTS: Dict[str, Dict[str, List[str]]] = {
    REFUSAL_CLASS_POLICY: {
        "alternatives": ["换一种做法或参数（同一意图的另一条实现）",
                         "让用户用 /rules 改 .ace/permissions*.json 里的规则"],
        "missing": [],
    },
    REFUSAL_CLASS_BOUNDARY: {
        "alternatives": ["改到项目目录内的合法路径",
                         "换用其他工具完成同一目标"],
        "missing": [],
    },
    REFUSAL_CLASS_AUTH_PENDING: {
        "alternatives": [],
        "missing": ["用户授权（等回答，不是失败）"],
    },
    REFUSAL_CLASS_CAPABILITY: {
        "alternatives": ["降级到受支持的能力/路径并**声明**这次降级"],
        "missing": ["沙箱/运行环境能力"],
    },
    REFUSAL_CLASS_TRANSIENT: {
        "alternatives": ["退避后重试同一条路"],
        "missing": [],
    },
    REFUSAL_CLASS_MALFORMED: {
        "alternatives": ["重新生成完整、闭合的输出（不是换工具）"],
        "missing": ["闭合的 JSON / 完整输出"],
    },
}


def hint_for(refusal_class: str, tool: str = "",
             message: str = "") -> Dict[str, List[str]]:
    """该拒绝类的替代路径 `{alternatives, missing}`（拷贝，调用方改不坏模板）。"""
    base = _DEFAULT_HINTS.get(str(refusal_class or "").strip().upper(), {})
    return {"alternatives": list(base.get("alternatives") or []),
            "missing": list(base.get("missing") or [])}


def defect_producer(refusal_class: str) -> str:
    """这类拒绝**是谁生产的**（HL-04 的 `production producer`）。

    §0.1 那个案例的全部教训在这一行：上报必须能指认生产者，否则"模型死循环"这种
    归因会让人去修错的地方。取不到（未分类）时**如实说未知**，不编一个。
    """
    return _DEFECT_PRODUCERS.get(
        str(refusal_class or "").strip().upper(),
        "未知（上报时必须补上生产者，否则就是 §0.1 的归错因）")


# ============================================================
# HL-02 五级阶梯（判定在 `tools.status` 的登记表，这里只做"数"）
# ============================================================

def ladder_step(*, refusal_class: str, fingerprint_count: int, tool_count: int,
                cross_goals: int = 0, budget_exhausted: bool = False,
                breaker_n: Optional[int] = None,
                degrade_tool_n: Optional[int] = None,
                cross_goal_n: Optional[int] = None) -> str:
    """算出这一次该升到哪一级（§3.3 那张表）。

    触发条件（各自独立，取**最高**档 —— 阶梯只升不降）：
      L0 `TRANSIENT`（退避重试）/ 基线；`MALFORMED` **永远**停在这里（H-19）
      L1 `POLICY`/`BOUNDARY` 首次 → 换路径
      L2 同 `(goal, fingerprint, class)` 第 `breaker_n` 次 → 禁掉**这个指纹**
      L3 `CAPABILITY`，或同工具第 `degrade_tool_n` 次 → 降级并声明
      L4 同 class 跨目标 ≥ `cross_goal_n`，或任一级预算耗尽 → 停下问人

    `MALFORMED` 在最前面早退是**有意的**：它在 `FailureLedger.record` 里根本进不来，
    这里再挡一次，是为了让"截断永不升级"这个契约在两处都成立（H-19 的教训就是
    只有一处判据时会漏）。

    CAPABILITY 即便数到 3 也走 L3（降级并声明）而不是 L2 —— 能力缺失时"禁掉这条路"
    没有意义（没地方可去），RL-02 给它的唯一动作是"降级并声明，或上报"。
    """
    cls = str(refusal_class or "").strip().upper()
    if cls == REFUSAL_CLASS_MALFORMED:
        return LADDER_L0_RETRY
    bn = LADDER_BREAKER_N if breaker_n is None else int(breaker_n)
    dn = LADDER_DEGRADE_TOOL_N if degrade_tool_n is None else int(degrade_tool_n)
    gn = LADDER_CROSS_GOAL_N if cross_goal_n is None else int(cross_goal_n)

    hits: List[str] = [LADDER_L0_RETRY]
    if int(cross_goals or 0) >= gn or budget_exhausted:
        hits.append(LADDER_L4_ESCALATE)
    if cls == REFUSAL_CLASS_CAPABILITY or int(tool_count or 0) >= dn:
        hits.append(LADDER_L3_DEGRADE)
    if int(fingerprint_count or 0) >= bn:
        hits.append(LADDER_L2_BREAKER)
    if cls in (REFUSAL_CLASS_POLICY, REFUSAL_CLASS_BOUNDARY):
        hits.append(LADDER_L1_REROUTE)
    return ladder_highest(*hits)


# ============================================================
# 学习动作 / 提议 / 上报（DL-03 的四个出口）
# ============================================================

@dataclass
class LearningAction:
    """一次"从拒绝中学习"的产物。`kind` 是 `tools.status.LEARNING_ACTIONS` 闭集里的值。"""

    kind: str
    detail: str = ""
    payload: Any = None
    requires_human: bool = False

    def __post_init__(self) -> None:
        self.kind = str(self.kind or "").strip()
        # DL-04：每一件"学习产物"出厂前过一遍断言（放宽动作在这里就死掉）
        assert_no_relaxation(self.kind)

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail,
                "requires_human": self.requires_human}


@dataclass
class RuleProposal:
    """"把这条路固化成规则"的**提议** —— 不是规则本身，必须人确认（DL-04/TH-R3）。

    `action` 只允许 `deny`（更严）；`allow` 方向当场抛 `RelaxationForbidden`。
    提议**不落盘**，`accept_proposal` 才是唯一的落地入口（且要求人签字）。
    """

    tool: str
    pattern: str = ""
    action: str = ace_rules.DENY
    scope: str = "local"
    key: Optional[LedgerKey] = None
    count: int = 0
    evidence: Dict[str, Any] = field(default_factory=dict)
    requires_human: bool = True

    def __post_init__(self) -> None:
        act = str(self.action or ace_rules.DENY).strip().lower()
        if act != ace_rules.DENY:
            raise RelaxationForbidden(
                f"规则提议只允许更严（{ace_rules.DENY}）：拿到 {act!r}。"
                "放宽（allow / 提权 / 扩大作用域）只能是人的动作（DL-04）")
        self.action = act
        self.tool = str(self.tool or "").strip()
        self.pattern = str(self.pattern or "")
        self.scope = self.scope if self.scope in ace_rules.SCOPES else "local"
        # "自动固化"不是可选项：这个字段永远为真，免得哪天被顺手改成 False
        self.requires_human = True

    def to_rule(self) -> "ace_rules.Rule":
        """转成既有规则系统认识的 `Rule`（接线 `core/ace_rules.py`）。"""
        return ace_rules.Rule(self.tool, self.pattern, ace_rules.DENY, self.scope)

    def as_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "pattern": self.pattern, "action": self.action,
                "scope": self.scope, "count": self.count,
                "key": self.key.as_dict() if self.key else None,
                "evidence": dict(self.evidence), "requires_human": True}


#: 缺陷的生产者（HL-04 的 `production producer`）：**这条上报必须能指认是谁生产的**，
#: 否则就是 §0.1 那个"归错因"的复发（把规则的问题报成模型的问题）。
_DEFECT_PRODUCERS: Dict[str, str] = {
    REFUSAL_CLASS_POLICY: "规则本身（同一类策略拒绝在多个目标上反复出现 ⇒ 规则不适用，"
                          "不是模型不听话）",
    REFUSAL_CLASS_BOUNDARY: "边界规则/敏感清单（多个目标撞同一面墙 ⇒ 边界画错了位置或"
                            "缺少一条合法路径）",
    REFUSAL_CLASS_CAPABILITY: "运行环境（沙箱/依赖/渠道缺失），不是规则也不是模型",
    REFUSAL_CLASS_MALFORMED: "生成端/上下文长度（截断的确定性复现），不是工具用法错误",
    REFUSAL_CLASS_AUTH_PENDING: "授权流程（同一类授权请求在多个目标上反复出现 ⇒ 该进持久规则）",
    REFUSAL_CLASS_TRANSIENT: "外部依赖抖动（传输层），不是规则",
}


@dataclass
class RuleDefectReport:
    """"规则本身有问题"的上报物料（DL-03 动作④ / HL-L4）。

    它必须**可判定**：`observed`（观测到什么）+ `production_producer`（是谁生产的）
    是最低要求 —— §0.1 那个案例上报了"模型死循环"却给不出生产者，于是修错了地方。
    """

    refusal_class: str
    goals: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    count: int = 0
    observed: str = ""
    production_producer: str = ""
    requires_human: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {"refusal_class": self.refusal_class, "goals": list(self.goals),
                "tools": list(self.tools), "count": self.count,
                "observed": self.observed,
                "production_producer": self.production_producer,
                "requires_human": True}


@dataclass
class RefusalEntry:
    """拒绝账本的一条：同一个键被拒了多少次、什么时候、带什么替代路径。"""

    key: LedgerKey
    tool: str = ""
    count: int = 0
    first_at: str = ""
    last_at: str = ""
    hint: Dict[str, Any] = field(default_factory=dict)
    source: str = ""          # 生产者：这条知识是哪条路径产生的（HL-04 的 producer）
    pattern: str = ""         # 建议固化的最小模式（ace_rules.suggest_rule 的口径）

    def as_dict(self) -> Dict[str, Any]:
        return {"key": self.key.as_dict(), "tool": self.tool, "count": self.count,
                "first_at": self.first_at, "last_at": self.last_at,
                "hint": dict(self.hint), "source": self.source,
                "pattern": self.pattern}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RefusalEntry":
        k = d.get("key") or {}
        return cls(key=LedgerKey(k.get("goal_id", ""), k.get("fingerprint", ""),
                                 k.get("refusal_class", "")),
                   tool=str(d.get("tool") or ""), count=int(d.get("count") or 0),
                   first_at=str(d.get("first_at") or ""),
                   last_at=str(d.get("last_at") or ""),
                   hint=dict(d.get("hint") or {}), source=str(d.get("source") or ""),
                   pattern=str(d.get("pattern") or ""))


# ============================================================
# 拒绝账本（DL-03）：长期 / 跨会话 —— 它是**知识**
# ============================================================

class RefusalLedger:
    """拒绝账本。**从不出熔断/降级/禁用**（那些是失败账本的出口）。

    它的三个消费者：
      · 驱动层要"别再原样重发" → `guidance`（含替代路径）
      · 人要不要把它固化成规则 → `propose_rule` + `accept_proposal(confirmed_by=...)`
      · 规则本身有没有病 → `report_defect`
    """

    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._entries: Dict[LedgerKey, RefusalEntry] = {}
        self._max_entries = max(1, int(max_entries))
        self.proposals: List[RuleProposal] = []
        self.defects: List[RuleDefectReport] = []
        self.load_error = ""

    # ---------- 写 ----------

    def record(self, key: LedgerKey, *, tool: str = "",
               hint: Optional[Dict[str, Any]] = None, source: str = "",
               pattern: str = "", at: Optional[str] = None) -> RefusalEntry:
        """记一条拒绝（同键累加）。返回累加后的条目。"""
        now = at or time.strftime("%Y-%m-%d %H:%M:%S")
        entry = self._entries.get(key)
        if entry is None:
            entry = RefusalEntry(key=key, tool=str(tool or ""),
                                 first_at=now, last_at=now)
            self._entries[key] = entry
        entry.count += 1
        entry.last_at = now
        if tool:
            entry.tool = str(tool)
        if hint:
            entry.hint = {k: (list(v) if isinstance(v, (list, tuple)) else v)
                          for k, v in dict(hint).items()}
        if source:
            entry.source = str(source)
        if pattern and not entry.pattern:
            entry.pattern = str(pattern)
        self._prune()
        return entry

    def _prune(self) -> None:
        """内存上限：超了按 `last_at` 淘汰最旧（有损，所以上限给得很大）。"""
        if len(self._entries) <= self._max_entries:
            return
        ordered = sorted(self._entries.values(), key=lambda e: (e.last_at, str(e.key)))
        for e in ordered[:len(self._entries) - self._max_entries]:
            self._entries.pop(e.key, None)

    # ---------- 读 ----------

    def entry(self, key: LedgerKey) -> Optional[RefusalEntry]:
        return self._entries.get(key)

    def count(self, key: LedgerKey) -> int:
        e = self._entries.get(key)
        return e.count if e else 0

    def keys(self) -> List[LedgerKey]:
        return list(self._entries.keys())

    def entries(self) -> List[RefusalEntry]:
        return list(self._entries.values())

    def total(self) -> int:
        return sum(e.count for e in self._entries.values())

    def is_closed(self, key: LedgerKey) -> bool:
        """这条路是否已被标记"此路不通"（同类够格 + 至少拒过一次）。"""
        return bool(self._entries.get(key)) and class_closes_path(key.refusal_class)

    def distinct_goals(self, refusal_class: str) -> List[str]:
        """这类拒绝出现在**几个不同目标**上（空 goal_id 不算一个目标）。

        动作④的判据不是"拒了多少次"，而是"跨了多少个目标" —— 同一个目标上撞五十次
        面墙只说明模型没转弯（那是动作③的事），跨目标反复出现才说明**墙有问题**。
        """
        cls = str(refusal_class or "").strip().upper()
        return sorted({e.key.goal_id for e in self._entries.values()
                       if e.key.refusal_class == cls and e.key.goal_id})

    def guidance(self, key: LedgerKey,
                 hint: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """回喂给驱动层的结构化指导（动作①+②的合流出口）。"""
        e = self._entries.get(key)
        if e is None:
            return {"closed": False, "count": 0, "message": "",
                    "alternatives": [], "missing": [],
                    "driver_action": driver_action(key.refusal_class)}
        h = hint or e.hint or hint_for(key.refusal_class)
        alts = list(h.get("alternatives") or [])
        missing = list(h.get("missing") or [])
        if class_closes_path(key.refusal_class):
            msg = (f" 这条路已关（{key.refusal_class} · fp={key.fingerprint[:6]} 已被拒 "
                   f"{e.count} 次）：**不要原样重发**；换路径/换实现即可，权限不会因此放宽。")
        else:
            msg = (f" 同类已出现 {e.count} 次（{key.refusal_class} · "
                   f"fp={key.fingerprint[:6]}）→ {driver_action(key.refusal_class)}")
        if alts:
            msg += " 替代路径：" + "；".join(alts)
        if missing:
            msg += " 缺：" + "；".join(missing)
        return {"closed": class_closes_path(key.refusal_class), "count": e.count,
                "message": msg, "alternatives": alts, "missing": missing,
                "driver_action": driver_action(key.refusal_class)}

    # ---------- 学习（DL-03 四种，证据强度升序） ----------

    def _build_proposal(self, key: LedgerKey,
                        threshold: Optional[int] = None) -> Optional[RuleProposal]:
        e = self._entries.get(key)
        if e is None or key.refusal_class not in RULE_PROPOSABLE_CLASSES:
            return None
        n = RULE_PROPOSAL_N if threshold is None else int(threshold)
        if e.count < n:
            return None
        return RuleProposal(
            tool=e.tool or key.refusal_class,
            pattern=e.pattern or ace_rules.suggest_rule(e.tool, {}),
            action=ace_rules.DENY, scope="local", key=key, count=e.count,
            evidence={"tool": e.tool, "fingerprint": key.fingerprint,
                      "refusal_class": key.refusal_class, "goal_id": key.goal_id,
                      "count": e.count, "first_at": e.first_at, "last_at": e.last_at,
                      "source": e.source,
                      "why": "同一意图（同指纹）被同一类拒绝反复挡下 ⇒ 值得固化成规则，"
                             "免得每次会话重新撞一遍"})

    def _build_defect(self, refusal_class: str,
                      threshold: Optional[int] = None) -> Optional[RuleDefectReport]:
        cls = str(refusal_class or "").strip().upper()
        n = CROSS_GOAL_N if threshold is None else int(threshold)
        goals = self.distinct_goals(cls)
        if len(goals) < n:
            return None
        mine = [e for e in self._entries.values() if e.key.refusal_class == cls]
        return RuleDefectReport(
            refusal_class=cls, goals=goals,
            tools=sorted({e.tool for e in mine if e.tool}),
            count=sum(e.count for e in mine),
            observed=(f"{cls} 类拒绝出现在 {len(goals)} 个不同目标上，共 "
                      f"{sum(e.count for e in mine)} 次；涉及工具 {sorted({e.tool for e in mine if e.tool})}"),
            production_producer=_DEFECT_PRODUCERS.get(
                cls, "未知（上报时必须补上生产者，否则就是 §0.1 的归错因）"))

    def propose_rule(self, key: LedgerKey,
                     threshold: Optional[int] = None) -> Optional[RuleProposal]:
        """动作③：够次数就返回一条**deny**提议（人确认后才落地）。

        提议本身每次调用都会返回（让消费者可以反复读），但 `proposals` 里同一个键
        只留一条 —— 学习不该把同一个念头刷屏。
        """
        prop = self._build_proposal(key, threshold)
        if prop is not None and not any(p.key == key for p in self.proposals):
            self.proposals.append(prop)
        return prop

    def report_defect(self, refusal_class: str,
                      threshold: Optional[int] = None) -> Optional[RuleDefectReport]:
        """动作④：同一类拒绝跨目标够多 → 上报"规则本身有问题"。"""
        rep = self._build_defect(refusal_class, threshold)
        if rep is not None and not any(d.refusal_class == rep.refusal_class
                                       for d in self.defects):
            self.defects.append(rep)
        return rep

    def learning_actions(self, key: LedgerKey, *, tool: str = "",
                         hint: Optional[Dict[str, Any]] = None) -> List[LearningAction]:
        """四种学习动作，按证据强度升序；没拒过就什么都不产出。

        关键：**MALFORMED 不产出 `no_resend` / `propose_rule`** ——
        一次截断不该永久禁掉一条路（H-19）。它仍可以带上"重新生成"的替代路径，
        跨目标频繁时也可以上报（生产者在生成端，见 `_DEFECT_PRODUCERS`）。
        """
        e = self._entries.get(key)
        if e is None:
            return []
        cls = key.refusal_class
        out: List[LearningAction] = []
        if class_closes_path(cls):
            out.append(LearningAction(
                LEARNING_ACTION_NO_RESEND,
                f"同指纹同类已被拒 {e.count} 次：回喂『这条路已关』，不要原样重发",
                payload={"key": key.as_dict(), "count": e.count},
                requires_human=False))
        h = hint or e.hint or hint_for(cls)
        if h.get("alternatives") or h.get("missing"):
            out.append(LearningAction(
                LEARNING_ACTION_ALTERNATIVES,
                "带上替代路径/缺什么（拒绝不是终点）",
                payload={"alternatives": list(h.get("alternatives") or []),
                         "missing": list(h.get("missing") or [])},
                requires_human=False))
        prop = self._build_proposal(key)
        if prop is not None:
            out.append(LearningAction(
                LEARNING_ACTION_PROPOSE_RULE,
                f"同指纹被拒 {prop.count} 次 → 提议固化成规则（{prop.action} "
                f"{prop.tool}:{prop.pattern or '*'} @{prop.scope}）",
                payload=prop, requires_human=True))
        rep = self._build_defect(cls)
        if rep is not None:
            out.append(LearningAction(
                LEARNING_ACTION_REPORT_DEFECT,
                f"{cls} 跨 {len(rep.goals)} 个目标反复出现 → 上报规则缺陷（人裁决）",
                payload=rep, requires_human=True))
        # 顺序是契约（DL-03：按证据强度升序），别按插入顺序碰运气
        order = {k: i for i, k in enumerate(LEARNING_ACTION_ORDER)}
        out.sort(key=lambda a: order.get(a.kind, 99))
        return out

    # ---------- 固化（唯一落地入口：必须人确认） ----------

    def accept_proposal(self, proposal: RuleProposal, confirmed_by: str,
                        save_path: str = "") -> Optional["ace_rules.Rule"]:
        """人确认后把提议变成规则；`save_path` 给了就顺手写进既有规则文件。

        `confirmed_by` 为空 ⇒ 抛 `RelaxationForbidden`。这是 DL-04 的"放宽只能是人的
        动作"在**固化**这一步的落点：账本自己永远不会调用它。
        """
        if not str(confirmed_by or "").strip():
            raise RelaxationForbidden(
                "固化规则必须由人确认（confirmed_by 不能为空）："
                "学习只能**提议**，把提议变成规则是人的动作（DL-04/TH-R3）")
        rule = proposal.to_rule()
        if save_path:
            existing, _warns = ace_rules.load_rules_file(str(save_path), proposal.scope)
            existing = [r for r in existing
                        if not (r.tool == rule.tool and r.pattern == rule.pattern)]
            existing.append(rule)
            ace_rules.save_rules(existing, str(save_path))
        return rule

    # ---------- 落盘（跨会话 = 它是知识） ----------

    def as_dict(self) -> Dict[str, Any]:
        return {"version": 1,
                "entries": [e.as_dict() for e in self._entries.values()]}

    def save(self, path: str) -> bool:
        """原子写（临时文件 + replace）：崩溃不产生半截账本。"""
        try:
            p = os.path.abspath(str(path))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.as_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
            return True
        except OSError:
            return False

    @classmethod
    def load(cls, path: str) -> "RefusalLedger":
        """读回一份长期账本。文件缺失/读坏 → 空账本 + `load_error`（不炸会话）。

        为什么"读坏就当空"在这里可以接受：它是**知识**的缓存，不是闸门 ——
        读不出来只损失"少知道几条被拒过的路"，不会放行任何东西（方向朝安全）。
        """
        led = cls()
        try:
            if not os.path.isfile(str(path)):
                return led
            with open(str(path), "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in (data.get("entries") if isinstance(data, dict) else data) or []:
                if isinstance(raw, dict):
                    e = RefusalEntry.from_dict(raw)
                    led._entries[e.key] = e
        except (OSError, ValueError, TypeError) as exc:
            led.load_error = f"{type(exc).__name__}: {exc}"
            led._entries.clear()
        return led

    def clear(self) -> None:
        """清空（知识账本平时**不该**清；只有测试/显式重来才用）。"""
        self._entries.clear()
        self.proposals.clear()
        self.defects.clear()


# ============================================================
# 失败账本（HL-01）：短期 / 本会话 —— 它是**状态**
# ============================================================

@dataclass
class FailureEntry:
    key: LedgerKey
    tool: str = ""
    count: int = 0
    threshold: int = LADDER_BREAKER_N
    first_at: str = ""
    last_at: str = ""
    level: str = LADDER_L0_RETRY

    @property
    def banned(self) -> bool:
        return self.count >= self.threshold


class FailureLedger:
    """失败账本。**故意没有 `save`/`load`** —— 会话结束即清是它的语义（§4）。

    它回答的问题只有一个："现在该升到哪一级"。所以出口是 `ladder_step` 的结果 +
    `is_fingerprint_banned`（L2 的硬闸门）。它**不产出**规则提议（那是知识的事）。
    """

    def __init__(self) -> None:
        self._entries: Dict[LedgerKey, FailureEntry] = {}
        self._tool_bans: Set[str] = set()      # 兼容/手工按工具名禁用（生产路径不用）
        self._views: List[Any] = []

    # ---------- 写 ----------

    def record(self, key: LedgerKey, *, tool: str = "",
               threshold: Optional[int] = None, cross_goals: int = 0,
               budget_exhausted: bool = False,
               at: Optional[str] = None) -> Optional[FailureEntry]:
        """记一次失败；`MALFORMED` 返回 None（HL-03 硬规则① / H-19）。

        为什么第二道门放在账本里（`_note_tool_failure` 已经挡过一次）："唯一的计数
        入口"这个说法只有在**入口本身拒绝**时才成立。哪天有人从别处直接调账本，
        截断照样进不来。
        """
        if key.refusal_class == REFUSAL_CLASS_MALFORMED:
            return None
        now = at or time.strftime("%Y-%m-%d %H:%M:%S")
        entry = self._entries.get(key)
        if entry is None:
            entry = FailureEntry(key=key, tool=str(tool or ""),
                                 first_at=now, last_at=now)
            self._entries[key] = entry
        if tool:
            entry.tool = str(tool)
        if threshold is not None:
            entry.threshold = max(1, int(threshold))
        entry.count += 1
        entry.last_at = now
        entry.level = ladder_step(
            refusal_class=key.refusal_class, fingerprint_count=entry.count,
            tool_count=self.tool_count(entry.tool), cross_goals=cross_goals,
            budget_exhausted=budget_exhausted, breaker_n=entry.threshold)
        self._sync()
        return entry

    def clear_tool(self, tool: str) -> int:
        """清掉某个工具的全部失败计数（成功推进时只清自己那份）。返回清掉的条数。"""
        name = str(tool or "")
        gone = [k for k, e in self._entries.items() if e.tool == name]
        for k in gone:
            self._entries.pop(k, None)
        self._tool_bans.discard(name)
        self._sync()
        return len(gone)

    def unban_tool(self, tool: str) -> None:
        """按工具名解禁（兼容视图 `discard`）：清掉该工具被禁的指纹 + 工具级禁用。"""
        name = str(tool or "")
        self._tool_bans.discard(name)
        for k in [k for k, e in self._entries.items()
                  if e.tool == name and e.banned]:
            self._entries.pop(k, None)
        self._sync()

    def ban_tool_legacy(self, tool: str) -> None:
        """兼容视图的 `add`：按工具名禁用（**生产路径禁用指纹，不用这个**）。"""
        name = str(tool or "").strip()
        if name:
            self._tool_bans.add(name)
        self._sync()

    def unban_all(self) -> None:
        """全部解禁（兼容视图的 `clear`）：计数与工具级禁用一起归零。"""
        self._tool_bans.clear()
        self._entries.clear()
        self._sync()

    def clear(self) -> None:
        """会话结束即清（状态不留到下一个会话）。"""
        self._entries.clear()
        self._tool_bans.clear()
        self._sync()

    # ---------- 读 ----------

    def entry(self, key: LedgerKey) -> Optional[FailureEntry]:
        return self._entries.get(key)

    def entries(self) -> List[FailureEntry]:
        return list(self._entries.values())

    def count(self, key: LedgerKey) -> int:
        e = self._entries.get(key)
        return e.count if e else 0

    def tool_count(self, tool: str) -> int:
        """同工具失败**总次数**（HL-L3 的"同工具第 5 次"判据）。"""
        name = str(tool or "")
        return sum(e.count for e in self._entries.values() if e.tool == name)

    def is_fingerprint_banned(self, goal_id: str, fingerprint: str) -> bool:
        """这条路（指纹）在这个目标下是否已熔断 —— **熔断的是指纹，不是工具**。"""
        g, fp = str(goal_id or ""), str(fingerprint or "")
        return any(e.banned and e.key.goal_id == g and e.key.fingerprint == fp
                   for e in self._entries.values())

    def is_tool_banned(self, tool: str) -> bool:
        return str(tool or "") in self._tool_bans

    def banned_fingerprints(self, goal_id: str) -> Set[str]:
        g = str(goal_id or "")
        return {e.key.fingerprint for e in self._entries.values()
                if e.banned and e.key.goal_id == g}

    def banned_tools(self) -> Set[str]:
        """兼容视图：被禁指纹所属的**工具名**集合（+ 手工工具级禁用）。

        为什么保留工具名这一层：既有断言按工具名读 `banned_tools`（`test_all [10]`/
        `[79]`），而**闸门**只认指纹 —— 视图给人看，闸门认路，两者不混。
        """
        names = {e.tool for e in self._entries.values() if e.banned and e.tool}
        return names | set(self._tool_bans)

    def as_repeat_fail(self) -> Dict[str, int]:
        """兼容视图：`{f"{tool}:{fingerprint}:{class}": count}`。

        键仍以 `f"{tool}:"` 开头 —— 既有断言 `k.startswith("ask_user:")` 的读法不变；
        中间两截就是 HL-01 要的键空间（工具不再是键的全部）。
        """
        return {f"{e.tool}:{e.key.fingerprint}:{e.key.refusal_class}": e.count
                for e in self._entries.values()}

    # ---------- 兼容视图同步 ----------

    def attach(self, view: Any) -> None:
        self._views.append(view)

    def _sync(self) -> None:
        for v in list(self._views):
            try:
                v.refresh()
            except Exception:      # noqa: BLE001 —— 视图刷新失败不该影响账本
                pass


class RepeatFailView(dict):
    """`ExecutionLayer.repeat_fail` 的兼容视图（是 dict，读法一字不改）。

    它是**同一份状态**的窗口，不是副本：`view.clear()` 真的清账本。
    这样 `test_all [10]` 的 `repeat_fail.clear()` 与 `banned_tools.discard(...)` 仍然
    是"操作真状态"，不会出现"测试清了视图、闸门还认旧账"的假绿。
    """

    def __init__(self, ledger: FailureLedger) -> None:
        super().__init__()
        self._ledger = ledger
        ledger.attach(self)
        self.refresh()

    def refresh(self) -> None:
        dict.clear(self)
        dict.update(self, self._ledger.as_repeat_fail())

    def clear(self) -> None:                     # type: ignore[override]
        self._ledger.clear()

    def copy(self) -> Dict[str, int]:            # type: ignore[override]
        return dict(self)

    def __repr__(self) -> str:
        return repr(dict(self))


class BannedToolsView(set):
    """`ExecutionLayer.banned_tools` 的兼容视图（是 set，`in` / `discard` 照旧）。"""

    def __init__(self, ledger: FailureLedger) -> None:
        super().__init__()
        self._ledger = ledger
        ledger.attach(self)
        self.refresh()

    def refresh(self) -> None:
        set.clear(self)
        set.update(self, self._ledger.banned_tools())

    def discard(self, tool: str) -> None:        # type: ignore[override]
        self._ledger.unban_tool(tool)

    def add(self, tool: str) -> None:            # type: ignore[override]
        self._ledger.ban_tool_legacy(tool)

    def clear(self) -> None:                     # type: ignore[override]
        self._ledger.unban_all()

    def __repr__(self) -> str:
        return repr(set(self))
