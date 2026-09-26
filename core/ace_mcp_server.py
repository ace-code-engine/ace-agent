#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ace_mcp_server —— MCP（Model Context Protocol）**服务端**：让外部 agent 借用 ACE 的执行层

## 这个模块解决什么

在此之前 ACE 只有三个前端（CLI 主循环 / Textual 界面 / `--serve` 的独立进程前端），
而它们都是"ACE 自己在干活"。这个模块把方向反过来：**Claude Code / Cursor / Codex 这类
MCP host 负责想，ACE 负责"这一下到底能不能动"** —— host 的一次 `tools/call` 就是一次
经过执行层裁决的工具执行（`ExecutionLayer.run_tool_direct(..., source="mcp")`）。

## 协议：自己实现，不引 SDK

`core/ace_mcp.py` 已经写了协议的另一侧（客户端：initialize / tools/list / tools/call /
notifications，含 server→client 的 sampling）。服务端是它的镜像，形状都在仓库里，
所以按仓库的依赖纪律（离线 wheel、核心零依赖）手写这一层，不引入新包。

MCP 的线上格式是 **JSON-RPC 2.0 over stdio，一行一个消息**：

- 请求：`{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}`
- 应答：`{"jsonrpc":"2.0","id":1,"result":{...}}` 或 `{"jsonrpc":"2.0","id":1,"error":{...}}`
- 通知：没有 `id`，**不许应答**（应了就是协议违规）

注意这与 `core/ace_serve.py` 的帧**刻意不同**（那边是 `{"v":1,"type":"req",...}`，
并且明确论证过"不引完整 JSON-RPC"）。两处共用的是引擎与体检手法，不是传输层。

## 两种"失败"要分清（这一层最容易做错的地方）

| 情形 | 表达方式 |
|---|---|
| **工具执行失败**（权限不足、路径越界、命令非零退出…） | `result` 里 `{"content":[...],"isError":true}` —— 这是**业务结果**，不是协议错误 |
| **协议/参数错误**（方法不存在、`name` 缺失、没握手就发业务请求…） | JSON-RPC `error` 对象（`-32601` / `-32602` / `-32002` …） |

把第一种塞进 `error` 会让 host 以为"服务器坏了"而不是"这一步被拒了"（拒绝理由正是
host 的 agent 要继续思考的输入）；把第二种塞进 `isError` 则会让 host 的框架层漏掉它。

## 这个模块**不**做的事

- 不碰引擎：工具清单与调用都是**注入**进来的两个可调用对象（`list_tools` / `call_tool`），
  所以这一层可以脱离整个 ACE 单测（`test_all` 就是这么验的）。接线在 `ai_code.py::_run_mcp`。
- 不做 elicitation（服务端反向问用户）、不做 resources/prompts 能力、不做 TCP/HTTP：
  理由见 `docs/design/MCP-SERVER.md` 的"明确不做"。
- 不写 stdout 之外的东西：stdout **被协议独占**，所有诊断走 stderr（与 ace_serve 同一纪律）。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional

from core import version as _version

__all__ = [
    "PROTOCOL_VERSION_LATEST", "SUPPORTED_PROTOCOL_VERSIONS", "MAX_LINE_BYTES",
    "PARSE_ERROR", "INVALID_REQUEST", "METHOD_NOT_FOUND", "INVALID_PARAMS",
    "INTERNAL_ERROR", "SERVER_NOT_INITIALIZED",
    "MCP_TOOL_NAMES", "MCP_TOOL_HIDDEN", "mcp_tools", "recover_id",
    "McpProtocolError", "McpServer", "tool_error", "tool_text",
]

# ---------------------------------------------------------------- 协议常量

#: 我们实现的最新一版协议。客户端要更旧的版本时按它自己报的版本回（只要在支持列表里）。
PROTOCOL_VERSION_LATEST = "2025-06-18"

#: 认识的协议版本（由新到旧）。客户端报的版本**不在**这里时：回最新版并让它自己决定 ——
#: 这是规范允许的做法（服务端必须回一个自己支持的版本），而不是"猜一个能跑的"。
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

