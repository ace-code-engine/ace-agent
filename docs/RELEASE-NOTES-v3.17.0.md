# ACE v3.17.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3170-2026-09-19)。

## 一句话

ACE 现在真的会说 MCP：你配置一个 server，它的工具就出现在模型手里——权限、审批、审计照旧。

## ✨ 接上外部工具：MCP（stdio）

在 `~/.ai_code.json` 里加一段：

```json
"mcp_servers": {
  "fs": {"command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
         "timeout": 20, "call_timeout": 120}
}
```

或者把它写进项目根的 `.ace/mcp.json`（同名时**项目级覆盖用户级**）。启动后：

- ACE 用 stdio JSON-RPC 2.0 跟它握手（`initialize` → `tools/list`），把每个工具注册成 **`mcp__fs__read_file`** 这样的名字，**schema 原样透传**（MCP 用的就是 JSON Schema，转一道只会丢信息）
- 模型在工具列表里直接看到它们，调用结果进会话日志，`/audit` 里逐条可查
- `/mcp` 看状态：就绪 / 失败 / 已禁用、失败原因、启动命令、以及**拿到了哪些工具**

这不是"把 MCP 工具手写成 Python 函数"那种接入——协议是真的：握手、工具枚举、调用、反向请求、超时、进程猝死都按协议处理。

## 🛡️ 安全边界（这段最要紧）

**MCP server 跑在 ACE 的沙箱之外。** 它是你配置的一个子进程，它内部能读写什么、能连哪里，是它的代码决定的。

- 执行层管的是**"ACE 要不要调用它"**：权限档、审批策略、审计日志照常。
- 执行层**管不了"它内部干了什么"**。
- 所以：**只把你信得过的 server 写进配置**。这一条没有技术兜底。

权限默认从严：对面自己声明 `annotations.readOnlyHint: true` 才按只读算，**其余一律按写**（readonly 会话下需要授权）。对面说只读是它自己声明的，说错话的代价不该由你承担。

## ⚙️ 出问题时你看到什么

失败是**分开报**的，因为处置方式不同：

| 情况 | 报什么 | 你该做什么 |
|---|---|---|
| server 没起来 / 没声明这个工具 | `503` + "未注册：server「x」没启动或没声明「y」" | 看 `/mcp` 的状态与失败原因 |
| 调用超时 | `504` + 超时秒数 | 对面太慢；确认它是不是卡住了 |
| 进程猝死 | `503` + **退出码** | 对面崩了；stderr 尾巴会一起带出来 |
| 协议错（比如对面把日志打到 stdout） | `500` + 原始那一行 | 那是 server 的问题，不是猜出来的 |
| 对面自己说失败（`isError`） | 工具失败，但正文照旧回传 | 模型能看到它说了什么 |

子进程会被**显式收掉**（退出时 + `/clear` 重建时）。Windows 上父进程退出不会带走子进程，所以这一步是防孤儿 `npx`/`python` 的唯一办法。

## 📋 现在还没有的（写在明面上）

- **只支持 stdio 传输**。HTTP/SSE 的 MCP server 还连不上，没实现也不假装支持。
- server 发起的反向请求（sampling / roots / elicitation）目前一律回 `-32601`（未实现）——不让对面干等，但也没有真正实现。

## 📋 兼容性

- 无破坏性变更：不配 `mcp_servers` 时行为与之前完全一致（不启动任何子进程）
- 新增 8 个 i18n 键，中英日三语齐全

---

# ACE v3.17.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3170-2026-09-19).

## In one line

ACE now actually speaks MCP: configure a server and its tools land in the model's hands — with permissions, approval and audit unchanged.

## ✨ External tools: MCP over stdio

Add to `~/.ai_code.json`:

```json
"mcp_servers": {
  "fs": {"command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
         "timeout": 20, "call_timeout": 120}
}
```

Or put it in a project-level `.ace/mcp.json` (project wins on name clashes). Then:

- ACE performs a real stdio JSON-RPC 2.0 handshake (`initialize` → `tools/list`) and registers each tool as **`mcp__fs__read_file`**, passing the **input schema through unchanged** (MCP already uses JSON Schema; converting it only loses information)
- The model sees those tools directly; every call and result lands in the session log and shows up in `/audit`
- `/mcp` shows status — ready / failed / disabled, the failure reason, the launch command, and **which tools were actually received**

This is not "hand-writing MCP tools as Python functions": handshake, tool enumeration, calls, server-initiated requests, timeouts and process death are all handled as protocol.

## 🛡️ The security boundary (read this part)

**An MCP server runs outside ACE's sandbox.** It is a child process you configured; what it can read, write or reach is decided by its own code.

- The execution layer decides **whether ACE calls it**: permission level, approval policy and audit apply as usual.
- The execution layer **cannot** control what it does internally.
- Therefore: **only add servers you trust.** There is no technical backstop for this one.

Permissions default to strict: a tool counts as read-only only if the server declares `annotations.readOnlyHint: true`; **everything else is treated as a write** (thus needing authorisation in a readonly session). A server claiming read-only is still just a claim, and the cost of a wrong claim should not land on you.

## ⚙️ What you see when things go wrong

Failures are reported **separately**, because they need different responses:

| Situation | Reported as | What to do |
|---|---|---|
| Server didn't start, or never declared that tool | `503` + "unregistered: server `x` is not up or does not declare `y`" | Check `/mcp` for status and reason |
| Call timed out | `504` + the timeout | The server is slow — check whether it is stuck |
| Process died mid-call | `503` + the **exit code** | It crashed; the stderr tail comes with it |
| Protocol error (e.g. it logged to stdout) | `500` + the offending line | That is the server's bug, not something we guess at |
| The server itself reported failure (`isError`) | Tool failure, body still returned | The model gets to see what it said |

Child processes are **closed explicitly** (on exit and when `/clear` rebuilds the execution layer). On Windows a parent exiting does not reap its children, so this is the only thing standing between you and a pile of orphaned `npx`/`python` processes.

## 📋 Not there yet (stated plainly)

- **stdio transport only.** HTTP/SSE MCP servers cannot be reached; it is not implemented and we do not pretend otherwise.
- Server-initiated requests (sampling / roots / elicitation) currently get `-32601` (not implemented) — the server is not left hanging, but the capability is genuinely absent.

## 📋 Compatibility

- No breaking changes: without `mcp_servers` configured, behaviour is identical (no child processes are started)
- 8 new i18n keys, complete in Chinese, English and Japanese
