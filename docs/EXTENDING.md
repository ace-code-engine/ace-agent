# 扩展（Extending ACE）—— 钩子 / 自定义命令 / 插件 / MCP

> ACE 的内置闸门是**通用**的（权限档、路径边界、AST 检查、快照回滚）。但每个团队
> 都有自己的规矩：不许改 `migrations/`、提交前必须过 lint、每次跑命令都要记一条审计。
> 这些规矩写进核心就是把一个团队的习惯变成所有人的负担。**扩展点**是给它们的出口。
>
> 一句话原则：**扩展是"用户自己的代码"，不在 ACE 的沙箱里。** 执行层管的是"要不要
> 执行它、以及它说的话算不算数"；它内部干什么，我们管不了 —— 所以只装你信得过的。

---

## 1. 事件钩子（hooks）

四个事件，插在关键节点上：

| 事件 | 时机 | 能做什么 |
|---|---|---|
| `session_start` | 会话建立 | 记一笔、准备环境（改不了任何决定） |
| `user_prompt` | 用户输入进模型**之前** | 追加/补充上下文，或直接拦下（这一轮不发） |
| `pre_tool` | 工具**执行之前**（权限已放行） | 拦截这一次调用，理由回给模型 |
| `post_tool` | 工具执行之后 | 看结果、记审计、补充上下文（改不了已发生的事） |
| `session_end` | 会话结束 | 收尾、汇总 |

### 协议（任何语言都能写）

```bash
# stdin 收到（一行 JSON）
{"event":"pre_tool","tool":"file_write","params":{"path":"migrations/001.sql"},
 "cwd":"/repo","session_id":"1789…jsonl","ace_version":"3.18.0"}

# stdout 回（可空）
{"decision":"block","reason":"migrations/ 下的文件必须人工改","additional_context":"…"}
```

- **退出码**：`0` = 放行；`2` = 拦截（`stderr` 当理由）；其它非零 = 出错，按 `on_error` 处理
- `stdout` 不是 JSON 也没关系：当作一句说明（不改变决定）
- 参数里超过 4000 字符的字段会被截断，**文件内容不会被塞给钩子**（要读自己读）

### 配置

```json
"hooks": {
  "pre_tool": ["python .ace/hooks/no_migrations.py"],
  "post_tool": [{"command": "python .ace/hooks/audit.py", "timeout": 5, "on_error": "warn"}],
  "user_prompt": ["python .ace/hooks/add_context.py"]
}
```

或项目内 `.ace/hooks.json`（**追加**在用户级之后，不是覆盖 —— "我的习惯"和"这个仓库的
规矩"本来就该一起生效）。命令的 `cwd` 是项目根，所以 `.ace/hooks/x.py` 这种相对路径直接可用。

### 失败语义（默认值是有意的）

**`on_error` 默认 `block`（fail-close）**：钩子崩了、超时了、输出大到离谱，都**不算**
"检查通过"。那正好是"我加了检查、检查其实没跑"的最坏情形。要宽松就显式写 `"on_error": "warn"`。

被 `pre_tool` 拦下的调用返回状态 `HOOK_BLOCKED`：**不计入安全违规计数**（那是团队规矩，
不是有人在试探边界），但会作为一次失败回喂模型，并附上"别重复同一个调用"的指令。

---

## 2. 自定义斜杠命令（`.ace/commands/*.md`）

```markdown
---
description: 跑全量测试并逐条列失败项
argument-hint: [段号]
---
请运行 python test_all.py $ARGUMENTS，失败项逐条列出；不要改动测试文件。
```

- 放 `.ace/commands/` 下即可，文件名就是命令名（`/review`）
- frontmatter 只认 `description` / `argument-hint`（**不引入 YAML 依赖**）
- 正文里 `$ARGUMENTS` 是整串参数，`$1`/`$2` 是按空白切开的第 n 个
- 没写 frontmatter 也认：描述取正文第一行
- **内置命令优先**：`/help` 这类永远不会被自定义命令顶掉
- 自定义命令展开成一段**提示词**，走正常对话流程（不是内部命令）—— 所以模型的
  权限/审批/审计照旧

---

## 3. 插件目录（`.ace/plugins/<名字>/`）

```
.ace/plugins/myplugin/
├── plugin.json          # 可选：{"name": "...", "description": "..."}
├── commands/*.md        # 贡献斜杠命令（名字自动加前缀：/myplugin:review）
└── hooks.json           # 贡献钩子（与用户配置同格式，追加生效）
```

- 命令带**插件名前缀**，不会和内置命令或其它插件撞名
- 坏插件的错误记在它自己的条目里（`/plugins` 会显示原因），**不影响其它插件**
- **这一版插件不能带工具**：tools 需要 Python 模块，那等于让插件在进程内跑代码，
  是远大于"命令 + 钩子"的信任面。要做工具扩展，用 MCP（下面）。

`/plugins` 看加载结果，`/hooks` 看钩子与上次执行结果。

---

## 4. MCP server（外部进程工具）

见 [CONFIGURATION.md](CONFIGURATION.md#mcp-servermcp_servers) 与
[SECURITY-MODEL.md](SECURITY-MODEL.md) 的「MCP 边界说清楚」：stdio JSON-RPC 2.0，
工具注册成 `mcp__<server>__<工具名>`，`/mcp` 看状态。**MCP server 同样不在沙箱里。**

---

## 5. 边界与不做的部分（写在明面上）

| 项 | 现状 |
|---|---|
| 钩子 / MCP 的执行环境 | 用户配置的本地命令，**不在 ACE 沙箱内**；只有你信得过的才该装 |
| `post_tool` 能否改结果 | 不能。它只能补充上下文（`data.hook_note`）与记审计 |
| 插件能否带工具 | 不能（见上）；工具扩展走 MCP |
| MCP 传输 | 只支持 stdio；HTTP/SSE 未实现 |
| 钩子超时上限 | 单条钩子默认 10s（可配），超时按 `on_error` 处理 |
