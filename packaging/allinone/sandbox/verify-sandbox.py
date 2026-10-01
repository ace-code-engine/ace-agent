#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify-sandbox —— 底座层自检：**这台机器连得到底座吗？底座真的能跑代码吗？**

分两步，每一步都独立可信（不猜上游端点）：
  ① **可达性**：对 `ACE_SANDBOX_API` 的 host:port 做一次 TCP 连接（stdlib socket）。
     连不上就是连不上，不需要任何 SDK。
  ② **真跑一次**：装了 `e2b` SDK 才做 —— 建一个沙箱、跑 `print(1+1)`、杀掉，
     断言看到 `2`。这一步失败会如实说"没装 SDK 所以只验到可达性"，而不是假装通过。

用法：
    python verify-sandbox.py                       # 读 ACE_SANDBOX_API
    python verify-sandbox.py http://10.0.0.5:3000  # 直接给地址
"""
from __future__ import annotations

import os
import socket
import sys
from urllib.parse import urlparse

DEFAULT = "http://127.0.0.1:3000"


def main() -> int:
    api = ""
    for a in sys.argv[1:]:
        if a.startswith("http"):
            api = a
    api = api or os.environ.get("ACE_SANDBOX_API", "") or DEFAULT
    u = urlparse(api if "//" in api else "//" + api)
    host, port = u.hostname or "127.0.0.1", u.port or 3000
    print(f"ACE 底座自检 —— 目标 {host}:{port}")

    # ① 可达性
    try:
        with socket.create_connection((host, port), timeout=5):
            print(f"  OK   TCP 可达：{host}:{port}")
    except OSError as e:
        print(f"  FAIL 连不上 {host}:{port}（{type(e).__name__}: {e}）")
        print("       底座没起 / 地址不对 / 防火墙 —— 在这之前 ace_sandbox_exec 会一律拒绝（Tier 0），")
        print("       这是设计行为，不是 bug。")
        return 1

    # ② 真跑一次（需要 e2b SDK）
    try:
        from e2b import Sandbox  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        print(f"  --   未装 e2b SDK（{type(e).__name__}），只验到『可达』。"
              "要验真执行：pip install e2b")
        return 0

    os.environ.setdefault("E2B_API_URL", api)
    if os.environ.get("ACE_SANDBOX_KEY"):
        os.environ.setdefault("E2B_API_KEY", os.environ["ACE_SANDBOX_KEY"])
    sbx = None
    try:
        sbx = Sandbox.create(template=os.environ.get("ACE_SANDBOX_TEMPLATE") or "ace-sandbox",
                             envs={}, timeout=60)
        ex = sbx.run_code("print(1+1)", language="python", timeout=60)
        out = str(getattr(ex, "stdout", "") or "").strip()
        if "2" not in out:
            print(f"  FAIL 沙箱跑起来了但结果不对：stdout={out!r} exit={getattr(ex, 'exit_code', None)}")
            return 1
        print(f"  OK   沙箱真跑通：print(1+1) -> {out.strip().splitlines()[-1]}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL 建沙箱/执行失败：{type(e).__name__}: {e}")
        print("       （常见原因：模板名不对 / key 不对 / 底座还没就绪）")
        return 1
    finally:
        if sbx is not None:
            try:
                sbx.kill()
            except Exception:  # noqa: BLE001
                pass
    print("底座可用 —— 回到 host 里让 agent 调一次 ace_sandbox_exec。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
