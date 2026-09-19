# 命令参考（Command Reference）

> 本文档由 README「命令参考」一节拆分而来（docs/design/README-RESTRUCTURE.md，v3.7），内容与当时 README 保持一致。
> README 入口见「常用命令」（只列最常用的）；完整清单在这里。

**首页**：↑/↓ 选择 · 数字直选 · Enter 确认 · Esc/q 退出。聊天内 `exit` 回首页，首页 `7`/`Esc`/`q` 才真正退出。

首页由三块构成：**「当前会话」面板**（模型 / 边界四轴 / 目录 / 历史 —— 包括"恢复了哪一次会话"）、**「最近会话」面板**（最近 3 次，时间 / 轮数 / 首句；没有历史时整块不画）、**分组菜单**（会话 / 模型 / 其他）。面板宽度跟着终端列数走（48–96 列之间），中文按两列算，所以换终端不会错位。

**斜杠命令**（聊天里输入 `/` 实时弹菜单，需 `prompt_toolkit`，未装自动降级）：

| 分类 | 命令 |
|---|---|
| 会话 | `/help` `/clear` `/status` `/stats` `/audit` `/history` `/expand` `/mcp` `/exit` |
| 扩展 | `/hooks`（事件钩子与上次结果） `/plugins`（插件与它们贡献的命令/钩子） |
| 安全 | `/permission [level]` `/snapshots` `/undo` `/rollback <id>` `/sandbox [档]` `/net [on\|off]` |
| 模型 | `/provider [名称\|编号] [key]` `/model <名称>` `/config` `/mock` `/thinking [on\|off]` |
| 工具 | `/open <路径>` `/edit <路径>` `/search <关键词>` `/memory` `/report` `/goal [动作]` |

```bash
/provider                   # 列出 9 家厂商 · 10 入口（当前标 ✓）
/provider zhipu             # 一键切智谱（自动换到 glm-4.7-flash）
/provider 3 sk-你的key      # 编号 + 密钥一把梭
```

工具输出超过 8 行时卡片折叠，末行写着「已折叠 N 行 (用 /expand 看完整)」——`/expand` 重印上一次被折叠的完整输出（单次最多保留 4000 字符，被截断时会在标题里说明；没有折叠过就如实回答没有）。

**卡片上看什么**：标题是 `符号 工具名 状态 [状态码] · 耗时 · exit 退出码 · +N -M`。

- **`· exit N`**：命令类工具的退出码。**"跑完了"和"成功"是两件事**，非 0 时标题不再用绿色 —— 由你自己判断这次算不算成功
- **`· +N -M`**：写入类工具改了几行；正文逐行 `+`（绿，新增）/ `-`（红，删除）/ `@@`（青，区块位置），文件头按暗色（它不是增删行）
- 一轮里调用 ≥2 次工具时，收尾会有一行 `N 次工具调用 · 耗时 · 工具名 状态…` 汇总；只调一次不打这行
- 新文件不显示 diff（全是 `+` 行没有信息量）；`.env` / `*.pem` / `id_rsa` 这类凭据文件**不读旧内容**，所以也不显示 diff

**底栏**（常驻，直接显示状态而不是等出事才说）：`模型 | 权限 | 沙箱 | 联网 | 目标 | 轮数/工具数 | 上下文占比`。
- 上下文占比是**估算**（口径见 `cli/ace_context.py`：中文按字计，宁可高估），颜色即语义：灰=有余量 · 黄=用掉压缩触发点的 80% · 红=已达触发点（下一轮会把中段折成摘要）
- 窗口未知时不显示这一项——不拿 0 当分母造一个假百分比
- 逼近阈值时会在请求发出前提醒一次（按触发点的 10% 一档节流，不会每轮刷屏）；`/status` 里有 tokens/窗口/触发点的明细
- 用 `--no-compact` 关掉压缩后，`/status` 会额外说明"超出窗口直接硬截断"，免得以为还有压缩兜底

**输入行**：

- **多行输入**：`Alt+Enter` 或 `Ctrl+J` 在光标处换行，`Enter` 发送。`Shift+Enter` 也接，但它要终端支持扩展键协议（Windows Terminal / Kitty 支持；旧 conhost 会把 `Shift+Enter` 当成 `Enter` 送上来）——所以主推前两个键。续行用 `… ` 对齐。
- **历史**：`↑`/`↓` 翻当前会话输入；`Ctrl+R` 反向逐条搜索（跨会话，历史写在 `~/.ace_history`）；`/history 关键词` 按**子序列**模糊检索（`dsk` 能命中 `deepseek` 那条），命中字符高亮，交互终端里选中后会填进下一次输入行——**不自动发送**。
- **`/` 菜单**：命令按「会话 / 安全 / 模型 / 工具」分组排序，说明前标组名；`/help` 按同一分组分节。

**@ 快捷方式**（输入 `@` 弹菜单）：

