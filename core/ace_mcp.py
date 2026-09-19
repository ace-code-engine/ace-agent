#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_mcp —— MCP（Model Context Protocol）客户端：stdio JSON-RPC 2.0

为什么需要它：`tools/registry.register()` 只回答了"工具怎么进注册表"，没回答
"外部进程怎么说话"。MCP 是一套**真实协议**（initialize 握手 → tools/list →
tools/call，JSON-RPC 2.0，stdio 上按行分隔），不实现它就只能把每个 MCP server
的工具一条条手写成 Python 函数 —— 那不叫接入，叫抄。

边界（写在明面上，不假装）：
- **MCP server 本身不在我们的沙箱里**。它是你配置的一个子进程，它内部做什么我们
  管不了。执行层管的是"ACE 要不要调用它"（权限/审批/审计照常适用），不是"它内部
  干了什么"。所以只把你信得过的 server 写进配置。
- 目前只支持 **stdio 传输**（本地子进程）。HTTP/SSE 传输没有实现，也不假装支持。
- server 发起的反向请求（sampling / roots / elicitation）一律回"方法未实现"，
  不静默忽略 —— 静默忽略会让对面一直等。
- 协议版本声明为 2025-06-18；对面若不接受，initialize 会如实报错，而不是硬凑。

纯逻辑（内容块展平、spec 名、配置校验、权限归类）与进程 I/O 分开：前者可单测，
后者用假 server 端到端验。
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["McpError", "McpTimeout", "McpProcessDied", "McpStdioClient",
           "McpManager", "flatten_content", "is_error_result", "spec_name",
           "parse_spec_name", "tool_permission", "tool_spec", "load_server_configs",
           "PROTOCOL_VERSION", "CLIENT_NAME"]

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "ace"

# MCP 工具全名（模型看到的那个）：`mcp__<server>__<tool>`。
# 前缀是有意的：一眼能看出这个工具不是 ACE 自己的，也便于按 server 归类/禁用。
SPEC_PREFIX = "mcp__"
_NAME_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
# 文本展平的兜底上限：一个工具回 10MB 文本会把上下文直接撑爆
MAX_CONTENT_CHARS = 60_000


class McpError(Exception):
    """协议层错误（对面返回 error 对象 / 响应不成形）"""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = int(code or 0)


class McpTimeout(McpError):
    """等响应超时。单独一类是因为它要报 504，而不是笼统的 500。"""


class McpProcessDied(McpError):
    """子进程退出/管道断了 —— 这类错误下重试没有意义，得让人看见。"""


# ============================================================
# 纯逻辑：内容块、命名、配置、权限
# ============================================================

