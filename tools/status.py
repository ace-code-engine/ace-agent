#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.status —— 错误码/状态码唯一目录(Q-10)

契约:
  · 对模型/用户暴露的 `ExecutionResult.error_code` 只允许使用本文件集合中的值;
  · 新增错误码:先在下方登记常量并加入 ERROR_CODES,再使用;
  · `test_all.py` 的 AST 守卫会拒绝代码库中未登记的散落字面量(防漂移)。
  · 数字串语义:400 参数错 · 403 权限/越界/敏感目标/策略拒绝 · 404 不存在 ·
    409 歧义 · 500 内部失败 · 501 未实现/缺渠道 · 503 沙箱档不可用(不静默回退) · 504 超时。

## 另外一件事:`outcome`(机器通道的闭集)

`ExecutionResult.outcome` 是 **THREE-LAYERS RL-01 结果信封**里的机器通道字段,
它回答的问题与 `status` **不是同一个**:

> **`status` 说"发生了什么"(给人看),`outcome` 说"下一步该干什么"(给驱动层判)。**

为什么必须有它:`THREE-LAYERS` §0.2 的病根是**"拒绝"与"失败"被塞进同一个计数器** ——
于是"被策略挡下"(= 此路不通的**知识**)与"事情没成"(= 该升级的**状态**)在驱动层眼里
一模一样。`outcome` 是那个拆开它们的最小闭集。

