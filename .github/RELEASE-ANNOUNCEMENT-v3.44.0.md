# ACE v3.44.0 · 把执行层交给别人的 agent

> 本条同时作为 v3.44.0 的发布说明，可直接粘进 Release。
> 一行摘要：**ACE 现在是一个 MCP server** —— Claude Code / Cursor / Codex 这类 host 负责想，
> ACE 负责"这一下到底能不能动"；审批沿用 fail-close + 授权令放行，每次调用进台账。

```bash
python ai_code.py --mcp --project-root /path/to/project                # 只读（默认）
python ai_code.py --mcp --project-root /path/to/project --permission write
```

挂上去只要一段 JSON（三种 host 的写法见 `docs/MCP-SERVER.md`）：

```json
{ "mcpServers": { "ace": { "command": "python",
    "args": ["/abs/path/ace/ai_code.py", "--mcp", "--project-root", "/abs/path/proj"] } } }
```

## 这一版给你什么

- **第四个前端**：`ace --mcp` 在 stdio 上说 JSON-RPC 2.0（自己实现，不引 SDK）。`tools/list`
  给的是**白名单**；`tools/call` 走执行层裁决后执行 —— **本进程一行模型调用都没有**。
- **不发明新政策**：能不能动仍由执行层的三个旋钮决定（权限档 / 授权令 / 沙箱）。默认只读；
  要问人的那几处在 headless 下 fail-close 拒绝，**拒绝文本写明缺什么**（提权，或签一张令）；
  **配了覆盖它的令就静默放行**（roots / 可逆性下限 / 不可逆额度都是真边界）。
- **两种失败分得清**：工具被拒是 `content` + `isError`（host 的 agent 拿它继续想），
  协议/参数错误才是 JSON-RPC error —— 把前者塞进 error 会让 host 以为"服务器坏了"。
- **可核的账**：每次调用进会话台账（`source=mcp` + MAC 链），归属记成**非用户来源**。

## 立项过程中被实测改掉的三处

1. **接错了入口** —— 第一版接 `run_tool_direct`（那是给"人自己敲的命令"用的，刻意跳过整个权限
   裁决阶段）。探针当场拍到 write 档下 `terminal_exec` 直接执行、项目外已存在文件也能改。
   现在走新的 `run_tool_external`；`[72]` 留了一条对照断言钉住差别。
2. **1 MiB 行长上限误杀合法写入** —— 探针实测 2 MiB 的 `file_write` 被协议层拒。上限改 8 MiB。
3. **超限/坏 JSON 回 `id: null` 让客户端死等**（探针第一次跑死等 600 s）—— 现在尽力把 id 抠回来。

## 验证到什么程度（以及没验到什么）

- `test_all` 新增段 `[72]` **32 条**（含真 `ExecutionLayer` 的裁决与授权令两半）；
  `e2e/mcp_probe.py` 以真进程验 **39 条**（stdout 零杂音 / EOF 干净收工 / 台账 / 配置里的令生效 /
  2 MiB 真落盘）；全量 **2405 / 2405**（0 跳过）、`ruff` 零命中、CI 三平台全绿。
- **没有在任何真实 MCP host 上跑过。** 本机装了 Claude Code，但它被配置成接 DeepSeek 的
  Anthropic 兼容端点，headless 模式报 `unrecognized_model` —— 我没有继续动那台机器上的凭据与额度。
  **"某个真 host 通过 ACE 写了一个文件"这件事还没有发生**，本版不把它说成已经发生。
- 未做：`elicitation`（服务端反向问用户）；`resources`/`prompts`；TCP/HTTP transport。
- 已知边界：项目外**新建**文件不问人（ACE 既有政策，CLI 与模型路径同口径）；单条消息上限 8 MiB
  且没有分块写工具；请求串行处理。

