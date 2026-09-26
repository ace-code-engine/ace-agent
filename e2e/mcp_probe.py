#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mcp_probe —— 假装自己是 MCP host，跟一个**真的** `ace --mcp` 进程说话

为什么要有这个探针（而不是只在 test_all 里调 `McpServer.handle()`）：
协议层的单测证明不了三件事 ——
  ① **stdout 纯度**：引擎几百处 print 会不会有一条漏到协议通道里（漏一条，host 就解析失败）；
  ② **进程真的起得来**：`--mcp` 的接线（stdout 换到 stderr、执行层构造、atexit 收子进程）；
  ③ **裁决真的生效**：只读档写文件被拒、write 档能写、`terminal_exec` headless 被拒、
     以及每次调用都进了会话台账（`.ace_sessions/*.jsonl`）。

用法：
    python e2e/mcp_probe.py            # 全部用例，exit 0 = 全过
    python e2e/mcp_probe.py -v         # 连子进程的 stderr 一起打出来

判据：每个用例自己 `report()`；最后按失败数退出。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ace_mcp_server as M  # noqa: E402
from core import ace_mandate  # noqa: E402

VERBOSE = "-v" in sys.argv
FAILS: list[str] = []
CHECKS = 0


def ck(label: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}" + (f"  [{detail}]" if detail else ""))
        FAILS.append(label)


def _fresh() -> pathlib.Path:
    """一个干净的临时工程目录。落在仓库内 `.test_tmp/`（gitignore）。

    用 uuid 而不是固定名：上次用固定名时，Windows 上 rmtree 静默失败会让下一次运行
    撞上 `FileExistsError`，症状看起来像"探针本身坏了"。
    """
    base = ROOT / ".test_tmp" / f"mcp_probe_{uuid.uuid4().hex[:8]}"
    (base / "project").mkdir(parents=True)
    (base / "home").mkdir()
    return base


