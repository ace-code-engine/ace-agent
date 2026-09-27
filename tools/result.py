#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.result —— 工具执行结果（从 execution_layer 拆出）

## 两个通道（`THREE-LAYERS` **RL-01** 的结果信封）

同一个结果要喂两种读者，而它们的语言不一样：

- **人通道**（UI / 模型）：`status` / `error_code` / `message` / `data` —— 给渲染与回喂用；
- **机器通道**（驱动层 / 自愈层）：`outcome` / `refusal_class` / `retryable` /
  `fingerprint` / `hint` —— 给"下一步该干什么"的**判定**用。

为什么非得分开：驱动层此前想知道"发生了什么"只能**解析渲染后的中文散文**
（`agent_runner` 的 `PROMPT_TOOL_RESULT`），于是**"被拒"与"失败"在它眼里是同一件事** ——
那正是 `THREE-LAYERS` §0.2 记下的病根（`file_write` 被一次截断导致的 400 永久熔断）。

**正交新增**：机器通道那五个字段全是**新加的**，`status` / `error_code` 的语义一个都没动 ——
四个外壳正在读它们，改语义等于同时改四处（`TH-R5` 的纪律）。

`budget`（目标级预算）**不在这里**：它属于自愈层的 `HL-05`，是**目标**的属性而不是**一次工具调用**的属性。
"""

from dataclasses import dataclass, field
from typing import Any, Dict

from tools.status import outcome_for


@dataclass
class ExecutionResult:
    """执行结果"""
    status: str = "success"           # success / error / guard_violation / bait_triggered / permission_denied
    data: Any = None
    error_code: str = ""
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # ---- 机器通道（RL-01；漏填也不影响人通道）----
    outcome: str = ""                 # 闭集见 `tools.status.OUTCOMES`；空 = 构造时按单一来源自动补
    refusal_class: str = ""           # RL-02 的六分类（**批次 1 才填**）；`class` 是 Python 关键字故改名
    retryable: bool = False           # 驱动层唯一必答的问题（判据由 RL-02 给，此处只留位）
    fingerprint: str = ""             # 两个账本的键（`THREE-LAYERS` §4）
    hint: Dict[str, Any] = field(default_factory=dict)   # {alternatives: [...], missing: [...]}

    def __post_init__(self) -> None:
        """没显式给 `outcome` 就按**单一来源**推导。

        为什么要在这里补，而不是让 250+ 个构造点各填一次：那些点在 `tools/` 下遍地都是，
        逐个改既改不完、也一定会漏；放这里**每个结果都自动带上机器通道**，
        而调用方仍可显式覆盖（显式值优先）。
        """
        if not self.outcome:
            self.outcome = outcome_for(self.status, self.error_code)
