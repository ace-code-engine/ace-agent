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

from typing import Final, FrozenSet

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