class Host:
    """一个极小的 MCP host：写请求、读应答（一行一个 JSON）。"""

    def __init__(self, *extra_args: str, project: pathlib.Path, home: pathlib.Path,
                 config: dict | None = None) -> None:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        # 环境隔离（与 demo 录制同一课）：只搬 HOME 在 Linux 上够、Windows 上不够 ——
        # 签名锚读的是 %LOCALAPPDATA%，不搬的话会落到**运行者自己的** AppData 里。
        env["HOME"] = env["USERPROFILE"] = str(home)
        for var, sub in (("LOCALAPPDATA", "AppData/Local"), ("APPDATA", "AppData/Roaming"),
                         ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
            env[var] = str(home / sub)
        # 锚也钉在临时区：令的密钥由锚派生，探针与子进程必须用**同一个**锚才能对上。
        env["ACE_ANCHOR_DIR"] = str(home / "anchors")
        if config is not None:
            (home / ".ai_code.json").write_text(
                json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "ai_code.py"), "--mcp", "--mock",
             "--project-root", str(project), *extra_args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(project), env=env, text=True, encoding="utf-8", bufsize=1)
        self._id = 0
        self.stray: list[str] = []          # stdout 上不是合法 JSON 的行（协议通道被污染的证据）
        self.stderr_lines: list[str] = []

    def send(self, method: str, params: dict | None = None, *, notify: bool = False) -> dict:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self._id += 1
            msg["id"] = self._id
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        if notify:
            return {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("子进程在应答之前就断了（stdout EOF）")
            try:
                got = json.loads(line)
            except ValueError:
                self.stray.append(line.rstrip("\n"))
                continue                     # 记下来继续等 —— 这条正是探针要抓的东西
            if got.get("id") == msg["id"]:
                return got
            if got.get("id") is None and "error" in got:
                # 服务端回了"无法关联到请求"的错误（id 抠不出来时按规范就是这样）。
                # **不能继续等** —— 第一次跑这条路径时探针死等了 600 s。真实客户端这里
                # 该把它当成本次调用的失败（并可能自己超时），而不是等一个永远不来的应答。
                return got

    def initialize(self) -> dict:
        r = self.send("initialize", {"protocolVersion": M.PROTOCOL_VERSION_LATEST,
                                     "capabilities": {}, "clientInfo": {"name": "probe",
                                                                        "version": "0"}})
        self.send("notifications/initialized", notify=True)
        return r

    def call(self, name: str, args: dict | None = None) -> dict:
        return self.send("tools/call", {"name": name, "arguments": args or {}})

    def close(self) -> int:
        """关 stdin（= host 死法）→ 等子进程自己收工，返回退出码。"""
        try:
            self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            code = self.proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = -99
        err = self.proc.stderr.read() or ""
        self.stderr_lines = err.splitlines()
        if VERBOSE and err.strip():
            print("  --- 子进程 stderr ---")
            for ln in self.stderr_lines:
                print(f"      {ln}")
        return code


def _text(resp: dict) -> str:
    try:
        return resp["result"]["content"][0]["text"]
    except Exception:  # noqa: BLE001
        return ""


def case_readonly() -> None:
    print("[1] 默认（只读）档：能读、不能写、理由可执行")
    tmp = _fresh()
    proj, home = tmp / "project", tmp / "home"
    (proj / "notes.txt").write_text("第一行内容\n第二行内容\n", encoding="utf-8")
    h = Host(project=proj, home=home)
    try:
        init = h.initialize()
        ck("握手回协议版本 + 声明 tools 能力",
           init["result"]["protocolVersion"] == M.PROTOCOL_VERSION_LATEST
           and "tools" in init["result"]["capabilities"],
           json.dumps(init, ensure_ascii=False))
        ck("回 serverInfo 与 instructions（写给 host 的操作事实）",
           init["result"]["serverInfo"]["name"] == "ace" and init["result"].get("instructions"))
        listed = h.send("tools/list")
        names = [t["name"] for t in listed["result"]["tools"]]
        ck("tools/list == 白名单（一个不多一个不少）",
           names == list(M.MCP_TOOL_NAMES), f"{len(names)} vs {len(M.MCP_TOOL_NAMES)}")
        ck("控制面工具没暴露", "subagent" not in names and "request_permission" not in names)

        r = h.call("file_read", {"path": "notes.txt"})
        ck("只读档能读文件", "第一行内容" in _text(r), _text(r)[:160])
        ck("成功结果不带 isError", not r["result"].get("isError"))

        r = h.call("file_write", {"path": "new.txt", "content": "x"})
        body = _text(r)
        ck("只读档写文件被拒（isError，不是 JSON-RPC error）",
           "error" not in r and r["result"].get("isError") is True, json.dumps(r, ensure_ascii=False)[:200])
        ck("拒绝理由写明「缺什么」（提权）", "权限档" in body or "提权" in body, body[:200])
        ck("写被拒后磁盘上确实没有文件", not (proj / "new.txt").exists())

        r = h.call("no_such_tool", {})
        ck("未知工具 → JSON-RPC -32602（调用方写错，不是工具失败）",
           r.get("error", {}).get("code") == M.INVALID_PARAMS, json.dumps(r, ensure_ascii=False)[:160])

        r = h.call("file_read", {"path": "notes.txt", "bogus": 1})
        ck("多余参数不致命（引擎自己忽略/报错都算正常答复）", "result" in r or "error" in r)
    finally:
        code = h.close()
    ck("host 断开 → 子进程正常收工（退出码 0）", code == 0, f"exit={code}")
    ck("stdout 上**一行杂音都没有**（协议通道纯度）", h.stray == [], str(h.stray[:3]))
    ck("stderr 里有「MCP server 就绪」与其他日志（诊断没被吞）",
       any("MCP" in ln for ln in h.stderr_lines), str(h.stderr_lines[-3:]))
    shutil.rmtree(tmp, ignore_errors=True)


def case_write_and_ledger() -> None:
    print("[2] write 档：项目内能写；要问人的那几处在 headless 下被拒；调用都进台账")
    tmp = _fresh()
    proj, home = tmp / "project", tmp / "home"
    outside_old = tmp / "outside_existing.txt"          # 项目外**已存在** → 按政策要问人
    outside_old.write_text("原有内容\n", encoding="utf-8")
    outside_new = tmp / "outside_new.txt"               # 项目外**新建** → 按既有政策不问
    h = Host("--permission", "write", project=proj, home=home)
    try:
        h.initialize()
        r = h.call("file_write", {"path": "made.txt", "content": "hello from mcp\n"})
        ck("write 档能落项目内文件",
           not r["result"].get("isError") and (proj / "made.txt").is_file(),
           json.dumps(r, ensure_ascii=False)[:200])
        ck("落盘内容正确", (proj / "made.txt").read_text(encoding="utf-8") == "hello from mcp\n")

        r = h.call("file_write", {"path": str(outside_old), "content": "被外部 agent 改掉了\n"})
        body = _text(r)
        ck("项目外**已存在**文件被拒（要问人 → headless 拒绝）",
           r["result"].get("isError") is True, body[:200])
        ck("拒绝理由写明「没有人可以确认」这条事实", "没有人可以确认" in body, body[:240])
        ck("拒绝理由给出两条出路（提权 / 授权令）",
           "权限档" in body and "授权令" in body, body[-260:])
        ck("项目外文件内容未被改动",
           outside_old.read_text(encoding="utf-8") == "原有内容\n")

        r = h.call("file_write", {"path": str(outside_new), "content": "new\n"})
        # 这条**不是**在夸设计，是在钉住 ACE 的既有政策："项目外新建"不算破坏性动作
        # （CLI/模型路径也一样不问）。MCP 没有另立一套 —— 要更严是一条独立决定。
        ck("项目外**新建**按既有政策放行（与 CLI/模型路径同口径，不是 MCP 特例）",
           not r["result"].get("isError"), _text(r)[:200])

        r = h.call("terminal_exec", {"command": "echo hi"})
        body = _text(r)
        ck("terminal_exec 在 headless 下被拒（逐次确认没人可答）",
           r["result"].get("isError") is True, body[:200])
        ck("拒绝理由提到「授权令」这条出路",
           "授权令" in body or "mandate" in body.lower(), body[:240])
    finally:
        code = h.close()
    ck("异常用例后仍然正常收工", code == 0, f"exit={code}")
    ck("stdout 仍然纯净", h.stray == [], str(h.stray[:3]))

    # 台账：外部来源必须留痕（RG-02 的链 + source=mcp）
    logs = sorted((proj / ".ace_sessions").glob("*.jsonl"))
    ck("会话台账里有这个 MCP 进程的日志", bool(logs), str(proj))
    if logs:
        raw = logs[-1].read_text(encoding="utf-8")
        ck("台账里有 MCP 来源的记录（source=mcp）", "mcp" in raw)
        ck("台账里记了工具调用（file_write / terminal_exec）",
           "file_write" in raw and "terminal_exec" in raw)
        ck("台账里记了「要问人」的那次拒绝（confirm，不是静默）",
           "confirm" in raw, raw[:200])
        ck("每条事件都带 MAC（RG-02 链式签名）", raw.count('"mac"') >= 2)
    shutil.rmtree(tmp, ignore_errors=True)


def case_mandate_config() -> None:
    """配置里的授权令真的会生效 —— 走**配置文件**而不是构造函数。

    为什么必须有这一条：`test_all [72]` 是把令直接塞给 `ExecutionLayer(...)`，那条路证明的是
    "令 → 放行"这套逻辑；而**令怎么从配置进到执行层**（`ai_code.py` 里那个 `"mandate"` 键、
    `~/.ai_code.json` 的读取）在单测里根本没经过。键名打错、读取漏掉，[72] 照样全绿，
    而真 host 那边会一直"明明配了令还是被拒"。所以这里用真进程 + 真配置文件验一次。
    """
    print("[3] 配置文件里的授权令：terminal_exec 从被拒变成放行")
    tmp = _fresh()
    proj, home = tmp / "project", tmp / "home"
    os.environ["ACE_ANCHOR_DIR"] = str(home / "anchors")   # 探针与子进程同一个锚
    try:
        key = ace_mandate.mandate_key(project_root=str(proj))
        mandate = ace_mandate.issue(key, mandate_id="probe", intents=["terminal_exec"],
                                    roots=[str(proj)], recovery_floor="never",
                                    irreversible_quota=3,
                                    allow_irreversible=["terminal_exec"], ttl_s=3600)
        cfg = {"permission": "write", "mandate": mandate}    # 注意：不传 --permission，只靠配置
        h = Host(project=proj, home=home, config=cfg)
        try:
            h.initialize()
            r = h.call("terminal_exec", {"command": "echo mandate-allowed"})
            body = _text(r)
            ck("配置里的令覆盖了这次调用 → 放行（不再 headless 拒绝）",
               not r["result"].get("isError") and "mandate-allowed" in body, body[:240])
            ck("权限档也是从配置读的（没传 --permission）",
               not r["result"].get("isError") and "returncode" in body or "mandate-allowed" in body,
               body[:200])
        finally:
            code = h.close()
        ck("带令的进程同样干净收工", code == 0, f"exit={code}")
        ck("stdout 纯净（放行路径也一样）", h.stray == [], str(h.stray[:3]))
    finally:
        os.environ.pop("ACE_ANCHOR_DIR", None)
    shutil.rmtree(tmp, ignore_errors=True)


def case_big_write() -> None:
    """大一点的正经写入不该被**协议层**的行长上限拦掉。

    为什么单独一条：MCP 是把 `arguments` 整包放进**一行** JSON 里的，所以"文件内容"这种
    参数天然就会把行撑长 —— 而引擎那边 `file_write` 本来能写任意大小的内容（模型路径不过
    行协议）。行长上限是防"对面写进死循环"，不是防"用户要写一个 2 MB 的文件"。
    第一版把 `ace_serve` 的 1 MiB 直接搬了过来，这条用例就是那次的实测：**2 MiB 的写入被
    协议层拒了**（`-32600 单行超过上限`），症状会像"ACE 不能写大文件"。
    """
    print("[4] 大 payload：2 MiB 的项目内写入要能通过协议层")
    tmp = _fresh()
    proj, home = tmp / "project", tmp / "home"
    h = Host("--permission", "write", project=proj, home=home)
    try:
        h.initialize()
        blob = "x" * (2 * 1024 * 1024)
        r = h.call("file_write", {"path": "big.txt", "content": blob})
        ck("2 MiB 写入没被协议层拒（不是 -32600 单行超限）",
           "error" not in r, json.dumps(r, ensure_ascii=False)[:200])
        if "result" in r:
            ck("2 MiB 写入真的落盘且字节数正确",
               not r["result"].get("isError") and (proj / "big.txt").is_file()
               and (proj / "big.txt").stat().st_size == len(blob),
               f"{_text(r)[:120]} size={((proj / 'big.txt').stat().st_size if (proj / 'big.txt').is_file() else -1)}")
        # 反面：离谱的大行仍然要有一个明确答复（不能把内存吃光）
        huge = {"jsonrpc": "2.0", "id": 999, "method": "tools/call",
                "params": {"name": "file_write",
                           "arguments": {"path": "z.txt", "content": "y" * (12 * 1024 * 1024)}}}
        h.proc.stdin.write(json.dumps(huge) + "\n")
        h.proc.stdin.flush()
        line = h.proc.stdout.readline()
        got = json.loads(line)
        ck("离谱的大行有明确答复（要么执行要么一条说得清的错，不是静默/崩溃）",
           ("error" in got) or ("result" in got), json.dumps(got, ensure_ascii=False)[:160])
    finally:
        code = h.close()
    ck("大 payload 之后进程仍然干净收工", code == 0, f"exit={code}")
    ck("stdout 纯净", h.stray == [], str(h.stray[:3]))
    shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("MCP server 探针 —— 真进程 + 真执行层")
    case_readonly()
    case_write_and_ledger()
    case_mandate_config()
    case_big_write()
    print(f"\n{CHECKS - len(FAILS)} / {CHECKS} 通过")
    if FAILS:
        print("失败项：")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("MCP server：全部用例通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
