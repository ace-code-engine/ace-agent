#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_cubesandbox —— CubeSandbox（KVM MicroVM）薄客户端：主 agent 与 ACE **共用的安全底座**

职责只有三件：① 有没有沙箱可调（`available`）；② 把一段代码丢进去跑（`run`）；
③ 不可达时**如实拒绝**。

S-1（WP-9 卡）：这里**只提供执行边界，不做任何裁决** —— 裁决仍在 execution_layer；
本模块被 `ace_sandbox_exec`（MCP 面）调用，任何调用方想"退而求其次在本地跑"都得
自己另写代码 —— 这里没有那条路（Tier-0 铁律：不可达 → 拒绝，绝不退回本地）。

零依赖：**不 import e2b**。SDK 是可选装（`pip install e2b`，CubeSandbox 对 E2B SDK
兼容），装了 + 配了 API 才真的连通；没装 / 没配就 fail-close，文案把两者分得清
（"没装 SDK"与"服务不可达"是两件事，排查方向不同）。
真 wire 行为只在真机冒烟（卡 A5）时被真实验证；单测用注入的 fake，形状照
E2B Python SDK（`Sandbox.create` / `run_code` / `Execution.stdout·stderr·exit_code`）。

凭据纪律（WP-9 验收 1/2）：**任何宿主环境变量都不注入沙箱**；`env` 里唯一允许出现的是
显式配置的出网白名单（那是白名单参数，不是凭据）。
出网（验收 3）：未配置 allowlist 时**不传任何**出网参数 = 沙箱侧默认拒；配置了才传
`EGRESS_ALLOWLIST`，取值与 ACE 的 `egress_allowlist` **同一份清单、同一个来源**。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["SandboxConfig", "load_sandbox_config", "CubeSandboxBackend",
           "TIER0_TEXT", "MAX_CODE_BYTES", "MAX_TIMEOUT_S", "MIN_TIMEOUT_S"]

TIER0_TEXT = "Tier 0 拒绝（沙箱不可达 → 拒绝，绝不退回本地执行；WP-9 验收 4）"

MAX_CODE_BYTES = 1 << 20
MIN_TIMEOUT_S = 1.0
MAX_TIMEOUT_S = 120.0


@dataclass
class SandboxConfig:
    """沙箱连接的装配。全空 = 未配置（`available()` 会如实拒绝）。"""

    api_base: str = ""            # CubeSandbox 的 E2B 兼容 API 地址（http://127.0.0.1:8080 …）
    template: str = ""            # 沙箱模板名（空 = "ace-sandbox" 默认）
    egress_allowlist: List[str] = field(default_factory=list)  # 显式配置才非空（默认拒绝）
    timeout_s: float = 30.0


def load_sandbox_config(project_root: str = ".",
                        cfg: Optional[Dict[str, Any]] = None) -> SandboxConfig:
    """从配置 / 环境装配。取值顺序：`cfg["sandbox_mcp"]` > `ACE_SANDBOX_API` /
    `ACE_SANDBOX_TEMPLATE` 环境变量。egress allowlist 与 ACE 的 `egress_allowlist`
    **同一份清单、同一个来源**（读 `cfg["egress_allowlist"]`，可被 `sandbox_mcp`
    子表覆盖 —— 覆盖的是值，不是口径）。"""
    cfg = dict(cfg or {})
    sub = dict(cfg.get("sandbox_mcp") or {})
    api = str(sub.get("api") or os.environ.get("ACE_SANDBOX_API", "")).strip()
    tpl = str(sub.get("template") or os.environ.get("ACE_SANDBOX_TEMPLATE", "")).strip()
    allow = list(sub.get("egress_allowlist") or cfg.get("egress_allowlist") or [])
    try:
        timeout = float(sub.get("timeout_s") or cfg.get("sandbox_timeout_s") or 30.0)
    except (TypeError, ValueError):
        timeout = 30.0
    return SandboxConfig(api_base=api, template=tpl,
                         egress_allowlist=[str(a).strip() for a in allow if str(a).strip()],
                         timeout_s=timeout)


class CubeSandboxBackend:
    """一次会话一个实例；`run()` 每次开一个沙箱、跑完杀掉。"""

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()

    def available(self) -> "tuple[bool, str]":
        """(有没有沙箱可调, 原因)。原因要**可执行**：没配 API 与没装 SDK 是两种修法。"""
        if not self.config.api_base:
            return False, ("未配置沙箱 API（配置 sandbox_mcp.api 或环境变量 "
                           f"ACE_SANDBOX_API）—— {TIER0_TEXT}")
        try:
            import e2b  # noqa: PLC0415 —— 可选依赖，不装就 fail-close
        except Exception as e:  # noqa: BLE001 —— 装没装/坏没坏都如实说
            return False, (f"e2b SDK 不可用（pip install e2b；{type(e).__name__}: {e}）"
                           f"—— {TIER0_TEXT}")
        if not hasattr(e2b, "Sandbox"):
            return False, f"e2b SDK 已装但没有 Sandbox 类（版本不符）—— {TIER0_TEXT}"
        return True, ""

    def run(self, code: str, language: str = "python",
            timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """在沙箱里跑一段代码。

        返回 `{"ok":…, "code":…, "stdout":…, "stderr":…, "exit_code":…, "detail":…}`。
        - `ok=False`：沙箱**没跑成**（未配置 / SDK 缺失 / 创建失败）—— 这是"不可达"，
          调用方必须把它当拒绝（Tier 0），**不要**重试成本地执行。
        - `ok=True`：代码**跑完了**；`exit_code` 非 0 是**业务结果**，不是"沙箱坏了"。
        """
        ok, why = self.available()
        if not ok:
            return {"ok": False, "code": "sandbox_unavailable", "detail": why,
                    "stdout": "", "stderr": "", "exit_code": None}
        t = min(max(float(timeout_s if timeout_s is not None
                          else self.config.timeout_s), MIN_TIMEOUT_S), MAX_TIMEOUT_S)
        env: Dict[str, str] = {}
        if self.config.egress_allowlist:
            env["EGRESS_ALLOWLIST"] = ",".join(self.config.egress_allowlist)
        try:
            from e2b import Sandbox  # noqa: PLC0415

            # API 地址：老 SDK 用类属性 / 新 SDK 用 create 参数，两代都试一下；
            # 失败就落进下面的 except（如实报错，而不是猜一个能跑的）。
            try:
                Sandbox.api_url = self.config.api_base     # type: ignore[attr-defined]
            except (AttributeError, TypeError):
                pass
            sbx = Sandbox.create(template=self.config.template or "ace-sandbox",
                                 envs=env, timeout=t)
            try:
                exec_ = sbx.run_code(str(code), language=language, timeout=t)
            finally:
                try:
                    sbx.kill()
                except Exception:  # noqa: BLE001 —— 收尾失败不该盖过执行结果
                    pass
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "code": "sandbox_error",
                    "detail": f"沙箱执行失败（{type(e).__name__}: {e}）—— {TIER0_TEXT}",
                    "stdout": "", "stderr": "", "exit_code": None}
        return {"ok": True, "code": "sandbox_ok",
                "stdout": str(getattr(exec_, "stdout", "") or ""),
                "stderr": str(getattr(exec_, "stderr", "") or ""),
                "exit_code": getattr(exec_, "exit_code", None),
                "error": str(getattr(exec_, "error", "") or ""),
                "detail": ""}
