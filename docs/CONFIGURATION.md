# 配置（Configuration）

> 本文档由 README「配置」一节拆分而来（docs/design/README-RESTRUCTURE.md，v3.7），内容与当时 README 保持一致。
> 配置优先级见 [SECURITY-MODEL.md](SECURITY-MODEL.md) 顶部（命令行参数 > `~/.ai_code.json` > `~/.claude/settings.json` > 环境变量）。
> **下面的键写进 `~/.ai_code.json` 即生效**（CLI 会原样透传给执行层）；`python ai_code.py --save-config` 可把当前命令行参数落盘。
> v3.8 修正：`signing_key` / `max_snapshots` / `confine_files` / `email_smtp` / `egress_allowlist` / `session_id` 此前**只在程序化构造 `ExecutionLayer` 时生效**，写进配置文件会被静静忽略——配置写了不生效比没这个键更坏（用户以为闸门开着），现已修复并有 test_all 断言盯着。

```python
config = {
    "flywheel_path": ".../violations.jsonl",   # L5 飞轮落盘路径
    "sandbox_base": "...",                     # code_execute 沙箱临时目录（默认系统临时区）
    "confine_files": True,                     # 文件工具限制在项目目录内（含跨盘符检查）
    "signing_key": "你的签名密钥",              # Guardian 快照 HMAC 签名（生产建议）
    "max_snapshots": 20,                       # 快照硬上限，自动清理最旧
    "session_id": "会话标识",                   # archive 记忆按会话隔离
    "bait": {"enabled": True, "frequency": 0}, # 诱饵验证（0 = 每任务一次）
    "guard": {"rules": {"no_hardcoded_secrets": False}},  # 关闭某条守门规则
    "email_smtp": {"host": "smtp.qq.com", "port": 587,
                   "user": "you@qq.com", "password": "授权码",
                   "use_tls": True},           # notify_send email 渠道（缺省时返回 501）
    "egress_allowlist": ["api.github.com", ".openai.com"],  # 出站目的地白名单（缺省 = 闸门关闭）
    "approval_policy": "on_request",       # 审批策略：on_request（默认）/ on_failure / never / untrusted
    "sandbox_policy": "workspace_write",   # 判定用沙箱策略：read_only / workspace_write / danger_full_access
    "mcp_servers": {                        # MCP server（外部进程工具，v3.17.0 起）
        "fs": {"command": "npx",
               "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
               "enabled": True,             # 可选：false = 只登记不启动
               "timeout": 20,               # 可选：握手/列工具超时（秒）
               "call_timeout": 120},        # 可选：单次工具调用超时（秒）
    },
}
```

### MCP server（`mcp_servers`）

- **协议**：stdio 上的 JSON-RPC 2.0（一行一个消息），实现 `initialize` 握手、`tools/list`、`tools/call`。HTTP/SSE 传输**没有实现**。
- **工具怎么进来**：每个外部工具注册成 `mcp__<server>__<工具名>`，schema 原样透传；模型看到的工具列表里就能直接调用它们。
- **权限怎么算**：对面声明 `annotations.readOnlyHint: true` 才算只读，**其余一律按写**（readonly 会话下需要授权）。默认从严：对面说只读是它自己声明的，说错话的代价不该由用户承担。
- **项目级配置**：项目根下 `.ace/mcp.json`（`{"mcpServers": {...}}` 或直接 `{名字: {...}}`），同名时**项目级覆盖用户级**。
- **起不来怎么办**：单个 server 启动失败不影响会话，状态与失败原因在 `/mcp` 里如实展示；调用它的工具会得到 `503` + "未注册" 说明（**不会**变成"要不要临时授权"——那会让人以为点一下就能用）。

### 审批策略与沙箱策略（两个正交维度）

`approval_policy` 回答"要不要问人"，`sandbox_policy` 回答"允许它碰什么"；两者与权限档（`permission`）正交，共三个维度。CLI 入口是 `--approval-policy`（`ai_code.py` 与 `agent_runner.py` 都有），写进 `~/.ai_code.json` 同样生效（v3.8.1 起透传，此前只在程序化构造 `ExecutionLayer` 时被读取）。

| 档位 | 语义 |
|---|---|
| `on_request`（默认） | 判定为"需审批"时问人 |
| `on_failure` | **有真实边界**（`--sandbox job/docker`）时"先试后问"：交给边界执行，沙箱拦下才升级给人；**没有边界时退回 `on_request`**（仍要人点头，不会因为写了 on_failure 就免问） |
| `never` | 从不问人：判定为需审批的一律**拒绝**（不是放行）。**必须配真边界**：`never` + `sandbox=off`（或 `sandbox_policy=danger_full_access`）会**拒绝启动**（退出码 2 / 库调用方抛 `PolicyRefused`）——它挡不住不需要审批的工具，所以"没人 + 没边界"没有可辩护的用途 |
| `untrusted` | 除白名单外一律问 |

