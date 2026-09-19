#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_cost —— 会话成本估算（$）

实话先说在前面：**这是估算，不是账单**。两个不确定来源：

1. token 数是按字符估的（`cli/ace_context.estimate_tokens`：中文按字、英文按 4 字符），
   不是各家真正的 tokenizer；
2. 价格表是**本地快照**，厂商随时会改。默认表只覆盖常见模型，标着快照日期；
   你的实际价格请用配置覆盖：

```json
"pricing": {"deepseek-v4-flash": {"in": 0.28, "out": 0.42}}
```

键按**子串**匹配（写 `deepseek` 就能命中 `deepseek-v4-flash`），最长匹配优先 ——
这样既不必逐个模型抄，也能在需要时精确覆盖一个。查不到价格时输出"价格未知"，
**不猜**：一个凭空的数字比没有数字更糟。

单位统一为 **美元 / 每百万 token**（与各家价目表一致，避免"每千"和"每百万"混着写）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = ["DEFAULT_PRICING", "PRICING_SNAPSHOT", "price_for", "estimate_cost",
           "format_cost", "resolve_pricing", "cost_line"]

# 默认价格表的快照日期。**它一定会过期** —— 这句话是给以后改代码的人看的。
PRICING_SNAPSHOT = "2026-08"

# 美元 / 每百万 token（in = 输入，out = 输出）。
# 取值是常见公开价目的近似值，用于"这轮花了多少钱"的量级判断；精确计费以厂商账单为准。
DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    "deepseek-v4-flash": {"in": 0.28, "out": 0.42},
    "deepseek-v4-pro": {"in": 0.55, "out": 2.19},
    "deepseek-reasoner": {"in": 0.55, "out": 2.19},
    "deepseek-chat": {"in": 0.27, "out": 1.10},
    "glm-4.7-flash": {"in": 0.0, "out": 0.0},      # 免费档（厂商活动价，随时可能变）
    "glm-4.6": {"in": 0.43, "out": 1.74},
    "glm-4.5-air": {"in": 0.14, "out": 0.86},
    "qwen2.5-coder": {"in": 0.0, "out": 0.0},      # 本地 Ollama 跑：只有电费
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "claude-sonnet": {"in": 3.00, "out": 15.00},
    "claude-opus": {"in": 15.00, "out": 75.00},
    "claude-haiku": {"in": 0.80, "out": 4.00},
}


def resolve_pricing(user_pricing: Any) -> Dict[str, Dict[str, float]]:
    """合并默认表与用户配置（用户覆盖同名键，键按小写处理）。"""
    table = {k.lower(): dict(v) for k, v in DEFAULT_PRICING.items()}
    if isinstance(user_pricing, dict):
        for k, v in user_pricing.items():
            if not isinstance(v, dict):
                continue
            try:
                in_p = float(v.get("in", v.get("input", 0.0)) or 0.0)
                out_p = float(v.get("out", v.get("output", 0.0)) or 0.0)
            except (TypeError, ValueError):
                continue
            table[str(k).lower()] = {"in": in_p, "out": out_p}
    return table


def price_for(model: str, table: Optional[Dict[str, Dict[str, float]]] = None
              ) -> Optional[Dict[str, float]]:
    """按**最长子串**匹配价格；查不到返回 None（调用方据此说"价格未知"）。

    为什么最长优先：`deepseek` 与 `deepseek-v4-pro` 同时命中时，后者才是用户写的那个。
    """
    name = str(model or "").strip().lower()
    if not name:
        return None
    tbl = table if isinstance(table, dict) else DEFAULT_PRICING
    best: Optional[Dict[str, float]] = None
    best_len = -1
    for key, price in tbl.items():
        k = str(key).lower()
        if k and k in name and len(k) > best_len:
            best, best_len = price, len(k)
    return best


def estimate_cost(in_tokens: int, out_tokens: int,
                  price: Optional[Dict[str, float]]) -> Optional[float]:
    """按"每百万 token"的价格算钱；没有价格返回 None。"""
    if not price:
        return None
    try:
        in_n = max(0, int(in_tokens or 0))
        out_n = max(0, int(out_tokens or 0))
        return (in_n / 1_000_000.0) * float(price.get("in", 0.0)) + \
               (out_n / 1_000_000.0) * float(price.get("out", 0.0))
    except (TypeError, ValueError):
        return None


def format_cost(usd: Optional[float]) -> str:
    """给人看的一行金额。小额用更多小数位，否则会全显示成 $0.00。"""
    if usd is None:
        return "—"
    if usd == 0:
        return "$0"
    if usd < 0.01:
        return f"${usd:.4f}"
    if usd < 1:
        return f"${usd:.3f}"
    return f"${usd:.2f}"


def cost_line(model: str, in_tokens: int, out_tokens: int,
              table: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """一步到位：给模型 + token 数，返回可直接展示的结构。

    返回：{model, in_tokens, out_tokens, price, usd, text}
    `usd is None` 表示**价格未知**（不是 0 元）—— 调用方必须把这层意思传出去。
    """
    tbl = table if isinstance(table, dict) else DEFAULT_PRICING
    price = price_for(model, tbl)
    usd = estimate_cost(in_tokens, out_tokens, price)
    if price is None:
        text = "价格未知（配置 pricing 可补）"
    else:
        text = f"{format_cost(usd)}（估算）"
    return {"model": str(model or ""), "in_tokens": int(in_tokens or 0),
            "out_tokens": int(out_tokens or 0), "price": price, "usd": usd,
            "text": text}