| 命令 | 作用 | 示例 |
|---|---|---|
| `@lang` | 切换回复语言 + 界面语言（zh/en/ja） | `@lang en` |
| `@skill` | 切换技能，描述与推荐工具注入提示词 | `@skill coding` |
| `@file` | 把文件内容加入上下文（≤4000 字符自动截断） | `@file README.md` |
| `@folder` | 把文件夹列表加入上下文（≤30 项） | `@folder tools` |
| `@refs` / `@clear` | 查看 / 清空当前引用（最多保留 3 项） | `@refs` |

可选技能：`coding`（默认推荐 `code_execute` `file_write` `terminal_exec`）· `writing` · `analysis` · `fiction` · `general`。

**扩展**：钩子、自定义命令、插件与 MCP 都写在 [`docs/EXTENDING.md`](EXTENDING.md)。
- `.ace/commands/*.md` → 斜杠命令（`$ARGUMENTS` / `$1` 代入参数；内置命令优先，不会被顶掉）
- `.ace/plugins/<名>/` → 插件：`commands/*.md` + `hooks.json`（命令带插件名前缀 `/名:cmd`）
- `hooks`（`~/.ai_code.json` 或 `.ace/hooks.json`）→ 四个事件的用户检查；**默认出错即拦截**（fail-close），要宽松显式写 `on_error: warn`
- `/hooks` 看装了哪些钩子与上次结果，`/plugins` 看插件加载情况

**MCP（外部进程工具）**：在 `~/.ai_code.json` 写 `mcp_servers`（或项目内 `.ace/mcp.json`），启动时按 stdio JSON-RPC 2.0 握手并把对面的工具注册成 `mcp__<server>__<工具名>`——模型可以直接调用它们，权限/审批/审计照旧。`/mcp` 看 server 状态与工具清单（`/mcp notools` 只看状态）。**MCP server 不在 ACE 的沙箱里**：它是你配置的子进程，只写你信得过的。

**在对话里打开文件**——默认只给可点击链接，不抢焦点、不弹窗：

```
（自己动手）  ❯ /open 报告.docx        # 系统默认程序打开
              ❯ /edit main.py          # 优先 VS Code
（叫 Agent）  ❯ 帮我打开桌面的报告.docx
              🔗 点击打开文件: C:\Users\...\报告.docx   ← 点一下才展开
```

## 启动参数（CLI flags，非聊天斜杠命令）

完整清单以 `python ai_code.py --help` 为准；常用：

- `--preview [--preview-width N]` — 只画一遍首屏（面板 + 分组菜单 + 状态栏示例）然后退出。不开交互终端也能看界面长什么样，`demo/record_demo.py --session landing` 就是用它出的图
- `--json` — **机器可读事件流**：stdout 一行一个 JSON 对象（`session_start` / `user_message` / `model_request` / `tool_call` / `tool_result` / `permission_request` / `notice` / `final` / `session_end`），无 ANSI、无进度条；人看的输出会变成 `notice` 事件。契约见 [INTERFACES.md](INTERFACES.md#91-headless-事件流契约ace---json)。例：`ace --json --input "现在几点" | jq -c 'select(.type=="final")'`

- `--tools` — 原生工具调用（OpenAI 兼容 function calling，不支持时自动降级到文本协议）
- `--max-history N` — 只保留最近 N 轮，防本地小模型上下文溢出
- `--context-window N` — 告诉 ACE 模型窗口有多大（默认 32768），压缩阈值按它算
- `--no-compact` — 关掉上下文压缩，退回纯硬截断（会丢早期对话）
- `--install-ui` — 装 / 补全 prompt_toolkit（多镜像自动回退）
- `--install-executor` — 下载官方预编译执行器（无需本机 Go；`--sandbox job` 前置）
- `--sandbox job` — Windows Job Object：进程树/内存上限 + 受限令牌（拿不到边界一律 503，不静默回退）
- `--sandbox docker` — 一次性容器：--network none + --read-only + cap-drop ALL + --init + 只挂工作目录。镜像需先构建一次（`docker build -t ace-sandbox:latest -f docker/Dockerfile.sandbox .`）；镜像放在 registry 里的话 `ACE_SANDBOX_PULL=1` 可自动拉（先 `docker login`），`--sandbox-image <ref>@sha256:<digest>` 可固定摘要
- `--approval-policy <档>` — 审批策略（与沙箱正交）：`on_request`（默认，需审批时问人）/ `on_failure`（有 job/docker 边界时先试后问；无边界时退回 on_request）/ `never`（从不问人，需审批的一律拒绝）/ `untrusted`（除白名单外都问）。**无人值守请组合 `--sandbox job|docker` + `on_failure`**
- `--kb <目录>` — 外挂知识库（不指定则用项目 `.ace_kb/`）
- `--input "<话>"` — 单次对话，跑完即退

本地 Ollama（Qwen 支持原生工具调用）：

```bash
python agent_runner.py --base-url http://localhost:11434/v1 --api-key ollama \
       --model qwen2.5-coder:7b --tools
```

容器编排：根目录 `docker compose up`（ACE + Ollama）；`docker/` 下另有 lite / standard / full 三档镜像与模型下载脚本，见 [../docker/README-Docker.md](../docker/README-Docker.md)。