**它同样受本文件的登记纪律约束**:先登记常量、再加进 `OUTCOMES`,然后才能用。
"""

from typing import Dict, Final, FrozenSet, Tuple

ERROR_BAD_REQUEST: Final[str] = "400"
ERROR_FORBIDDEN: Final[str] = "403"
ERROR_NOT_FOUND: Final[str] = "404"
ERROR_CONFLICT: Final[str] = "409"
ERROR_INTERNAL: Final[str] = "500"
ERROR_NOT_IMPLEMENTED: Final[str] = "501"
ERROR_SANDBOX_UNAVAILABLE: Final[str] = "503"
ERROR_TIMEOUT: Final[str] = "504"

ERROR_CODES: FrozenSet[str] = frozenset({
    ERROR_BAD_REQUEST, ERROR_FORBIDDEN, ERROR_NOT_FOUND, ERROR_CONFLICT,
    ERROR_INTERNAL, ERROR_NOT_IMPLEMENTED, ERROR_SANDBOX_UNAVAILABLE,
    ERROR_TIMEOUT,
})

# ============================================================
# outcome —— 机器通道的**闭集**（THREE-LAYERS RL-01）
# ============================================================

OUTCOME_SUCCESS: Final[str] = "success"    # 事情成了
OUTCOME_DENIED: Final[str] = "denied"      # **被拒**：执行层正常工作、策略生效了（是知识，不是状态）
OUTCOME_FAILED: Final[str] = "failed"      # 事情**没成**（该升级了）
OUTCOME_PARTIAL: Final[str] = "partial"    # 成了一半（**尚无生产者** —— RL-03 三段式回传时才有）
OUTCOME_DEFERRED: Final[str] = "deferred"  # 挂在等人/等条件上（**不是失败**，别拿它去熔断）

OUTCOMES: FrozenSet[str] = frozenset({
    OUTCOME_SUCCESS, OUTCOME_DENIED, OUTCOME_FAILED, OUTCOME_PARTIAL,
    OUTCOME_DEFERRED,
})

#: 这些**外发状态**属于"被拒"一档：执行层的门正常工作了，重试同一条路不会有别结果。
#: 注意 `PERMISSION_REQUEST` 在 `denied` 里 —— 它**不是失败**（`THREE-LAYERS` RL-02
#: 把它单列成 `AUTH_PENDING`："停下等人"），但在"别原样重发"这一点上与拒绝同向。
_DENIED_STATUSES: Final[FrozenSet[str]] = frozenset({
    "PERMISSION_REQUEST", "GUARD_VIOLATION", "TOOL_BANNED", "BAIT_TRIGGERED",
    "AST_FAILED", "HOOK_BLOCKED", ERROR_FORBIDDEN,
})

#: 挂在等外部条件/等人上的状态：**不是失败**，不该计进失败账本。
#: `ASK_USER`（WP-1 ask_user 工具）也是"停下等人"—— 模型主动提问、等用户文本答案。
_DEFERRED_STATUSES: Final[FrozenSet[str]] = frozenset({
    "PLAN_PENDING", "PLAN_PROPOSED", "PLAN_ALREADY_APPROVED", "ASK_USER",
})

#: 不是"工具执行结果"的那些外发状态（回合级/协议级），它们成功即 `success`。
_OK_STATUSES: Final[FrozenSet[str]] = frozenset({"SUCCESS", "FINAL_REPLY", "success"})


def outcome_for(status: str, error_code: str = "") -> str:
    """把**人通道**的 `status`/`error_code` 映射成机器通道的 `outcome`（闭集之一）。

    这张表是"拒绝 vs 失败"的**唯一判定处** —— 别在调用点各写一遍 `if error_code == "403"`。

    规则（按优先级）：
      1. `SUCCESS` / `FINAL_REPLY` / `"success"` → `success`
      2. 被拒那一档（`_DENIED_STATUSES`，含 **403** 与 `PERMISSION_REQUEST`）→ `denied`
      3. 挂起那一档（`_DEFERRED_STATUSES`）→ `deferred`
      4. 其余（400/404/409/500/501/503/504、`FORMAT_ERROR`、`ERROR`…）→ `failed`

    **永远返回闭集里的值**：认不出的一律落 `failed`（"没成"），
    **绝不落 `success`** —— 认不出却报成功是这里最危险的失败方向。
    """
    s = str(status or "").strip().upper()
    code = str(error_code or "").strip()
    if s in {x.upper() for x in _OK_STATUSES}:
        return OUTCOME_SUCCESS
    if s in _DENIED_STATUSES or code == ERROR_FORBIDDEN:
        return OUTCOME_DENIED
    if s in _DEFERRED_STATUSES:
        return OUTCOME_DEFERRED
    return OUTCOME_FAILED


# ============================================================
# refusal class —— 拒绝六分类（THREE-LAYERS RL-02）
# ============================================================
#
# RL-01 的 `outcome` 拆开了"拒绝 vs 失败"；RL-02 再往前一步：**拒绝**里再分六类，
# 每一类给驱动层**唯一**的处置动作（`THREE-LAYERS` §2.3 那张表就是全部契约）。
# 与 `outcome`/`error_code` 同一条登记纪律：先登记常量、加进 `REFUSAL_CLASSES`，再使用。

REFUSAL_CLASS_POLICY: Final[str] = "POLICY"             # 策略/黑名单拒绝 → **换路径**，别重试
REFUSAL_CLASS_BOUNDARY: Final[str] = "BOUNDARY"         # 越界/敏感目标/不可逆 → **换路径**；同指纹再犯→提议固化
REFUSAL_CLASS_AUTH_PENDING: Final[str] = "AUTH_PENDING"  # 需要人授权 → **停下等人**（不是失败）
REFUSAL_CLASS_CAPABILITY: Final[str] = "CAPABILITY"     # 环境/能力缺失（503/501）→ **降级并声明 / 上报**
REFUSAL_CLASS_TRANSIENT: Final[str] = "TRANSIENT"       # 超时/抖动/429 → **退避重试**
REFUSAL_CLASS_MALFORMED: Final[str] = "MALFORMED"       # 输出畸形/截断 → **重新生成**，永不计入熔断

REFUSAL_CLASSES: FrozenSet[str] = frozenset({
    REFUSAL_CLASS_POLICY, REFUSAL_CLASS_BOUNDARY, REFUSAL_CLASS_AUTH_PENDING,
    REFUSAL_CLASS_CAPABILITY, REFUSAL_CLASS_TRANSIENT, REFUSAL_CLASS_MALFORMED,
})

#: "策略/守门"那一类拒绝：执行层的门正常工作、按策略挡下（与 BOUNDARY 的"越界"不同）。
_POLICY_STATUSES: Final[FrozenSet[str]] = frozenset({
    "GUARD_VIOLATION", "TOOL_BANNED", "BAIT_TRIGGERED", "AST_FAILED", "HOOK_BLOCKED",
})

#: retryable 为真的只有两类：退避重试（TRANSIENT）与重新生成（MALFORMED）。
_RETRYABLE_CLASSES: Final[FrozenSet[str]] = frozenset({
    REFUSAL_CLASS_TRANSIENT, REFUSAL_CLASS_MALFORMED,
})


def classify_refusal(status: str, error_code: str = "") -> str:
    """把 `status`/`error_code` 映射成**拒绝六分类**之一；成功/挂起 → `""`（无处置类）。

    这张表是 RL-02「响应层 → 驱动层」全部契约的唯一判定处 —— 每类只有一个动作，互不重叠。
    与 `outcome_for` 同一条纪律：认不出的**拒绝**路径必须在这里归类（TH-R1），
    认不出的**失败**落 `""`（保守：不知道能不能重试就**不自动重试**）。
    """
    s = str(status or "").strip().upper()
    code = str(error_code or "").strip()
    if s in {x.upper() for x in _OK_STATUSES}:
        return ""                                   # 成功：无处置类
    if s in _DEFERRED_STATUSES:
        return ""                                   # 挂起：停下等人，但没有"拒绝类"
    if s == "PERMISSION_REQUEST":
        return REFUSAL_CLASS_AUTH_PENDING
    if s in _POLICY_STATUSES:
        return REFUSAL_CLASS_POLICY
    if code == ERROR_FORBIDDEN:
        return REFUSAL_CLASS_BOUNDARY
    if code in (ERROR_SANDBOX_UNAVAILABLE, ERROR_NOT_IMPLEMENTED):
        return REFUSAL_CLASS_CAPABILITY
    if code == ERROR_TIMEOUT:
        return REFUSAL_CLASS_TRANSIENT
    if s == "FORMAT_ERROR":
        return REFUSAL_CLASS_MALFORMED
    return ""                                       # 其余失败(400/404/409/500…)：无更细的类


def retryable_for(refusal_class: str) -> bool:
    """该类是否该重试：只有 TRANSIENT（退避重试）与 MALFORMED（重新生成）为真。"""
    return str(refusal_class or "").strip().upper() in _RETRYABLE_CLASSES


# ============================================================
# HL-03 三条硬规则（THREE-LAYERS §3.4）—— 契约的唯一判定处
# ============================================================
#
# 三条规则**全部来自现有 bug**，所以它们必须是契约，不能只活在实现细节里 ——
# 实现细节会被下一个改这段代码的人顺手改掉，契约不会（它被断言钉住）：
#
#   ① `MALFORMED` 永不计入熔断 —— H-19 血证（`agent_runner.py:93-104`）：被
#      `max_tokens` 截断时工具调用 JSON 未闭合 → `args` 退化成 `{}` → 报 400 →
#      计进"同工具同错误连续失败" → 3 次后**该工具被整会话熔断**。而每次回喂的
#      prompt 都在变长，截断是**确定性复现**的 —— 模型永远修不好、工具永远被禁。
#      截断与畸形是"重新生成"的事，不是"升级处置"的事。
#   ② 降级必须声明，不许静默回退 —— 本文件 `:10` 已经把 503 定义为"沙箱档不可用
#      （**不静默回退**）"；这条语义扩到**全部**降级路径：每一次降级都要有一个
#      可观测的出口（结果字段 / 事件日志 / stderr 一行）。
#   ③ 降级方向只朝"更严" —— 与 `ROADMAP` WP-9 同一条：沙箱不可达时降级到**拒绝**，
#      **绝不**降级到本地无边界执行（静默回退比没有沙箱更危险：用户以为命令跑在
#      容器里，实际跑在自己机器上）。


def counts_toward_breaker(status: str, error_code: str = "") -> bool:
    """这个结果许不许增加 `(tool, error)` 熔断计数（HL-03 硬规则①）。

    **`MALFORMED` 永不计入熔断**：判据直接复用 `classify_refusal`（唯一判定处），
    禁止在调用点各写一遍 `if status == "FORMAT_ERROR"` —— 那正是会让新路径漏掉的
    写法（H-19 就是漏在"没人把截断与参数错误分开"）。

    为什么这条住在 `status.py` 而不是 `execution_layer.py`：`FORMAT_ERROR →
    MALFORMED` 的映射在本文件，熔断计数只是它的**消费方**；映射改了而消费方没跟上，
    就是 H-19 复发。
    """
    return classify_refusal(status, error_code) != REFUSAL_CLASS_MALFORMED


#: 降级**允许**去的方向（HL-03 硬规则③），只有两档，都比原状更严：
DEGRADE_TO_DENY: Final[str] = "deny"          # 拒绝本次调用（沙箱不可达 / 快照不可用）
DEGRADE_TO_LIMITED: Final[str] = "limited"    # 受限执行（降权 / 逐次确认 / 只读面）
DEGRADATION_TARGETS_STRICTER: FrozenSet[str] = frozenset({
    DEGRADE_TO_DENY, DEGRADE_TO_LIMITED,
})

#: 明令**禁止**的降级目标：本地无边界执行。拿不到边界就拒绝，绝不偷偷改回宿主
#: （`agent_runner.py` / `tools/terminal_exec.py` / `tools/code_tools.py` 的 503 都是它）。
DEGRADE_TO_UNBOUNDED_LOCAL: Final[str] = "unbounded_local_exec"


def degradation_direction_ok(target: str) -> bool:
    """该降级目标是不是"更严"那两档（HL-03 硬规则③）。

    这是规则③的**闭集判定处**：新增降级点必须在这里被判过，而不是靠"这次看起来
    没问题"。`unbounded_local_exec` 永远不在集合里 —— 它是 503 那条路要拒绝的东西。
    """
    return str(target or "").strip() in DEGRADATION_TARGETS_STRICTER


# ============================================================
# HL-02 五级升级阶梯（THREE-LAYERS §3.3）—— 契约的唯一判定处
# ============================================================
#
# 阶梯回答的是 HL-01 失败账本的问题："现在该升到哪一级"（§4 的失败账本出口：
# 熔断 / 降级 / 上报）。它与 `REFUSAL_CLASSES` 一样受**登记纪律**约束：先登记常量、
# 再加进 `LADDER_LEVELS` / `LADDER_ACTIONS`，然后才能用。
#
# 为什么档位和动作要住在这里而不是 `core/ace_ledgers.py`：账本负责**数**，
# 阶梯的语义（每级唯一动作、档位高低、阈值）是契约 —— 与 `outcome_for` 同一条纪律，
# 换实现的人不该顺手把"L2 熔断"改成"再试一次"。

LADDER_L0_RETRY: Final[str] = "L0"        # 重试：TRANSIENT（退避重试）
LADDER_L1_REROUTE: Final[str] = "L1"      # 换路径：POLICY/BOUNDARY 首次（回传替代路径）
LADDER_L2_BREAKER: Final[str] = "L2"      # 熔断：同 fp+class 第 3 次 → 禁掉**这个指纹**
LADDER_L3_DEGRADE: Final[str] = "L3"      # 降级：同工具第 5 次 / CAPABILITY → 降级并声明
LADDER_L4_ESCALATE: Final[str] = "L4"     # 上报：同 class 跨目标 ≥N / 预算耗尽 → 停下问人

#: 有序（低 → 高）：`ladder_highest` 与单调性断言都读这个顺序，别按字典序猜。
LADDER_LEVELS: Final[Tuple[str, ...]] = (
    LADDER_L0_RETRY, LADDER_L1_REROUTE, LADDER_L2_BREAKER,
    LADDER_L3_DEGRADE, LADDER_L4_ESCALATE,
)

LADDER_ACTION_RETRY: Final[str] = "retry"
LADDER_ACTION_REROUTE: Final[str] = "reroute"
LADDER_ACTION_BREAKER: Final[str] = "breaker"
LADDER_ACTION_DEGRADE: Final[str] = "degrade"
LADDER_ACTION_ESCALATE: Final[str] = "escalate"

#: 每级**唯一**动作（§3.3 那张表的"动作"列）。五级五个动作，不许重叠。
LADDER_ACTIONS: Final[Dict[str, str]] = {
    LADDER_L0_RETRY: LADDER_ACTION_RETRY,
    LADDER_L1_REROUTE: LADDER_ACTION_REROUTE,
    LADDER_L2_BREAKER: LADDER_ACTION_BREAKER,
    LADDER_L3_DEGRADE: LADDER_ACTION_DEGRADE,
    LADDER_L4_ESCALATE: LADDER_ACTION_ESCALATE,
}

#: 阈值（写在这里让"第 3 次/第 5 次/跨 N 个目标"可被断言，不散在实现里）
LADDER_BREAKER_N: Final[int] = 3          # 同 (goal, fingerprint, class) 第 3 次 → L2
LADDER_DEGRADE_TOOL_N: Final[int] = 5     # 同工具第 5 次 → L3
LADDER_CROSS_GOAL_N: Final[int] = 3       # 同 class 跨目标 ≥3 → L4


def ladder_action(level: str) -> str:
    """该档位的唯一动作；认不出的档位返回 `""`（**绝不**默认成"重试"）。"""
    return LADDER_ACTIONS.get(str(level or "").strip(), "")


def ladder_rank(level: str) -> int:
    """档位高低（L0=0 … L4=4）；认不出的返回 -1。

    为什么要有它：阶梯的核心契约是**单调**（只升不降）—— 没有 rank 就只能靠字符串
    比较，"L10 < L2" 这种字典序错误正是这类实现翻过车的地方。
    """
    try:
        return LADDER_LEVELS.index(str(level or "").strip())
    except ValueError:
        return -1


def ladder_highest(*levels: str) -> str:
    """取最高的那一档（多个触发条件同时命中时用）。

    全部认不出时返回 `LADDER_L0_RETRY`：基线是"不升级"。
    **不会**因为"认不出"就跳到 L4 —— 那是把 bug 当上报，报出来的因是错的（§0.1）。
    """
    best, best_rank = LADDER_L0_RETRY, -1
    for lv in levels:
        r = ladder_rank(lv)
        if r > best_rank:
            best, best_rank = str(lv), r
    return best


#: 六类拒绝 → 驱动层**唯一**动作（RL-02 §2.3 那张表）。这张表与 `classify_refusal`
#: 是同一份契约的两半：前者说"是哪一类"，这里说"这一类该怎么办"。
DRIVER_ACTIONS: Final[Dict[str, str]] = {
    REFUSAL_CLASS_POLICY: "reroute",           # 换路径，别重试
    REFUSAL_CLASS_BOUNDARY: "reroute",         # 换路径；同指纹再犯 → 提议固化
    REFUSAL_CLASS_AUTH_PENDING: "await_human",  # 停下等人（**不是失败**）
    REFUSAL_CLASS_CAPABILITY: "degrade_or_report",   # 降级并声明，或上报
    REFUSAL_CLASS_TRANSIENT: "backoff_retry",  # 退避重试
    REFUSAL_CLASS_MALFORMED: "regenerate",     # 重新生成；永不计入熔断
}

#: "此路已关"的类：被拒之后**不该原样重发**（DL-03 学习动作①）。
#: `AUTH_PENDING` 不在里面 —— 它在等人授权，路**还没判死**（等到了就能走）；
#: `TRANSIENT`/`MALFORMED` 也不在 —— 它们是"再来一次"，不是"换条路"。
CLOSED_PATH_CLASSES: Final[FrozenSet[str]] = frozenset({
    REFUSAL_CLASS_POLICY, REFUSAL_CLASS_BOUNDARY, REFUSAL_CLASS_CAPABILITY,
})

#: 允许**提议固化规则**的类（DL-03 学习动作③）。只有"策略/越界"这两类才有
#: 一条**规则**可固化；能力缺失该去修环境（CAPABILITY），等人授权该去问人
#: （AUTH_PENDING），畸形该去重新生成（MALFORMED）。
RULE_PROPOSABLE_CLASSES: Final[FrozenSet[str]] = frozenset({
    REFUSAL_CLASS_POLICY, REFUSAL_CLASS_BOUNDARY,
})


def driver_action(refusal_class: str) -> str:
    """该拒绝类的驱动层唯一动作；不是拒绝类（成功/挂起/未分类失败）返回 `""`。"""
    return DRIVER_ACTIONS.get(str(refusal_class or "").strip().upper(), "")


def class_closes_path(refusal_class: str) -> bool:
    """这类拒绝是否意味着"这条路已关"（决定 DL-03 动作①是否触发）。"""
    return str(refusal_class or "").strip().upper() in CLOSED_PATH_CLASSES


# ============================================================
# DL-04 学习动作契约（THREE-LAYERS §1.5 / NG-D2）—— 硬约束 S-1
# ============================================================
#
# **拒绝账本的学习结果只允许产出两种东西**：
#   ① 更严的规则（提议固化，**由人确认**）；
#   ② 更会绕的路径（换实现，不改权限）。
# **绝不允许**任何形式的老化自动放宽（例如"被拒 3 次后自动批准"）。
#
# 为什么写成断言而不是注释：H-19 那次是"没人把截断与参数错误分开"，
# 而"自动放宽"这一类事故的共性正是**它在某次重构里被顺手加进来、且看起来很像好心**。
# 这里把"学习动作"做成**闭集**：认不出的动作 `learning_action_ok` 一律 False，
# `assert_no_relaxation` 对已知的放宽动作当场抛异常。

LEARNING_ACTION_NO_RESEND: Final[str] = "no_resend"        # ① 不再原样重发（回喂"此路已关"）
LEARNING_ACTION_ALTERNATIVES: Final[str] = "alternatives"  # ② 给替代路径（hint 的出口）
LEARNING_ACTION_PROPOSE_RULE: Final[str] = "propose_rule"  # ③ 提议固化规则（人确认）
LEARNING_ACTION_REPORT_DEFECT: Final[str] = "report_defect"  # ④ 上报规则缺陷（人裁决）

#: 证据强度升序 —— 顺序本身是契约（DL-03 说"四种，按证据强度升序"）。
LEARNING_ACTION_ORDER: Final[Tuple[str, ...]] = (
    LEARNING_ACTION_NO_RESEND, LEARNING_ACTION_ALTERNATIVES,
    LEARNING_ACTION_PROPOSE_RULE, LEARNING_ACTION_REPORT_DEFECT,
)
LEARNING_ACTIONS: Final[FrozenSet[str]] = frozenset(LEARNING_ACTION_ORDER)

#: 明令禁止的"学习"产物：放宽权限/自动批准/放宽规则。它们在**闭集之外**，
#: 所以就算有人把其中一个塞进学习路径，`learning_action_ok` 也会当场判 False。
RELAXING_ACTIONS: Final[FrozenSet[str]] = frozenset({
    "auto_approve", "auto_allow", "grant_permission", "widen_scope",
    "relax_rule", "auto_relax", "downgrade_guard",
})


class RelaxationForbidden(AssertionError):
    """有人试图让"学习"去**自动放宽**权限/规则 —— DL-04 硬约束 S-1。

    继承 `AssertionError`：它是**断言**，不是可恢复的业务错误（`--optimize` 下
    不许被优化掉的那种语义边界，这里用显式抛出来钉住）。
    """


def learning_action_ok(action: str) -> bool:
    """这个"学习产物"是否合法（闭集内 + 不在放宽名单里）。

    **认不出一律 False**：放行一个认不出的动作，等于给"自动放宽"留了一道后门。
    """
    a = str(action or "").strip()
    return a in LEARNING_ACTIONS and a not in RELAXING_ACTIONS


def assert_no_relaxation(action: str) -> None:
    """DL-04 的断言：放宽动作当场抛 `RelaxationForbidden`。

    放宽**只能是人的动作**（改配置/改规则文件/授权），不能是账本学习的结果。
    """
    if not learning_action_ok(action):
        raise RelaxationForbidden(
            f"学习结果不允许是 {action!r}：DL-04 只允许更严的规则（提议固化、人确认）"
            f"或更会绕的路径（换实现、不改权限）；放宽只能是人的动作。"
            f"合法学习动作：{sorted(LEARNING_ACTIONS)}")


# ============================================================
# WP-6 S-1：**预设只许更严或相等** —— 与 DL-04 同一个判定处
# ============================================================
#
# DL-04 管的是"**学习**产物不许放宽"（上面那一段）；WP-6 管的是"**预设文件**不许
# 放宽"（`docs/design/WP-6-AGENT-PRESETS.md` §二）。两者是**同一条硬约束 S-1**
# 的两个入口，所以共用同一个异常类 `RelaxationForbidden`、同一处判定（本文件）——
# 不新开第二套判定/异常，免得两处判据哪天走岔（那正是 S-1 想防的事）。
#
# 预设文件本身**不是放宽入口**：想放宽得改全局配置或持久规则，那两样都是人写的。

PERMISSION_ACTION_ALLOW: Final[str] = "allow"
PERMISSION_ACTION_ASK: Final[str] = "ask"
PERMISSION_ACTION_DENY: Final[str] = "deny"

#: 预设四维的取值闭集（`read`/`edit`/`webfetch`/`bash` 四维共用这一套值）。
PERMISSION_ACTIONS: Final[Tuple[str, ...]] = (
    PERMISSION_ACTION_ALLOW, PERMISSION_ACTION_ASK, PERMISSION_ACTION_DENY,
)

#: 严格度：**越大越严**。S-1 的比较只有这一条（`allow < ask < deny`），
#: 任何"更松"的写法都落成 `strictness(预设) < strictness(全局)`。
PERMISSION_STRICTNESS: Final[Dict[str, int]] = {
    PERMISSION_ACTION_ALLOW: 0,
    PERMISSION_ACTION_ASK: 1,
    PERMISSION_ACTION_DENY: 2,
}


def permission_relaxes(preset_value: str, global_value: str) -> bool:
    """预设值是否比全局值**更松**（WP-6 S-1）。认不出的值一律按"更松"处理。

    为什么认不出要按更松算：`deny` 与 `ask` 之间差的是"要不要问人"，
    放行一个我们读不懂的值 = 默认不问人 —— 方向朝松，且是静默的。
    """
    p = str(preset_value or "").strip().lower()
    g = str(global_value or "").strip().lower()
    if g not in PERMISSION_STRICTNESS:
        return True                     # 全局值都认不出 ⇒ 不比它松是做不到的承诺
    if p not in PERMISSION_STRICTNESS:
        return True                     # 认不出的预设值：保守判"更松"（会被拒）
    return PERMISSION_STRICTNESS[p] < PERMISSION_STRICTNESS[g]


def assert_no_permission_relaxation(scope: str, preset_value: str,
                                    global_value: str) -> None:
    """WP-6 S-1 的断言：预设比全局更松 ⇒ 当场抛 `RelaxationForbidden`。

    与 `assert_no_relaxation` 同一条纪律、同一个异常类、同一个文件 ——
    **放宽只能是人的动作**，预设文件不是那个入口。
    """
    if permission_relaxes(preset_value, global_value):
        raise RelaxationForbidden(
            f"预设 {scope!r} 想写 {preset_value!r}，但全局是 {global_value!r} —— "
            f"预设只许更严或相等（S-1）：{list(PERMISSION_ACTIONS)} 中越靠后越严。"
            f"要放宽请改全局配置或持久规则（那是人的动作），不要写进预设文件。")


# ============================================================
# HL-05 三级预算（THREE-LAYERS §3.6）—— 契约的唯一判定处
# ============================================================
#
# **明确拒绝**："只靠全局轮数上限"（`agent_runner.MAX_ROUNDS`）。它今天会把两件
# 不同的事报成同一件：「一个目标卡住」与「整个会话失控」。三级各有配额与**唯一**动作：
#
# | 级 | 配额 | 耗尽时 |
# |---|---|---|
# | 目标级 | 该目标的 `budget.{rounds,tokens,refusals}` | L4 上报（**这个目标**做不完） |
# | 分类级 | 该 `class` 的总拒绝次数上限 | **提议固化规则**（DL-03 第 3 条） |
# | 会话级 | 总 token / 总轮数 | L4 上报**并结束** |
#
# 为什么动作表住在这里：与 `LADDER_ACTIONS` / `DRIVER_ACTIONS` 同一条登记纪律 ——
# 新增一级预算必须先在这里登记；`budget_action` 认不出一律返回 `""`（不默认"重试"）。
# 配额 `0` = **未配**（不是"配额为零"）：没配预算时一行行为都不变。

BUDGET_SCOPE_SESSION: Final[str] = "session"   # 整个会话失控（最全局，优先报）
BUDGET_SCOPE_GOAL: Final[str] = "goal"         # 这个目标做不完
BUDGET_SCOPE_CLASS: Final[str] = "class"       # 这一类拒绝反复出现（该固化规则了）

#: 有序：越靠前越全局。多级同时耗尽时**先报会话级** —— 把"会话失控"报成
#: "某个目标卡住"正是本包要治的那件事。
BUDGET_SCOPES: Final[Tuple[str, ...]] = (
    BUDGET_SCOPE_SESSION, BUDGET_SCOPE_GOAL, BUDGET_SCOPE_CLASS,
)

BUDGET_DIM_ROUNDS: Final[str] = "rounds"
BUDGET_DIM_TOKENS: Final[str] = "tokens"
BUDGET_DIM_REFUSALS: Final[str] = "refusals"
BUDGET_DIMENSIONS: Final[Tuple[str, ...]] = (
    BUDGET_DIM_ROUNDS, BUDGET_DIM_TOKENS, BUDGET_DIM_REFUSALS,
)

#: 每级耗尽的**唯一**动作（§3.6 那张表的"耗尽时"列）。
BUDGET_ACTION_ESCALATE: Final[str] = "escalate"            # 停下问人（这个目标做不完）
BUDGET_ACTION_PROPOSE_RULE: Final[str] = "propose_rule"    # 提议固化规则（DL-03③，人确认）
BUDGET_ACTION_ESCALATE_END: Final[str] = "escalate_end"    # 停下问人**并结束**会话
BUDGET_ACTIONS: Final[Dict[str, str]] = {
    BUDGET_SCOPE_SESSION: BUDGET_ACTION_ESCALATE_END,
    BUDGET_SCOPE_GOAL: BUDGET_ACTION_ESCALATE,
    BUDGET_SCOPE_CLASS: BUDGET_ACTION_PROPOSE_RULE,
}

#: 配额 `0` 的含义（登记一次，免得各处各写一遍）：**未配**，永不耗尽。
BUDGET_QUOTA_UNSET: Final[int] = 0


def budget_action(scope: str) -> str:
    """该级预算耗尽时的唯一动作；认不出的级别返回 `""`（**绝不**默认成"重试"）。"""
    return BUDGET_ACTIONS.get(str(scope or "").strip(), "")


def budget_scope_ok(scope: str) -> bool:
    """是不是登记过的预算级别（session/goal/class）。"""
    return str(scope or "").strip() in BUDGET_SCOPES


def budget_dimension_ok(dimension: str) -> bool:
    """是不是登记过的预算维度（rounds/tokens/refusals）。"""
    return str(dimension or "").strip() in BUDGET_DIMENSIONS
