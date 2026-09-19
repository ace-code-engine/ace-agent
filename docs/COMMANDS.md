# 命令参考（Command Reference）

> 本文档由 README「命令参考」一节拆分而来（docs/design/README-RESTRUCTURE.md，v3.7），内容与当时 README 保持一致。
> README 入口见「常用命令」（只列最常用的）；完整清单在这里。

**首页**：↑/↓ 选择 · 数字直选 · Enter 确认 · Esc/q 退出。聊天内 `exit` 回首页，首页 `7`/`Esc`/`q` 才真正退出。

**斜杠命令**（聊天里输入 `/` 实时弹菜单，需 `prompt_toolkit`，未装自动降级）：

| 分类 | 命令 |
|---|---|
| 会话 | `/help` `/clear` `/status` `/stats` `/exit` |
| 安全 | `/permission [level]` `/snapshots` `/undo` `/rollback <id>` |
| 模型 | `/provider [名称\|编号] [key]` `/model <名称>` `/config` `/mock` |
| 工具 | `/open <路径>` `/edit <路径>` `/search <关键词>` `/memory` `/report` |

```bash
/provider                   # 列出 9 家厂商 · 10 入口（当前标 ✓）
/provider zhipu             # 一键切智谱（自动换到 glm-4.7-flash）
/provider 3 sk-你的key      # 编号 + 密钥一把梭
```

**@ 快捷方式**（输入 `@` 弹菜单）：

| 命令 | 作用 | 示例 |
|---|---|---|
| `@lang` | 切换回复语言 + 界面语言（zh/en/ja） | `@lang en` |
| `@skill` | 切换技能，描述与推荐工具注入提示词 | `@skill coding` |
| `@file` | 把文件内容加入上下文（≤4000 字符自动截断） | `@file README.md` |
| `@folder` | 把文件夹列表加入上下文（≤30 项） | `@folder tools` |
| `@refs` / `@clear` | 查看 / 清空当前引用（最多保留 3 项） | `@refs` |

可选技能：`coding`（默认推荐 `code_execute` `file_write` `terminal_exec`）· `writing` · `analysis` · `fiction` · `general`。

**在对话里打开文件**——默认只给可点击链接，不抢焦点、不弹窗：

```
（自己动手）  ❯ /open 报告.docx        # 系统默认程序打开
              ❯ /edit main.py          # 优先 VS Code
（叫 Agent）  ❯ 帮我打开桌面的报告.docx
              🔗 点击打开文件: C:\Users\...\报告.docx   ← 点一下才展开
```

## 启动参数（CLI flags，非聊天斜杠命令）

完整清单以 `python ai_code.py --help` 为准；常用：

- `--tools` — 原生工具调用（OpenAI 兼容 function calling，不支持时自动降级到文本协议）
- `--max-history N` — 只保留最近 N 轮，防本地小模型上下文溢出
- `--context-window N` — 告诉 ACE 模型窗口有多大（默认 32768），压缩阈值按它算
- `--no-compact` — 关掉上下文压缩，退回纯硬截断（会丢早期对话）
- `--install-ui` — 装 / 补全 prompt_toolkit（多镜像自动回退）
- `--install-executor` — 下载官方预编译执行器（无需本机 Go；`--sandbox job` 前置）
- `--sandbox job` — Windows Job Object：进程树/内存上限 + 受限令牌（拿不到边界一律 503，不静默回退）
- `--sandbox docker` — 一次性容器：--network none + --read-only + cap-drop ALL + 只挂工作目录。镜像本地缺失时**自动拉官方预编译镜像**（`ghcr.io/ace-code-engine/ace-sandbox`，多架构）；`--sandbox-image <ref>@sha256:<digest>` 可固定摘要，`ACE_SANDBOX_NO_PULL=1` 可关掉自动拉取（改用 `docker build -t ace-sandbox:latest -f docker/Dockerfile.sandbox .`）
- `--approval-policy <档>` — 审批策略（与沙箱正交）：`on_request`（默认，需审批时问人）/ `on_failure`（有 job/docker 边界时先试后问；无边界时退回 on_request）/ `never`（从不问人，需审批的一律拒绝）/ `untrusted`（除白名单外都问）。**无人值守请组合 `--sandbox job|docker` + `on_failure`**
- `--kb <目录>` — 外挂知识库（不指定则用项目 `.ace_kb/`）
- `--input "<话>"` — 单次对话，跑完即退

本地 Ollama（Qwen 支持原生工具调用）：

```bash
python agent_runner.py --base-url http://localhost:11434/v1 --api-key ollama \
       --model qwen2.5-coder:7b --tools
```

容器编排：根目录 `docker compose up`（ACE + Ollama）；`docker/` 下另有 lite / standard / full 三档镜像与模型下载脚本，见 [../docker/README-Docker.md](../docker/README-Docker.md)。