无人值守（CI / 管道 / 无 tty）请**显式**组合 `--sandbox job|docker` + `approval_policy: on_failure`。默认档下需要审批的动作在非交互里会被直接拒绝（`terminal_exec` 在 CI 里不可用），而无需审批的写/执行工具照跑——见 [`SECURITY-MODEL.md`](SECURITY-MODEL.md) 的「无人值守 / 自动化部署」；启动时也会对"非交互 + `off` 档 + 非只读"这个组合主动打提示。

### 出站白名单（`egress_allowlist`）

内网判定（`ace_net`）管的是"别打到内网去"，白名单管的是"能把数据带到哪个公网站点去"。后者只有宿主知道哪些站点算正当，所以**默认关闭**：不配这个键，`api_get` / `api_post` / `browser_open` / `web_search` 的行为和以前完全一样。

但"默认关闭"不等于"默认没人管"：**没配清单时，外发工具只要目的地不在内置端点里，就会逐次弹确认**（v3.8 起，见 [SECURITY-MODEL.md](SECURITY-MODEL.md) 的「外发闸门」）。清单是给"别再问我了"用的——写好之后清单内直接放行，清单外一律 403。

配上之后：

- **是并集，不是覆盖**：配置的条目会自动并上内置端点（搜索引擎等）。否则配置白名单的第一个可见后果就是搜索坏掉，而用户会把这读成"功能有 bug"，删掉清单——闸门也就没了。
- **逐跳复检**：清单内主机完全可以 `302` 到 `evil.tld`，而第一跳的判定是对的。所以每一跳都重新过清单，中途跳出清单直接掐断连接。
- **403 而不是 400/500**：这是授权问题。同一个地址重试不会变，只有人能把域名加进清单。返回消息里就这么写给模型看，免得它反复重试或改写 URL 试探。
- `browser_open` 也过清单。连接交给系统浏览器之后就不经过本进程（拦不住浏览器自己跟的重定向），但"要不要把这个域名交出去"这个决定本进程还能做。
- 条目写法宽松：`api.github.com`、`.github.com`（含子域）、`https://api.github.com/x`（只取主机）都认。匹配按标签边界，`evil-github.com` 不会命中 `github.com`。
- **`notify_send` 的 SMTP 也归它管**：那条路直连 `smtplib`，主机来自宿主配置而非模型参数（所以不是 SSRF 面），但正文和收件人是模型给的 —— 是实打实的外发通道，所以走同一份清单。

### 检索工具的边界（`grep` / `glob`）

两者属于 `READ_TOOLS`，`readonly` 会话就能调，所以约束不能只管起点：

- `glob` 的 `pattern` 里出现 `..` 直接 **403**，不是"复检后静静丢掉"。丢掉的话模型看到的是"没匹配"，它会换个写法再试。
- 每条命中都在**解析软链接之后**重新确认落点。项目里一个指向 `~/.ssh/id_rsa` 的软链接，`os.walk` 会当普通文件产出。
- 命中还要过 `sensitive_target`：项目内也可能躺着误提交的 `.pem`。
- 遍历文件数撞上限（5000）时回报 `scan_incomplete: true`，与"结果太多"分开报。否则模型会把"没扫完"读成"这个符号不存在"。
- 模型给的正则只在行首 4000 字符上跑。Python 的 `re` 没有超时，灾难性回溯会挂死整个工具调用；限住输入长度不能消除回溯，但能把上界从"行有多长"压到常数。

### `str_replace` 不做有损重编码

读-改-写路径用严格解码（UTF-8 → 系统编码，都失败就 **400 拒绝改写**），并按读进来的那个编码写回。此前是 `errors="ignore"` 解码 + 硬写 UTF-8：一个 GBK 源文件会被静默转码，解码时丢掉的字节永久消失，而模型只看到"替换成功"。

### `db_query` 的只读靠连接，不靠正则

`db_query` 用 `?mode=ro` 的 URI 连接，写入由 SQLite 自己拒绝。SQL 是完整语言，`CREATE TRIGGER`、`INSERT ... SELECT`、CTE 包一层写入、`pragma_table_list` 这类表值函数（`\bpragma\b` 对 `pragma_` 不成立）—— 前缀匹配挡不住的写法列不完。

`db_write` 天生要写，拿不到连接级保护，所以那边仍是黑名单，并且**不闭合**：`DELETE FROM t`（无 WHERE）、`REPLACE INTO`、`CREATE TABLE x AS SELECT` 都在放行范围内。真正的边界是权限档位与 Guardian 快照。两条路都拒绝多语句（分号），因为驱动拒绝多语句时抛的是 `sqlite3.Warning`，它**不是** `sqlite3.Error` 的子类，会一路冒成 500。