**完整细节** → [`docs/RELEASE-NOTES-v3.44.0.md`](docs/RELEASE-NOTES-v3.44.0.md) · [`CHANGELOG.md`](CHANGELOG.md)
**设计文档** → [`docs/design/MCP-SERVER.md`](docs/design/MCP-SERVER.md)　**怎么用/排障** → [`docs/MCP-SERVER.md`](docs/MCP-SERVER.md)

本项目有一条纪律：**没真正跑过的，不许说成"应该没问题"。**

---

## English

> This doubles as the v3.44.0 release note — paste it into the Release as-is.
> One-line summary: **ACE is now an MCP server** — Claude Code / Cursor / Codex do the thinking,
> ACE decides whether a single tool call may run. Approvals stay fail-close + mandate; every call
> lands in the ledger.

```bash
python ai_code.py --mcp --project-root /path/to/project                # read-only (default)
python ai_code.py --mcp --project-root /path/to/project --permission write
```

## What this version gives you

- **A fourth front end**: `ace --mcp` speaks JSON-RPC 2.0 over stdio (hand-rolled, no SDK).
  `tools/list` is a **whitelist**; `tools/call` goes through the execution layer and then runs —
  **this process never calls a model**.
- **No new policy**: which tools are reachable is still decided by permission level, mandate and
  sandbox. Read-only by default; anything that would ask a human is refused with an **actionable
  reason** (raise the level, or sign a mandate); **a covering mandate lets it through silently**
  (roots, recovery floor and irreversible quota are real bounds).
- **Two kinds of failure, kept apart**: a refused tool is `content` + `isError` (the host's agent
  keeps thinking with it); protocol/parameter mistakes are JSON-RPC errors.
- **An auditable trail**: every call lands in the session ledger (`source=mcp`, MAC-chained), and
  attribution is recorded as **not-the-user**.

## Three things measurement changed during the build

1. **Wrong entry point** — v1 called `run_tool_direct`, which exists for commands *the human typed*
   and therefore skips the whole permission stage. The probe caught `terminal_exec` executing
   outright and outside-project files being overwritten, with no confirmation. It now goes through
   `run_tool_external`, and `[72]` pins that difference with a contrast assertion.
2. **A 1 MiB line cap killed legitimate writes** — a 2 MiB `file_write` was refused at the protocol
   layer. The cap is 8 MiB now.
3. **`id: null` on an oversized/broken line made clients wait forever** (the probe hung for 600 s on
   the first run) — the id is now recovered from the first 4 KiB of the line.

## How far it is verified (and what is not)

- 32 new assertions in section `[72]` (including real-`ExecutionLayer` verdicts and both halves of
  the mandate story); `e2e/mcp_probe.py` drives a **real** `ace --mcp` subprocess for 39 more
  (pristine stdout, clean EOF exit, ledger, a config-file mandate taking effect, a 2 MiB write
  landing on disk); full suite **2405 / 2405** (nothing skipped this run), `ruff` clean, CI green on
  three Python versions.
- **It has not been run against any real MCP host.** Claude Code is installed on this machine but is
  pointed at DeepSeek's Anthropic-compatible endpoint and reports `unrecognized_model` in headless
  mode — we did not touch that machine's credentials or quota. So **"a real host wrote a file
  through ACE" has not happened yet**, and this release does not claim otherwise.
- Not done: `elicitation` (server-initiated questions), `resources`/`prompts`, TCP/HTTP transport.
- Known bounds: creating a *new* file outside the project does not ask (existing ACE policy, same
  as CLI and model paths); one message is capped at 8 MiB with no chunked write tool; requests are
  handled serially.

**Full details** → [`docs/RELEASE-NOTES-v3.44.0.md`](docs/RELEASE-NOTES-v3.44.0.md) · [`CHANGELOG.md`](CHANGELOG.md)
**Design doc** → [`docs/design/MCP-SERVER.md`](docs/design/MCP-SERVER.md)　**Usage / troubleshooting** → [`docs/MCP-SERVER.md`](docs/MCP-SERVER.md)

The project has one rule: **anything not actually run does not get described as "should be fine".**
