#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_mandate —— 授权令（RG-05 第一阶段：签发 / 验签 / 四条判定，**尚未接入审批流程**）

论文的 I2 要求"每次行动都能追溯到一条用户侧授权"。ACE 今天的审批粒度是**对象**
（H-09：一次调用绑一个对象），于是弹窗数随危险步数线性增长。原型的主张是把粒度换成
**一次任务一张令**：

    mandate = (intents, roots, recoveryFloor, irreversibleQuota, ttl) + 签名

签名用**锚里的密钥**（RG-01 那个座位）。之后每次行动只是**对着令核一遍**，
所以弹窗从 O(步数) 降到 O(任务数)。

第一阶段（本文件）只做**令本身**：签发、验签、以及四条判定（意图 / 范围 / 可逆性下限 / 额度 / TTL）。
**`_stage_permission` 一行都不动** —— 与 RG-03、RG-04 同样的节奏：先把逻辑与可证伪测试做出来，
接入审批流程是下一步（那一步才会真的改变弹窗行为）。

口径（写下来免得以后各处理解不一）：

* **可逆性从强到弱：`GIT` > `SNAPSHOT` > `REGENERABLE` > `UNKNOWN` > `NEVER`。**
  "可再生"比"有快照"弱一档 —— 快照是原样的副本，重新生成未必得到同一个东西（重装依赖就
  不一定同版本）。`NEVER` 永远达不到任何下限，只能靠 `allow_irreversible` 显式点名 + 额度。
* **过期 = 升级**（重新签一张即可），不是拒绝 —— 与原型"影子超时走升级路径"一致。
* **签名不符 / 缺签名 = 拒绝**，不是升级：那说明令被改过或不是本锚签的，去问人没有意义
  （人也只能看到一份被改过的纸条）。
* 行动的目标**没有分类信息**时按 `UNKNOWN` 处理（保守 → 需要令里明确放行）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.ace_recovery import GIT, SNAPSHOT, REGENERABLE, NEVER, UNKNOWN

# 从强到弱。数字只用于比较，别拿去做算术。
RECOVERY_ORDER: Dict[str, int] = {
    GIT: 4, SNAPSHOT: 3, REGENERABLE: 2, UNKNOWN: 1, NEVER: 0,
}
DEFAULT_FLOOR = SNAPSHOT
ALLOW = "allow"
ESCALATE = "escalate"
DENY = "deny"

MANDATE_KEY_NAME = "mandate_key"
_KEY_DOMAIN = b"ace-mandate-v1"


def mandate_key(anchor_dir: Optional[str] = None,
                project_root: Optional[str] = None) -> bytes:
    """授权令的签名密钥：从**锚**派生（与快照密钥、台账密钥域分离，各用各的）。

    `anchor_dir` / `project_root` 与 `core.guardian.anchor_dir_for` 同义 —— 测试与受限环境
    都靠它们注入。锚不可用时抛 `OSError`，由调用方决定 fail-close 还是如实报不可用。
    """
    from core.guardian import anchor_dir_for, load_or_create_anchor_secret
    root = project_root or "."
    secret = load_or_create_anchor_secret(
        anchor_dir_for(root, anchor_dir) / MANDATE_KEY_NAME)
    return hmac.new(secret.encode("utf-8"), _KEY_DOMAIN, hashlib.sha256).digest()