def flatten_content(result: Any) -> str:
    """MCP 工具结果 → 纯文本。

    MCP 的 `content` 是一个块数组（`{"type":"text","text":...}`、image、resource …）。
    这里只取文本；非文本块**如实标注**（`[image: image/png]`）而不是丢掉 ——
    "回了一张图"和"什么都没回"对用户是两件事。
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result[:MAX_CONTENT_CHARS]
    blocks: List[Any] = []
    if isinstance(result, dict):
        blocks = result.get("content") or []
        # 有些 server 只给 structuredContent（无 content 块）
        if not blocks and result.get("structuredContent") is not None:
            return json.dumps(result["structuredContent"], ensure_ascii=False,
                              indent=2)[:MAX_CONTENT_CHARS]
    elif isinstance(result, list):
        blocks = result
    if not isinstance(blocks, list):
        return str(result)[:MAX_CONTENT_CHARS]
    out: List[str] = []
    for b in blocks:
        if isinstance(b, str):
            out.append(b)
            continue
        if not isinstance(b, dict):
            out.append(str(b))
            continue
        btype = str(b.get("type") or "")
        if btype == "text" or "text" in b:
            out.append(str(b.get("text") or ""))
        elif btype == "resource":
            res = b.get("resource") or {}
            uri = res.get("uri") or ""
            if isinstance(res.get("text"), str):
                out.append(f"[resource {uri}]\n{res['text']}")
            else:
                out.append(f"[resource {uri}（非文本，未展开）]")
        elif btype in ("image", "audio"):
            out.append(f"[{btype}: {b.get('mimeType') or '未知类型'}，未展开]")
        else:
            out.append(f"[{btype or '未知块'}]")
    text = "\n".join(x for x in out if x != "")
    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS] + f"\n…（已截断，原始 {len(text)} 字符）"
    return text


def is_error_result(result: Any) -> bool:
    """MCP 的工具执行失败是用 `isError: true` 表达的，不是 JSON-RPC error ——
    两者要分开：前者是"工具跑了但失败了"，后者是"协议层面没成"。
    """
    return bool(isinstance(result, dict) and result.get("isError"))


def spec_name(server: str, tool: str) -> str:
    """外部工具 → ACE 工具名。非法字符替换成 `_`，防止造出跑不起来的名字。"""
    return f"{SPEC_PREFIX}{_NAME_SAFE.sub('_', str(server))}__{_NAME_SAFE.sub('_', str(tool))}"


def parse_spec_name(name: str) -> Optional[Tuple[str, str]]:
    """ACE 工具名 → (server, tool)；不是 MCP 工具则 None。"""
    if not isinstance(name, str) or not name.startswith(SPEC_PREFIX):
        return None
    rest = name[len(SPEC_PREFIX):]
    if "__" not in rest:
        return None
    server, tool = rest.split("__", 1)
    return (server, tool) if server and tool else None


def tool_permission(tool: Dict[str, Any]) -> str:
    """MCP 工具 → ACE 权限组。

    `annotations.readOnlyHint: true` 才按只读处理，其余一律按**写**（readonly 会话
    下需要授权）。默认从严：对面说只读是它自己声明的，说错话的代价不该由用户承担。
    """
    ann = (tool or {}).get("annotations")
    if isinstance(ann, dict) and ann.get("readOnlyHint") is True:
        return "read"
    return "write"


def tool_spec(server: str, tool: Dict[str, Any]) -> Dict[str, Any]:
    """MCP 工具声明 → ACE 工具声明（dict 形态，交给 tools.registry 组装 ToolSpec）。

    输入 schema 直接透传：MCP 用的就是 JSON Schema，转一道只会丢信息。
    """
    name = str((tool or {}).get("name") or "")
    desc = str((tool or {}).get("description") or "").strip()
    schema = (tool or {}).get("inputSchema")
    if not isinstance(schema, dict) or not schema:
        schema = {"type": "object", "properties": {}}
    return {
        "name": spec_name(server, name),
        "server": server,
        "tool": name,
        "permission": tool_permission(tool),
        "description": (f"[MCP:{server}] " + (desc or name))[:400],
        "parameters": schema,
    }


def load_server_configs(user_servers: Any,
                        project_file: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """合并「用户配置里的 mcp_servers」与「项目内 .ace/mcp.json」。

    项目级覆盖同名用户级（项目更具体），两边都做校验：缺 `command`、`args` 不是
    字符串数组、`enabled: false` 的条目都会被过滤掉 —— 配置写错时**少一个 server**
    比"整个会话起不来"好得多，但必须能被 `/mcp` 看见原因（见 `config_errors`）。
    """
    merged: Dict[str, Dict[str, Any]] = {}
    if isinstance(user_servers, dict):
        merged.update({k: v for k, v in user_servers.items() if isinstance(v, dict)})
    if project_file:
        try:
            p = Path(project_file)
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
                if isinstance(servers, dict):
                    merged.update({k: v for k, v in servers.items()
                                   if isinstance(v, dict)})
        except (OSError, json.JSONDecodeError):
            pass
    out: Dict[str, Dict[str, Any]] = {}
    for name, cfg in merged.items():
        cmd = str(cfg.get("command") or "").strip()
        args = cfg.get("args") or []
        if not cmd:
            continue
        if not isinstance(args, list):
            args = [str(args)]
        args = [str(a) for a in args]
        env = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
        out[str(name)] = {
            "command": cmd,
            "args": args,
            "env": {str(k): str(v) for k, v in env.items()},
            "cwd": cfg.get("cwd"),
            "enabled": cfg.get("enabled", True) is not False,
            "timeout": float(cfg.get("timeout") or 20.0),
            "call_timeout": float(cfg.get("call_timeout") or 120.0),
        }
    return out


# ============================================================
# stdio 客户端
# ============================================================

@dataclass
class McpServerState:
    name: str
    config: Dict[str, Any]
    status: str = "未启动"          # 未启动 / 就绪 / 失败 / 已关闭 / 已禁用
    error: str = ""
    tools: List[Dict[str, Any]] = field(default_factory=list)
    server_info: Dict[str, Any] = field(default_factory=dict)


class McpStdioClient:
    """一个 MCP server 的 stdio 会话（同步请求-响应）。

    实现要点：
    - **读线程 + 队列**：Windows 的管道不能 select，用后台线程收行、主线程按 id 取。
      顺带解决"通知与响应交错"：没有 id 的消息进缓冲，server 发起的请求就地回
      "方法未实现"。
    - **stderr 单独收**：server 的日志不能和协议流混在一起（混了就是坏 JSON），
      但也不能丢 —— 启动失败时那几行往往是唯一线索。
    - 超时/进程退出都给专门异常：调用方要报 504 还是 500，取决于这个区分。
    """

    def __init__(self, name: str, cfg: Dict[str, Any], project_root: str = ".") -> None:
        self.name = name
        self.cfg = dict(cfg or {})
        self.project_root = project_root
        self.proc: Optional[subprocess.Popen] = None
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stderr: List[str] = []
        self._next_id = 1
        self._lock = threading.Lock()
        self.server_info: Dict[str, Any] = {}
        self.capabilities: Dict[str, Any] = {}
        self._closed = False
        self._reader: Optional[threading.Thread] = None
        self._err_reader: Optional[threading.Thread] = None

    # ---------- 生命周期 ----------

    def start(self, timeout: float = 20.0) -> None:
        cmd = [self.cfg["command"]] + list(self.cfg.get("args") or [])
        env = dict(os.environ)
        env.update(self.cfg.get("env") or {})
        env.setdefault("PYTHONIOENCODING", "utf-8")
        cwd = self.cfg.get("cwd") or self.project_root
        try:
            self.proc = subprocess.Popen(          # noqa: S603 —— 命令来自用户配置
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", bufsize=1, cwd=cwd, env=env)
        except (OSError, ValueError) as e:
            raise McpProcessDied(f"启动失败: {e}") from e
        self._reader = threading.Thread(target=self._read_loop, daemon=True,
                                        name=f"mcp-{self.name}-out")
        self._reader.start()
        self._err_reader = threading.Thread(target=self._err_loop, daemon=True,
                                            name=f"mcp-{self.name}-err")
        self._err_reader.start()
        self.initialize(timeout=timeout)

    def close(self) -> None:
        self._closed = True
        p = self.proc
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except OSError:
            pass
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:  # noqa: BLE001 —— 收尾尽力而为，不掩盖主流程的错误
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass
        self.proc = None

    def _read_loop(self) -> None:
        p = self.proc
        if p is None or p.stdout is None:
            self._q.put(None)
            return
        try:
            for line in p.stdout:
                self._q.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self._q.put(None)                      # 进程结束的哨兵

    def _err_loop(self) -> None:
        p = self.proc
        if p is None or p.stderr is None:
            return
        try:
            for line in p.stderr:
                self._stderr.append(line.rstrip("\n"))
                del self._stderr[:-40]             # 只留最后 40 行，够定位问题
        except (OSError, ValueError):
            pass

    # ---------- 协议 ----------

    def _send(self, payload: Dict[str, Any]) -> None:
        p = self.proc
        if p is None or p.stdin is None or p.poll() is not None:
            raise McpProcessDied(
                f"MCP server {self.name} 已退出" + self.stderr_tail())
        try:
            p.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            p.stdin.flush()
        except (OSError, ValueError) as e:
            raise McpProcessDied(
                f"写入 {self.name} 失败: {e}" + self.stderr_tail()) from e

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method: str, params: Optional[Dict[str, Any]] = None,
                timeout: Optional[float] = None) -> Any:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        deadline = time.monotonic() + float(timeout or self.cfg.get("timeout") or 20.0)
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise McpTimeout(f"{self.name}.{method} 超时"
                                 f"（{timeout or self.cfg.get('timeout')}s）"
                                 + self.stderr_tail())
            try:
                line = self._q.get(timeout=min(remain, 0.5))
            except queue.Empty:
                if self.proc is not None and self.proc.poll() is not None:
                    raise McpProcessDied(
                        f"{self.name} 在等待 {method} 时退出"
                        f"（exit {self.proc.returncode}）" + self.stderr_tail())
                continue
            if line is None:
                raise McpProcessDied(self._died_message() + self.stderr_tail())
            line = line.strip()
            if not line:
                continue
            try:
                msg_in = json.loads(line)
            except json.JSONDecodeError:
                # 对面把日志打到了 stdout —— 这是对面违反协议，如实报，不猜
                raise McpError(f"{self.name} 输出了非 JSON 行: {line[:200]}")
            if not isinstance(msg_in, dict):
                raise McpError(f"{self.name} 输出了非对象消息")
            if msg_in.get("id") == req_id:
                if "error" in msg_in:
                    err = msg_in.get("error") or {}
                    raise McpError(str(err.get("message") or "未知错误"),
                                   code=int(err.get("code") or 0))
                return msg_in.get("result")
            if msg_in.get("id") is None and msg_in.get("method"):
                continue                            # 通知：忽略（不阻塞响应）
            if msg_in.get("method") and msg_in.get("id") is not None:
                # server → client 请求：明确回"方法未实现"，不让对面干等
                self._send({"jsonrpc": "2.0", "id": msg_in["id"],
                            "error": {"code": -32601,
                                      "message": f"ACE 未实现 {msg_in['method']}"}})

    def initialize(self, timeout: float = 20.0) -> Dict[str, Any]:
        res = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME,
                           "version": _client_version()},
        }, timeout=timeout)
        if isinstance(res, dict):
            self.server_info = res.get("serverInfo") or {}
            self.capabilities = res.get("capabilities") or {}
        self.notify("notifications/initialized")
        return res if isinstance(res, dict) else {}

    def list_tools(self, timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        res = self.request("tools/list", {}, timeout=timeout)
        tools = (res or {}).get("tools") if isinstance(res, dict) else None
        return [t for t in (tools or []) if isinstance(t, dict)]

    def call_tool(self, tool: str, arguments: Dict[str, Any],
                  timeout: Optional[float] = None) -> Dict[str, Any]:
        res = self.request("tools/call", {"name": tool, "arguments": arguments or {}},
                           timeout=timeout or self.cfg.get("call_timeout"))
        return res if isinstance(res, dict) else {"content": []}

    def stderr_tail(self, n: int = 3) -> str:
        tail = [x for x in self._stderr[-n:] if x.strip()]
        return ("；stderr: " + " | ".join(tail)) if tail else ""

    def _died_message(self) -> str:
        """进程没了的那句话：**带上退出码**。

        退出码是排查 MCP server 的第一个线索（3 常是它自己 `os._exit`，1 是异常退出，
        空 = 还没来得及收尸）。只说"stdout 已关闭"等于把最有用的信息丢掉。
        """
        rc = None
        if self.proc is not None:
            rc = self.proc.poll()
            if rc is None:
                try:
                    rc = self.proc.wait(timeout=0.5)
                except Exception:  # noqa: BLE001 —— 收不到就算了，不猜
                    rc = None
        if isinstance(rc, int):
            return f"MCP server {self.name} 已退出（stdout 关闭，exit {rc}）"
        return f"MCP server {self.name} 的 stdout 已关闭（进程可能已退出）"


def _client_version() -> str:
    try:
        from core import version
        return str(version.__version__)
    except Exception:  # noqa: BLE001 —— 版本号取不到不该影响握手
        return "0"


# ============================================================
# 多 server 管理 + 工具注册
# ============================================================

class McpManager:
    """多个 MCP server 的生命周期与调用入口。

    设计取舍：
    - **一个 server 起不来不影响其它**：`start()` 记录状态并在 `/mcp` 里如实展示，
      而不是整个会话失败。用户在配置里写错一个路径是常事。
    - **工具注册后才刷新执行层的权限集合**：否则新工具会落在
      "既不在 READ_TOOLS 也不在 WRITE_TOOLS"的缝里（那条缝的默认行为是拒绝，
      但报出来的理由会变成"未知工具"，看着像 bug）。
    """

    def __init__(self, configs: Dict[str, Dict[str, Any]], project_root: str = ".",
                 log: Optional[Any] = None) -> None:
        self.project_root = project_root
        self.log = log
        self.states: Dict[str, McpServerState] = {}
        self.clients: Dict[str, McpStdioClient] = {}
        for name, cfg in (configs or {}).items():
            state = McpServerState(name=name, config=cfg)
            if not cfg.get("enabled", True):
                state.status = "已禁用"
            self.states[name] = state

    def start(self) -> None:
        for name, state in self.states.items():
            if state.status == "已禁用":
                continue
            client = McpStdioClient(name, state.config, self.project_root)
            try:
                client.start(timeout=float(state.config.get("timeout") or 20.0))
                state.status = "就绪"
                state.server_info = client.server_info
                self.clients[name] = client
            except McpError as e:
                state.status = "失败"
                state.error = str(e)
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

    def load_tools(self) -> List[Dict[str, Any]]:
        """拉取每个就绪 server 的工具列表，写进状态。返回全部 spec dict。"""
        specs: List[Dict[str, Any]] = []
        for name, client in self.clients.items():
            try:
                tools = client.list_tools(timeout=float(
                    self.states[name].config.get("timeout") or 20.0))
            except McpError as e:
                self.states[name].status = "失败"
                self.states[name].error = f"tools/list 失败: {e}"
                continue
            self.states[name].tools = tools
            specs.extend(tool_spec(name, t) for t in tools)
        return specs

    def register_into(self, executor: Any, registry: Any) -> List[str]:
        """把 MCP 工具注册进注册表，并把 executor 挂上管理器。

        返回注册成功的工具名（便于断言与 `/mcp` 展示）。
        """
        specs = self.load_tools()
        registered: List[str] = []
        for s in specs:
            try:
                registry.register(registry.ToolSpec(
                    name=s["name"], permission=s["permission"],
                    description=s["description"], parameters=s["parameters"],
                    # pass_tool_name=True：一个 handler 服务所有 MCP 工具
                    handler="_exec_mcp_tool", pass_tool_name=True), replace=True)
                registered.append(s["name"])
            except Exception:  # noqa: BLE001 —— 单个工具注册失败不该拖垮整轮
                continue
        if registered:
            executor.mcp = self
            try:
                import execution_layer
                execution_layer.refresh_tool_sets()
            except Exception:  # noqa: BLE001
                pass
        return registered

    def call_tool(self, full_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用一个 MCP 工具。返回 dict（由 tools/base 映射成 ExecutionResult）。

        返回结构（不抛异常，让上层统一成工具结果）：ok / text / is_error /
        error_code / message / elapsed / server / tool
        """
        parsed = parse_spec_name(full_name)
        if not parsed:
            return {"ok": False, "error_code": "400",
                    "message": f"不是 MCP 工具名: {full_name}"}
        server, tool = parsed
        client = self.clients.get(server)
        if client is None:
            st = self.states.get(server)
            why = (st.error if st and st.error else "未启动或未配置")
            return {"ok": False, "error_code": "503",
                    "message": f"MCP server {server} 不可用（{why}）"}
        t0 = time.time()
        try:
            res = client.call_tool(tool, arguments)
        except McpTimeout as e:
            # 超时不一定是"对面死了"：它可能只是慢。但**如果它确实已经退出**，
            # 状态就得如实更新 —— 否则 /mcp 一直显示"就绪"，用户会一直重试。
            self._mark_dead_if_process_gone(server)
            return {"ok": False, "error_code": "504", "message": str(e),
                    "elapsed": time.time() - t0, "server": server, "tool": tool}
        except McpProcessDied as e:
            self.states[server].status = "失败"
            self.states[server].error = str(e)
            return {"ok": False, "error_code": "503", "message": str(e),
                    "elapsed": time.time() - t0, "server": server, "tool": tool}
        except McpError as e:
            self._mark_dead_if_process_gone(server)
            return {"ok": False, "error_code": "500", "message": str(e),
                    "elapsed": time.time() - t0, "server": server, "tool": tool}
        err = is_error_result(res)
        return {"ok": not err, "is_error": err, "text": flatten_content(res),
                "error_code": "" if not err else "500",
                "message": "" if not err else "MCP 工具报告执行失败（isError）",
                "elapsed": time.time() - t0, "server": server, "tool": tool}

    def _mark_dead_if_process_gone(self, server: str) -> bool:
        """子进程没了就把状态改成失败。返回是否已死。"""
        client = self.clients.get(server)
        proc = getattr(client, "proc", None)
        if proc is None or proc.poll() is None:
            return False
        st = self.states.get(server)
        if st is not None and st.status != "失败":
            st.status = "失败"
            st.error = f"进程已退出（exit {proc.returncode}）"
        return True


    def status(self) -> List[Dict[str, Any]]:
        """给 `/mcp` 与断言用的状态快照。

        `tools` 是**数量**、`tool_names` 是名字列表 —— 早先把两者混成一个字段，
        调用方一取 `[:20]` 就炸（测试当场抓到的）。数量与清单是两件事。
        """
        out: List[Dict[str, Any]] = []
        for name, st in self.states.items():
            out.append({
                "name": name, "status": st.status, "error": st.error,
                "tools": len(st.tools),
                "tool_names": [str(t.get("name")) for t in st.tools],
                "command": " ".join([str(st.config.get("command") or "")]
                                    + list(st.config.get("args") or []))[:120],
                "instructions": str((st.server_info or {}).get("name") or ""),
            })
        return out

    def close(self) -> None:
        for c in list(self.clients.values()):
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        self.clients.clear()