#: 单行上限。**这条上限保护的是一致性，不是内存** —— 老实说清楚，因为它很容易被读成后者：
#: `readline()` 已经把整行读进内存了，所以"超限就拒"是**事后**检查。要真限制内存得换成
#: 按块读 + 提前拒，第一版不做（写明在这里，而不是留一句看起来在保护什么的话）。
#:
#: 取值 8 MiB：MCP 把 `arguments` 整包放进**一行** JSON 里，所以"文件内容"这种参数天然撑长行
#: —— 引擎侧 `file_write` 本来能写任意大小（模型路径不过行协议）。第一版直接搬了 `ace_serve`
#: 的 1 MiB，`e2e/mcp_probe.py` 的实测结果是**2 MiB 的写入在协议层被拒**，症状像"ACE 不能写
#: 大文件"。8 MiB 仍然是个硬边界（对面写进死循环时不会无限增长），但容得下正经 payload。
#: host 自己可能设更小的上限，那是它的事。
MAX_LINE_BYTES = 8 << 20

#: 从"解析不了的行"里尽力抠 id 用。只看开头 4 KiB，不解析整条大消息。
_ID_HEAD_RE = re.compile(r'"id"\s*:\s*("[^"]{0,64}"|-?\d{1,20})')


def recover_id(line: str) -> Any:
    """超大行 / 坏 JSON 里尽力把 `id` 抠出来。

    为什么必须有：JSON-RPC 允许"解析不了就回 `id: null`"，但那样**客户端会一直等它自己那个
    id** —— 这不是推测，`e2e/mcp_probe.py` 的大 payload 用例第一次跑就死等超时（600 s）。
    id 按惯例在消息开头（`{"jsonrpc":"2.0","id":3,"method":...}`），只看前 4 KiB 就能取到，
    不必为了一个 id 去解析 12 MiB。抠不到就如实回 null（规范允许），客户端该有自己的超时。
    """
    m = _ID_HEAD_RE.search(line[:4096])
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith('"'):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        return None

# JSON-RPC 2.0 标准错误码
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
#: MCP 规范在标准码之外补的：还没握手就发业务请求。
SERVER_NOT_INITIALIZED = -32002

# ---------------------------------------------------------------- 暴露面

#: 经 MCP 暴露出去的工具。**白名单**：注册表将来新增工具，默认是不暴露 ——
#: 要暴露得有人显式往这里加一行，而不是某天悄悄多出一个外部 agent 能调的工具。
MCP_TOOL_NAMES = (
    # 只读
    "terminal_view", "file_read", "grep", "glob", "kb_search", "kb_list",
    "skill_list", "skill_load", "parse_document", "math_calc", "datetime_now",
    "search", "search_read",
    # 写 / 执行（要不要真放行由权限档与授权令决定，不由这张表决定）
    "file_write", "file_delete", "file_move", "str_replace", "edit_file",
    "terminal_exec", "code_execute",
    # 联网 / 数据库 / 浏览器
    "api_get", "api_post", "db_query", "db_write",
    "browser_open", "browser_navigate", "browser_click", "browser_type",
    # 发通知（会落一条本地通知，不改仓库）
    "notify_send",
)

#: **刻意不暴露**的工具与理由。写成代码里的数据，免得以后有人"顺手补全"：
#: 每一条被排除都有具体原因，不是遗漏。
MCP_TOOL_HIDDEN: Dict[str, str] = {
    "request_permission": "ACE 自己那套授权往返的控制面；MCP 侧没有可答的往返（见立项卡第四节）",
    "plan_propose": "同上：属于 ACE 对话循环的控制面，host 有自己的计划机制",
    "todo_write": "host 自己有待办清单；经 ACE 再存一份只是把两边的账都搅在一起",
    "subagent": "会在 ACE 侧再起一层 agent：成本、并发与归属都变得说不清",
    "goal_create": "目标生命周期属于「谁在驱动」这件事，驱动方是 host",
    "goal_update": "同上",
    "goal_status": "同上",
    "image_generate": "会产生外部费用，且与「能不能动这个对象」这条主线无关",
}


def mcp_tools(specs: Iterable[Any]) -> List[Dict[str, Any]]:
    """注册表 → MCP `tools/list` 的条目（**只发白名单里的**）。

    `inputSchema` 直接用 `ToolSpec.parameters`（它本来就是 JSON Schema），但**深拷贝** ——
    理由与 `tools.registry.openai_tools()` 逐字相同：ToolSpec 是 frozen dataclass，
    frozen 只冻字段绑定，冻不住字段指向的那个 dict；调用方随手改一下 schema 就改到了
    注册表本体，而且全进程可见。

    白名单里的名字在注册表里找不到（或没标 `expose`）时**直接抛**：静默少发一个工具，
    症状是"host 说它没有这个工具"，排查方向会跑到 host 那边去 —— 这种错要在这里就炸。
    """
    from copy import deepcopy

    by_name = {s.name: s for s in specs}
    missing = [n for n in MCP_TOOL_NAMES if n not in by_name]
    if missing:
        raise KeyError(f"MCP 白名单里的工具不在注册表里: {missing}（名字写错了？）")
    not_exposed = [n for n in MCP_TOOL_NAMES if not by_name[n].expose]
    if not_exposed:
        raise KeyError(f"MCP 白名单里的工具在注册表里标了 expose=False: {not_exposed}")
    # 被排除的那些不许出现在白名单里（两份名单互相打架时，宁可当场炸）
    conflict = [n for n in MCP_TOOL_NAMES if n in MCP_TOOL_HIDDEN]
    if conflict:
        raise KeyError(f"工具同时出现在暴露与排除名单里: {conflict}")
    return [{"name": n,
             "description": by_name[n].description,
             "inputSchema": deepcopy(by_name[n].parameters)}
            for n in MCP_TOOL_NAMES]