def _canonical(body: Dict[str, Any]) -> str:
    """令的规范形式（不含 `mac`）：排序键 + 紧凑分隔符 —— 与台账那边同一条规则。"""
    return json.dumps({k: v for k, v in body.items() if k != "mac"},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sign(key: bytes, body: Dict[str, Any]) -> str:
    return hmac.new(key, _canonical(body).encode("utf-8"), hashlib.sha256).hexdigest()


def issue(key: bytes, *, mandate_id: str, intents: Sequence[str] = (),
          roots: Sequence[str] = (), recovery_floor: str = DEFAULT_FLOOR,
          irreversible_quota: int = 0, allow_irreversible: Sequence[str] = (),
          ttl_s: int = 3600, now: Optional[float] = None) -> Dict[str, Any]:
    """签一张令。`intents` 是允许的意图/工具名；`roots` 是允许的路径前缀。"""
    now = time.time() if now is None else now
    body: Dict[str, Any] = {
        "mandateId": str(mandate_id),
        "intents": sorted({str(x) for x in intents}),
        "roots": [str(r) for r in roots],
        "recoveryFloor": str(recovery_floor),
        "irreversibleQuota": int(irreversible_quota),
        "allowIrreversible": sorted({str(x) for x in allow_irreversible}),
        "issuedAt": float(now),
        "expiresAt": float(now) + float(ttl_s),
        "usedIrreversible": 0,
    }
    body["mac"] = _sign(key, body)
    return body


def verify(key: bytes, mandate: Dict[str, Any],
           now: Optional[float] = None) -> Tuple[str, str]:
    """→ (`"ok"` / `"invalid"` / `"expired"`, 理由)。

    三态而不是布尔：**"签名不对"与"过期了"要走相反的处理** —— 前者拒绝，后者升级重签。
    """
    if not isinstance(mandate, dict) or not mandate.get("mandateId"):
        return "invalid", "令缺失或结构不对"
    mac = mandate.get("mac")
    if not (isinstance(mac, str) and mac):
        return "invalid", "令没有签名"
    if not hmac.compare_digest(mac, _sign(key, mandate)):
        return "invalid", "令的签名不符（被改过，或不是本锚签的）"
    now = time.time() if now is None else now
    if float(mandate.get("expiresAt") or 0) <= now:
        return "expired", "令已过期（重新签一张即可）"
    return "ok", "签名与有效期都有效"


def _below_floor(level: str, floor: str) -> bool:
    return RECOVERY_ORDER.get(str(level), 1) < RECOVERY_ORDER.get(str(floor), 3)


def authorize(key: bytes, mandate: Dict[str, Any], *, tool: str,
              targets: Iterable[str] = (), recovery: Optional[Dict[str, str]] = None,
              now: Optional[float] = None) -> Dict[str, Any]:
    """对着令核一次行动。**纯函数**：不修改 `mandate`（额度由调用方在放行后自行累加）。

    返回 `{"decision", "rule", "reason", "consumes"}`，其中 `consumes` = 这次放行要消耗几个
    不可逆额度（0 表示这次是可逆的，不占额度）。
    """
    status, why = verify(key, mandate, now=now)
    if status == "invalid":
        return {"decision": DENY, "rule": "no_mandate", "reason": why, "consumes": 0}
    if status == "expired":
        return {"decision": ESCALATE, "rule": "mandate_expired", "reason": why,
                "consumes": 0}

    tool = str(tool)
    if tool and tool not in (mandate.get("intents") or []):
        return {"decision": ESCALATE, "rule": "intent_scope", "consumes": 0,
                "reason": f"令里没有授权 {tool}（已授权：{', '.join(mandate.get('intents') or []) or '无'}）"}

    roots: List[str] = [str(r) for r in (mandate.get("roots") or [])]
    items = [str(t) for t in targets or []]
    outside = [t for t in items
               if not any(t == r or t.startswith(r.rstrip("/\\") + "/")
                          or t.startswith(r.rstrip("/\\") + "\\") for r in roots)]
    if outside:
        return {"decision": ESCALATE, "rule": "out_of_roots", "consumes": 0,
                "reason": f"目标越出令的范围：{', '.join(outside[:3])}"}

    floor = str(mandate.get("recoveryFloor") or DEFAULT_FLOOR)
    cls = recovery or {}
    allowed_irr = set(mandate.get("allowIrreversible") or [])
    quota = int(mandate.get("irreversibleQuota") or 0)
    used = int(mandate.get("usedIrreversible") or 0)
    offending = []
    for t in items:
        lvl = str(cls.get(t, UNKNOWN))
        if _below_floor(lvl, floor):
            offending.append((t, lvl))
    if not offending:
        return {"decision": ALLOW, "rule": "within_floor", "consumes": 0,
                "reason": f"目标都在可逆性下限（{floor}）之上"}
    # 不可逆：只有当**每一个**越界的落点都被点名放行、且额度还没用完，才允许
    unnamed = [t for t, _l in offending if t not in allowed_irr]
    if unnamed:
        return {"decision": ESCALATE, "rule": "recovery_below_floor", "consumes": 0,
                "reason": (f"目标可逆性低于令的下限（{floor}）且未被点名放行："
                           f"{', '.join(unnamed[:3])}")}
    if used >= quota:
        return {"decision": ESCALATE, "rule": "quota_exhausted", "consumes": 0,
                "reason": f"不可逆额度已用尽（{used}/{quota}）"}
    return {"decision": ALLOW, "rule": "allowed_irreversible", "consumes": 1,
            "reason": f"点名放行的不可逆动作，消耗 1 个额度（{used}/{quota}）"}


def record_use(mandate: Dict[str, Any], consumes: int,
               key: bytes) -> Dict[str, Any]:
    """放行之后累加额度并**重新签名**（返回新的一份，不改传进来的那份）。

    为什么要重签：额度是令的一部分，不重签就等于"额度可以事后随便改"。
    """
    if not consumes:
        return mandate
    body = dict(mandate)
    body.pop("mac", None)
    body["usedIrreversible"] = int(body.get("usedIrreversible") or 0) + int(consumes)
    body["mac"] = _sign(key, body)
    return body
