# v3.44.0 —— 把执行层交给别人的 agent（MCP server）

> 一句话：**ACE 不再只是"自己去干活的那个 agent"，而是任何 MCP host（Claude Code / Cursor /
> Codex / 自研）都能挂上的执行层** —— host 负责想，ACE 负责"这一下到底能不能动"。
> 设计与非目标 → `docs/design/MCP-SERVER.md`；怎么挂 → `docs/MCP-SERVER.md`。

```bash
python ai_code.py --mcp --project-root /path/to/project            # 只读（默认）
python ai_code.py --mcp --project-root /path/to/project --permission write
```

stdout 被协议独占（一行一个 JSON-RPC 消息）；引擎的日志与提示全部走 stderr ——
所以你在 host 的日志里看到的是"这台机器的边界是什么"，而不是被吞掉的诊断。

## 一、给 host 挂上（一分钟）

```json
{ "mcpServers": { "ace": {
    "command": "python",
    "args": ["/abs/path/ace/ai_code.py", "--mcp", "--project-root", "/abs/path/proj"],
    "env": { "PYTHONIOENCODING": "utf-8" } } } }
```

Claude Code / Cursor / Codex 各自的文件与键名见 `docs/MCP-SERVER.md` 第一节 —— 那三处是照各家
公开格式写的，**本机没在真 host 上跑过**（见第六节）。

## 二、它凭什么安全：不发明新政策

裁决点仍然只有一个（执行层），MCP 只是第四个前端。三个旋钮，与 CLI 完全同一套：

| 旋钮 | 决定什么 |
|---|---|
| **权限档**（默认 `readonly`） | 哪些工具够得着 |
| **授权令**（配置 `mandate`） | 哪些确认会收拢（roots / 可逆性下限 / 不可逆额度 / TTL） |
| 沙箱档（可选） | 跑起来之后还有没有第二道边界 |

- **两条失败分得清**：工具被拒 → `content` + `isError: true`（业务结论，host 的 agent 拿它
  继续想）；协议/参数错误才走 JSON-RPC `error`（`-32602` 未知工具、`-32002` 没握手…）。
- **headless 下"要问人"= 拒绝，但理由可执行**：拒绝文本会写明二选一 —— 让 ACE 的权限档允许
  这个工具，或签一张覆盖它的令。**配了覆盖它的令就静默放行**（这一半单独验过）。
- **暴露面是白名单**：`subagent` / `goal_*` / `todo_write` / `plan_propose` /
  `request_permission` / `image_generate` 刻意不发。
- **每次调用进台账**（`source=mcp` + MAC 链），归属记成**非用户来源**：外部 agent 要求动一个
  用户从没提过的路径 —— 这正是 RG-03 想量的那一类。

## 三、立项过程中被实测改掉的三处

1. **接错了入口**：第一版接 `run_tool_direct`，而它服务的是"**人自己敲的**命令"，刻意跳过整个
   `_stage_permission`。探针当场拍到 write 档下 `terminal_exec` **直接执行**、项目外**已存在**
   文件也能改，全都不问人。现在走新的 `ExecutionLayer.run_tool_external`；`run_tool_direct`
   的行为一个字没动。`[72]` 留了一条**对照断言**钉住差别。
2. **1 MiB 行长上限误杀合法写入**：探针实测 2 MiB 的 `file_write` 被协议层拒（症状像"ACE 不能
   写大文件"）。上限改为 8 MiB，并在注释里写明它**保护的是协议一致性、不是内存**。
3. **超限/坏 JSON 回 `id: null` 让客户端死等**：不是推测，探针第一次跑就死等了 600 s。
   现在尽力把 id 抠回来（只看开头 4 KiB），抠不到才回 null。

## 四、升级注意

| 变化 | 影响 |
|---|---|
| 新增 `--mcp` | **不加它，一切与 v3.43.0 逐字相同**（CLI / 界面 / `--serve` 都没动） |
| 崩溃/卡死类的协议缺陷修复 | 只影响 MCP 这一条新路径 |
| host 侧配置格式 | 那是 host 的事，以它的文档为准（本版没在真 host 上验过） |

## 五、测试与证据

- `test_all` 新增段 `[72]` **32 条**：暴露面 4 · 协议 13 · 行长与 id 3 · **真实裁决 5** ·
  翻译 3 · **授权令 3** · 对照 1。真实裁决那组用真 `ExecutionLayer`：write 档项目内真落盘、
  项目外已存在对象返回 `PERMISSION_REQUEST` 且文件内容一字未变、`terminal_exec` 与 readonly
  写工具各自 `PERMISSION_REQUEST`；令覆盖 → 项目外已存在文件**被真的改掉**。
- `e2e/mcp_probe.py`（新）：假装 MCP host 跟**真的** `ace --mcp` 子进程说 JSON-RPC，**39/39**。
  额外证明：stdout **一行杂音都没有** · host 断开（EOF）干净收工（退出码 0）· 台账有
  `source=mcp` 与那次拒绝且每条带 MAC · 配置里的令真会生效 · 2 MiB 写入真落盘且字节数正确。
- 全量以 `python test_all.py` 的实际输出为准（本次记录：本机 **2402 / 2402** 通过，跳过 3 项
  能力探测）；`ruff` 零命中；四张演示图重录并自校验通过（图内版本 → 3.44.0）。
- CI：三个 Python（3.10/3.11/3.12）× Linux + Windows + Docker 冒烟 + Rust 引擎 + Go 执行器
  全绿（`[72]` 在 Linux 上也跑）。

## 六、已知未验证（这一版最重要的一节）

- **没有在任何真实 MCP host 上跑过。** 本机装了 Claude Code（2.1.282），但它的配置是接到
  DeepSeek 的 Anthropic 兼容端点，headless（`-p`）模式下报 `unrecognized_model` —— 我没有
  继续动那台机器上的凭据与额度。所以：协议层与**真实执行层**都验过，但
  **"某台机器上、某个真 host 通过 ACE 写了一个文件"这件事还没有发生**。
  五步冒烟清单在 `docs/MCP-SERVER.md` 第五节；走完它才算"有人用过"，本版不把协议测试全绿
  当成那件事。
- `elicitation`（服务端反向问用户）没做：第一版靠"默认拒绝 + 令放行"，且**不假定** host 支持它。
- `resources` / `prompts` 能力、TCP/HTTP transport 明确不做（理由见立项卡的"明确不做"）。
- **项目外「新建」文件不问人**（只有"项目外**覆盖已存在**"才问）—— 这是 ACE 既有政策，CLI 与
  模型路径同口径；MCP 沿用它，把这条事实钉在探针里。要更严是一条**独立决定**（会同时改掉
  CLI 与模型路径）。
- 单条消息上限 8 MiB；**没有分块写工具**，所以更大的内容传不进去（这是已知限制）。
- 请求是**串行处理**的（一次一个工具）—— 执行层里的快照 / 台账 / `pending_permission` 都是
  "一次一个"的语义，第一版不做并发。
