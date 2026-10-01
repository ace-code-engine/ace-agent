#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify-mcp —— 本包的**自检**：把包自己拉起来，走一遍真协议，告诉你通没通。

为什么要有它：非侵入式接入最容易失败的地方是"装完了不知道对不对"，而用户能拿到的
信息只有 host 里一句"连接失败"。这个脚本用**和 host 完全一样的方式**（stdio 子进程 +
一行一个 JSON-RPC）跑一遍，所以它红了，host 那边也好不了。

零第三方依赖（与 `--mcp` 模式本身一致），Windows / Linux / macOS 通用。

    python verify-mcp.py            # 握手 + tools/list + 路径级扫描
    python verify-mcp.py --write    # 额外验证写路径（往系统临时目录真写一个文件）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIMEOUT_S = 120


class Fail(Exception):
    pass


def _spawn(extra: list) -> subprocess.Popen:
    """与 host 同一种拉起方式：直接跑 ai_code.py（绕开 .cmd/.sh 的 shell 差异，
    因为要验的是 ACE，不是 shell）。"""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    entry = HERE / "ai_code.py"
    if not entry.is_file():
        raise Fail(f"包里缺 ai_code.py：{entry}")
    if sys.version_info < (3, 10):
        raise Fail(f"需要 Python 3.10+，当前 {sys.version.split()[0]}")
    return subprocess.Popen(
        [sys.executable, str(entry), "--mcp", *extra],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(HERE), env=env, text=True, encoding="utf-8", errors="replace", bufsize=1)


def _rpc(proc: subprocess.Popen, msg_id, method, params=None, notify=False):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not notify:
        msg["id"] = msg_id
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            raise Fail(f"子进程在应答 {method} 之前就退出了（stderr 见下）\n"
                       + (proc.stderr.read() or "")[-1500:])
        line = line.strip()
        if not line:
            continue
        try:
            got = json.loads(line)
        except ValueError:
            raise Fail(f"stdout 上出现了非 JSON 的一行（协议通道被污染）：{line[:200]}")
        if got.get("id") == msg_id:
            return got


def main() -> int:
    extra = []
    if "--write" in sys.argv:
        extra = ["--permission", "write"]
    proc = None
    try:
        proc = _spawn(extra)
        init = _rpc(proc, 1, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "verify-mcp", "version": "1"}})
        _rpc(proc, None, "notifications/initialized", notify=True)
        info = init["result"]["serverInfo"]
        print(f"  OK   握手：{info['name']} v{info['version']} "
              f"(protocol {init['result']['protocolVersion']})")

        listed = _rpc(proc, 2, "tools/list")
        names = [t["name"] for t in listed["result"]["tools"]]
        print(f"  OK   tools/list：{len(names)} 个工具")
        for must in ("ace_security_scan", "ace_sandbox_exec", "file_read"):
            if must not in names:
                raise Fail(f"工具清单里缺 {must}")

        scan = _rpc(proc, 3, "tools/call",
                    {"name": "ace_security_scan", "arguments": {"path": "."}})
        text = scan["result"]["content"][0]["text"]
        if "不读文件内容" not in text:
            raise Fail("扫描报告里没有范围声明（SEC-022 的防线没了，别信这份报告）")
        print("  OK   ace_security_scan：真跑通，且报告自带范围声明")

        if extra:                                   # 写路径：真写一个临时文件
            target = Path(tempfile.gettempdir()) / "ace_mcp_verify.txt"
            w = _rpc(proc, 4, "tools/call", {"name": "file_write", "arguments": {
                "path": str(target), "content": "ace mcp verify\n"}})
            if w["result"].get("isError"):
                raise Fail("write 档下写临时文件仍被拒：" + w["result"]["content"][0]["text"][:300])
            print(f"  OK   写路径：{target}")
        else:
            print("  --  写路径未验（加 --write 才验；默认只读是安全的起点）")
        return 0
    except Fail as e:
        print(f"  FAIL {e}")
        return 1
    except Exception as e:                          # noqa: BLE001
        print(f"  FAIL 意外错误：{type(e).__name__}: {e}")
        return 1
    finally:
        if proc is not None:
            try:
                proc.stdin.close()
                proc.wait(timeout=20)
            except Exception:                       # noqa: BLE001
                proc.kill()


if __name__ == "__main__":
    print("ACE MCP 接入包自检 —— 与 host 同样的拉起方式")
    code = main()
    print("OK：这个包可以被 MCP host 正常拉起。" if code == 0
          else "FAIL：先修上面那条，再回到 host 里试。")
    sys.exit(code)