# ---------------------------------------------------------------- 工具结果的两种形体

def tool_text(text: str, *, is_error: bool = False) -> Dict[str, Any]:
    """工具结果：走 `result`，失败时带 `isError: true`（**不是** JSON-RPC error）。"""
    out: Dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        out["isError"] = True
    return out


def tool_error(text: str) -> Dict[str, Any]:
    """工具被拒/失败。理由要**可执行**（host 的 agent 靠它决定下一步），所以原文照传。"""
    return tool_text(text, is_error=True)


# ---------------------------------------------------------------- 协议错误

class McpProtocolError(Exception):
    """协议/参数层面的错误 → JSON-RPC `error` 对象。"""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_error(self) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


# ---------------------------------------------------------------- 服务端

class McpServer:
    """JSON-RPC 2.0 over stdio 的 MCP 服务端。

    `handle()` 是**纯函数**式的：吃一个已解析的消息，吐一个要发的消息（或 None 表示
    "这是通知，不许应答"）。I/O 在 `serve_forever()` 里，只有几十行 —— 于是协议行为
    可以脱离管道单测，而管道本身只需要测"读一行/写一行/EOF"。
    """

    def __init__(self, list_tools: Callable[[], List[Dict[str, Any]]],
                 call_tool: Callable[[str, Dict[str, Any]], Dict[str, Any]],
                 *, server_name: str = "ace",
                 server_version: Optional[str] = None,
                 instructions: str = "") -> None:
        self._list_tools = list_tools
        self._call_tool = call_tool
        self.server_name = server_name
        self.server_version = server_version or _version.__version__
        self.instructions = instructions
        self.initialized = False
        self.client_info: Dict[str, Any] = {}
        self.protocol_version: Optional[str] = None

    # ---------------- 纯逻辑：一个消息进，一个消息出

    def handle(self, msg: Any) -> Optional[Dict[str, Any]]:
        """派发一条消息。返回 None = 不需要应答（通知）。"""
        if isinstance(msg, list):
            # MCP 2025-06-18 起移除了 JSON-RPC 批处理。明说而不是当没看见：
            # 静默不理会让 host 一直等应答。
            return self._error(None, INVALID_REQUEST, "不支持批处理（JSON-RPC batch）")
        if not isinstance(msg, dict):
            return self._error(None, INVALID_REQUEST, "消息必须是 JSON 对象")
        if msg.get("jsonrpc") != "2.0":
            return self._error(msg.get("id"), INVALID_REQUEST, 'jsonrpc 字段必须是 "2.0"')
        method = msg.get("method")
        if not isinstance(method, str) or not method:
            return self._error(msg.get("id"), INVALID_REQUEST, "缺 method")
        has_id = "id" in msg
        if not has_id:
            return self._notify(method, msg.get("params"))       # 通知：不应答
        try:
            result = self._dispatch(method, msg.get("params"))
        except McpProtocolError as e:
            return self._error(msg["id"], e.code, e.message, e.data)
        except Exception as e:                                    # noqa: BLE001
            # 真 bug 才走这里：工具**被拒**是业务结果（isError），不是异常。
            return self._error(msg["id"], INTERNAL_ERROR,
                               f"{type(e).__name__}: {e}")
        return {"jsonrpc": "2.0", "id": msg["id"], "result": result}

    def _dispatch(self, method: str, params: Any) -> Dict[str, Any]:
        if method == "initialize":
            return self._initialize(params)
        if method in ("tools/list", "tools/call", "ping"):
            if not self.initialized:
                raise McpProtocolError(SERVER_NOT_INITIALIZED,
                                       "先发 initialize 再发业务请求")
            if method == "ping":
                return {}
            if method == "tools/list":
                return {"tools": self._list_tools()}
            return self._tools_call(params)
        raise McpProtocolError(METHOD_NOT_FOUND, f"不认识的方法: {method}")

    def _initialize(self, params: Any) -> Dict[str, Any]:
        if not isinstance(params, dict):
            raise McpProtocolError(INVALID_PARAMS, "initialize 的 params 必须是对象")
        want = params.get("protocolVersion")
        if not isinstance(want, str) or not want:
            raise McpProtocolError(INVALID_PARAMS, "initialize 缺 protocolVersion")
        # 规范：服务端回一个**自己支持的**版本。客户端报的版本不认识就回最新版，
        # 由它决定要不要继续 —— 而不是假装支持一个我们没实现的东西。
        self.protocol_version = (want if want in SUPPORTED_PROTOCOL_VERSIONS
                                 else PROTOCOL_VERSION_LATEST)
        self.client_info = dict(params.get("clientInfo") or {})
        self.initialized = True
        out: Dict[str, Any] = {
            "protocolVersion": self.protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self.server_name, "version": self.server_version},
        }
        if self.instructions:
            out["instructions"] = self.instructions
        return out

    def _tools_call(self, params: Any) -> Dict[str, Any]:
        if not isinstance(params, dict):
            raise McpProtocolError(INVALID_PARAMS, "tools/call 的 params 必须是对象")
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise McpProtocolError(INVALID_PARAMS, "tools/call 缺 name")
        name = name.strip()
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise McpProtocolError(INVALID_PARAMS, "arguments 必须是对象")
        # ACE 内部的 tool_call 形状是**扁平**的（`{"tool":名, ...参数}`）。
        # 这里把 MCP 的 `arguments` 摊平——但要是 host 在 arguments 里塞了 `tool`，
        # 那就是形状误解，明说而不是悄悄丢掉它。
        if "tool" in args:
            raise McpProtocolError(
                INVALID_PARAMS,
                'arguments 里不要放 "tool"（工具名走 params.name；'
                "ACE 的参数就是这个工具自己的参数）")
        known = {t["name"] for t in self._list_tools()}
        if name not in known:
            # 未知工具不是"工具失败"，是调用方写错了名字 → -32602。
            raise McpProtocolError(INVALID_PARAMS,
                                   f"未知工具: {name}（先 tools/list 看清单）")
        out = self._call_tool(name, dict(args))
        if not isinstance(out, dict) or "content" not in out:
            raise McpProtocolError(INTERNAL_ERROR, "call_tool 返回的形状不对（缺 content）")
        return out

    def _notify(self, method: str, params: Any) -> None:
        if method == "notifications/initialized":
            return None
        if method in ("notifications/cancelled", "notifications/progress"):
            return None                      # 我们不做取消/进度，但收到不该报错
        return None                          # 未知通知按规范一律忽略（不许回东西）

    @staticmethod
    def _error(id_: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": id_, "error": err}

    # ---------------- I/O：读一行、派发、写一行

    def handle_line(self, line: str) -> Optional[Dict[str, Any]]:
        """一行文本 → 要发的消息（None = 通知/空行）。

        解析失败/超限时**尽力把 id 抠回来**（`recover_id`）：否则客户端会一直等它自己那个 id
        —— 实测就是这么死等的。
        """
        if not line.strip():
            return None
        if len(line.encode("utf-8", "replace")) > MAX_LINE_BYTES:
            return self._error(recover_id(line), INVALID_REQUEST,
                               f"单行超过上限 {MAX_LINE_BYTES} 字节（这条上限是协议层的"
                               "一致性检查；大 payload 请拆小或换用别的工具）")
        try:
            msg = json.loads(line)
        except ValueError as e:
            return self._error(recover_id(line), PARSE_ERROR, f"不是合法 JSON: {e}")
        return self.handle(msg)

    def serve_forever(self, reader: Any = None, writer: Any = None) -> int:
        """主循环。EOF 是 host 的正常死法（关窗口 / 杀进程），算正常收工（返回 0）。"""
        reader = reader or _stdin()
        writer = writer or sys.stdout
        while True:
            line = reader.readline()
            if not line:                     # EOF：host 没了
                break
            out = self.handle_line(line)
            if out is not None:
                writer.write(json.dumps(out, ensure_ascii=False) + "\n")
                writer.flush()
        return 0


def _stdin() -> Any:
    """stdin 按 UTF-8 读（Windows 上默认代码页会把中文参数读成乱码）。"""
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    except Exception:                                                # noqa: BLE001
        pass
    return sys.stdin
