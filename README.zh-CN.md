<p align="center">
  <a href="https://github.com/ace-code-engine/ace-agent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ace-code-engine/ace-agent/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="安全核心依赖" src="https://img.shields.io/badge/safety%20core-zero--dep-orange">
  <img alt="模型调用" src="https://img.shields.io/badge/model%20API-requires%20requests-blue">
  <a href="CHANGELOG.md"><img alt="Latest" src="https://img.shields.io/badge/latest-v3.42.0%20(2026--09--26)-brightgreen"></a>
  <a href="CHANGELOG.md"><img alt="Changelog" src="https://img.shields.io/badge/%E6%9B%B4%E6%96%B0%E6%97%A5%E5%BF%97-CHANGELOG-blue"></a>
</p>

<h1 align="center">ACE · AI Code Engine</h1>

<p align="center"><strong>中文</strong> · <a href="README.md">English</a> · <a href="CHANGELOG.md">更新日志 · Changelog</a></p>

<p align="center">
  <strong>一个把安全下沉到执行层的 AI 编码 Agent —— 模型只负责理解和输出，<br>
  权限、沙箱、快照回滚全部由执行层裁决。</strong>
</p>

### 一览

| 关键属性 | 说明 |
|---|---|
| **本地跑** | **安全核心**纯 stdlib（执行层 · 网关 · 记忆 · CLI）。跑在你自己的机器上，链路里没有云，离线演示不需要任何 API Key。 |
| **模型无关** | **9 家厂商 · 10 个入口**，一个 `/provider` 切换 —— 智谱、DeepSeek、Moonshot、OpenAI、Anthropic、通义千问、SiliconFlow、OpenRouter、Ollama —— 同时支持 OpenAI 与 Anthropic 两种报文格式。 |
| **可插拔** | 每个工具只在 `tools/registry.py` 声明一次；**MCP server** 走 stdio，它的工具以 `mcp__<server>__<工具名>` 出现，权限/审批/审计照旧；技能就是普通 `SKILL.md` 文件。 |

> 模型调用需要 `requests`，安全核心不需要。MCP server 跑在 ACE 沙箱之外。

---

## Why ACE?

### 安全不该住在提示词里

大多数 Agent 把安全交给提示词："请不要删除文件"。ACE 不这么做。

模型的**每一次工具调用**都要穿过一个独立的执行层，由它做权限裁决、危险行为检测、写入前物理快照。提示词失效时 —— 被越狱、被注入的网页、被篡改的工具输出 —— 那一层仍然在。

> 如果你的需求只是**聊天式 AI 编程**（对话里生成代码、不改文件、不执行命令），ACE 未必必要。如果你的 Agent 要**真实地改文件、执行代码、访问网络**，并且你不希望这件事依赖模型的自觉 —— 那 ACE 才是目标场景。

### ACE 与「提示词护栏」型 Agent 的差别

| | 典型的提示词护栏 Agent | ACE |
|---|---|---|
| 「我有没有权限」在哪裁决 | 提示词里 | 执行层里，**每次调用**都过（`execution_layer.py`） |
| 提示词被注入 / 被越狱之后 | 看模型怎么决定 | 权限闸门、路径边界、敏感目标拦截照样生效 |
| 执行一条 shell 命令 | 模型直接跑 | `terminal_exec` **每次都问人** —— 它的黑名单可被绕过，所以「人」才是那道边界 |
| 撤销一次坏改动 | 指望 git | 每次写入前都有物理快照，`/undo` 一键回滚 |
| 数据离开这台机器 | 模型调 API 就走 | 外发闸门：目的地未知 ⇒ 确认；`egress_allowlist` ⇒ 一次性授权 |
| 离线、没有 API Key | 通常需要密钥 | `python ai_code.py --mock` 离线跑完整闭环 |
| 隔离 | 提示词级 | 三档：`off`（进程内策略）/ `job`（Windows Job Object）/ `docker`（一次性容器）—— 拿不到边界就返回 **503，绝不静默回退** |

### 设计取向

- **安全属于执行层，不属于提示词。** 权限裁决、危险命令拦截、写入前快照都在 `execution_layer.py` 里，与模型无关。换模型、模型被越狱、提示词被覆盖，这层都还在。
- **默认只读。** 起步权限是 `readonly`，写工具会被 403 拦下。提权是**人的动作**（`/permission write`），不是模型能自己发的。
- **边界要说清能挡什么、挡不住什么。** 全仓没有一句"完全安全"的宣称 —— 见 [安全边界](#安全边界)。

---

## 30 秒跑起来

### 从源码跑，不需要 API Key

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python test_all.py          # 端到端测试，纯 stdlib，应当全绿
python ai_code.py --mock    # 离线演示：完整跑一遍 模型↔执行层 闭环
```

**前置**：Python ≥ 3.10（用到 `int.bit_count`，建议 3.11/3.12）。核心不需要装任何第三方包。

### 接真实模型

```bash
python ai_code.py           # 进首页 → 选 2 走配置向导 → 选 1 进聊天
python ai_code.py --input "现在几点"   # 单次对话
```

- 聊天里也可以一行切换：`/provider deepseek <key>`。
- Windows 上项目目录已带 `ace.cmd`，加入 `PATH` 后可直接敲 `ace`。

<details>
<summary>其他启动方式（工具调用 / 沙箱 / 知识库；完整参数见 docs/COMMANDS.md）</summary>

```bash
ace --tools                    # 原生工具调用（function calling，不支持时自动降级）
ace --install-executor         # 官方预编译执行器（--sandbox job 前置，无需本机 Go）
ace --sandbox job              # Windows Job Object：进程树/内存上限
ace --sandbox docker           # 容器隔离：真实内核边界（需 Docker）
ace --kb D:\我的资料库         # 外挂知识库（kb_search/kb_add 跨会话持久）
```

</details>

### 预编译 Windows 发行包，不用装 Python

到 [Releases 页面](https://github.com/ace-code-engine/ace-agent/releases) 下载 `ace-<版本>-windows-amd64.zip`，解压到任意目录，运行 `ace\ace.exe` 即可。**没有安装程序，也不会往你选的目录之外写东西** —— 它是自带解释器的完整包，那台机器上**不需要装 Python**。

```powershell
# 离线：不需要账号也不需要密钥，先确认这个包是完整的
.\ace\ace.exe --mock

# 接真实模型：进首页选 2 走配置向导
.\ace\ace.exe
```

跑之前有两件事值得先知道：

- **Windows SmartScreen 会拦一下。** 这个构建没有代码签名，新下载的 exe 会弹"Windows 已保护你的电脑"——点 *更多信息* → *仍要运行*，或者先自己核对 zip。这是**未签名二进制**的正常样子，不代表这个包有问题。
- **它是一整个目录，不是单个文件。** `ace.exe` 必须和旁边的 `_internal\` 待在一起；只把 exe 拷出去用不了。

**冻结发行里有几项能力不成立**，而 exe 会**明说**，不会悄悄失败：

| 能力 | 预编译 exe | 原因 |
|---|---|---|
| 对话、工具、文件、终端、权限裁决、快照回滚 | ✅ | 纯 stdlib 安全核心，资源已随包带上 |
| `code_execute` | ❌ 如实返回 **501** | 它靠 `sys.executable` 去跑 Python，而冻结后那就是 `ace.exe` 自己；需要它请用源码运行 |
| `--install-ui` / `--setup` | ❌ 无意义 | 包里已经自带解释器与界面依赖 |
| `--install-executor` | ⚠️ 取决于包里带没带 Go 二进制 | 没带就去下载，这一步需要联网 |

构建脚本是 `packaging/build_exe.ps1`，**它不在打包产物上跑过就不算成功** —— 发布前会把 exe 真的跑一遍 `--version`、`--preview`、mock 工具往返、以及 `code_execute` 的 501 路径。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_exe.ps1
```

### 看它跑起来

[演示与截图](docs/SHOWCASE.md) —— 首屏、一段真实录制、diff 卡片、以及执行层拒绝 SSH 私钥那一刻。

**延伸阅读** —— 上手路径（5 分钟跑起来 · 三维度矩阵 `permission` / `sandbox` / `approval_policy` · 十个坑）：`docs/GETTING-STARTED.md`。可以直接照做的剧本：`examples/`。

---

## 核心能力

### 执行安全

| 能力 | 一句话钩子 |
|---|---|
| 三级权限 + 按权限裁剪工具表 | `readonly` / `write` / `full`。工具清单随档位裁剪，单点声明在 `tools/registry.py`，模型只在"看得见用得了"的工具里决策。 |
| 三层沙箱 | `off`（策略层）/ `job`（Windows Job Object：进程树、内存上限、受限令牌）/ `docker`（一次性容器：`network none` + `cap-drop ALL`）。拿不到边界就 503，绝不静默回退。 |
| 写入前快照 | 每次写操作自动物理快照，`/undo` 一键回滚。HMAC 签名防伪造，快照目录 Agent 自身不可写。 |
| 外发闸门 | 数据去往**模型指定的目的地**时，目的地不在白名单内就逐次问人；配置 `egress_allowlist` 即一次性授权。 |
| 安全事件分级 | 403 里"执行层主动防御"与"模型参数写错"分开计数：前者本会话累计到阈值就明确告警 —— 那通常意味着有东西在借被读取的文件或网页注入指令。 |
| 行为检测闸门 | 首次 `code_execute` 注入语义诱饵验证模型清醒 + AST 6 规则（无限递归 / 硬编码密钥 / SQL 注入等）。 |
| Go 执行器 | 危险工具委派独立 Go 进程（NDJSON），Job Object 整树回收 + 第二道策略复检；官方产物 `ace --install-executor`。 |

### Agent 能力

| 能力 | 一句话钩子 |
|---|---|
| 持久目标（goal） | `goal_create` 后**自动逐轮续跑**直到完成 / 暂停 / 阻塞 / 预算耗尽。blocked 须给机器 code，重启后 `/goal resume` 才续。 |
| 子代理 | `subagent` spawn（全新上下文）/ fork（继承父会话），各自带工具循环，结果回传父代理整合。 |
| 免 key 联网搜索 | `search` 双引擎兜底（Bing RSS → DuckDuckGo）+ `search_read` 一步抓 top 正文。出站全走 SSRF 校验 + 白名单。 |

### 可选与实验性

- **可选** —— 自定义知识库（`kb_search` / `kb_add` / `kb_list`）、会话事件日志与重启恢复（`/audit`）、Plan Mode、审批疲劳缓解、浏览器自动化、文档解析全家桶（Word / Excel / PPT / PDF / OCR）、SimHash 记忆、`AGENTS.md` 项目指令、上下文压缩、网络退避、i18n（zh / en / ja）。
- **实验性** —— 聊天内置滚动引擎。引擎已实现，真机接线待做，见 `docs/history/UI-CHAT-SCROLL.md`。

---

## 架构概览

每层一句话：`ai_code.py`（终端：登录页 / REPL / 斜杠命令）→ `agent_runner.py`（模型 ↔ 执行层闭环，最多 20 轮）→ **`execution_layer.py`**（解析 → 权限裁决 → 安全闸门 → 写前快照 → 执行；14 阶段状态机，**安全裁决的强制边界所在**）→ `tools/registry.py`（工具单点声明）→ `core/`（快照、记忆、元处理）。

Gateway（L1 / L2 / L4 / L5）是执行层**每轮内调用**的策略辅助层 —— 不是独立的第二道安全流水线。

**架构图（Mermaid，GitHub 自动渲染）、分层职责表与权威目录树** → **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**。

---

## 常用命令

### 首页与聊天

**首页**：↑/↓ 选择 · 数字直选 · Enter 确认 · Esc/q 退出。聊天内 `exit` 回首页，首页 `7` / `Esc` / `q` 才真正退出。

### 日常斜杠命令

```bash
/provider                    # 列出 9 家厂商 · 10 入口（当前标 ✓）
/provider zhipu              # 一键切智谱（自动换到 glm-4.7-flash）
/permission write            # 提权（默认 readonly）
/undo                        # 写入前快照 → 一键回滚
```

- **斜杠命令** —— `/help` `/clear` `/status` `/snapshots` `/rollback <id>` `/model <名称>` `/mock` `/open <路径>` `/edit <路径>` `/search <词>` `/memory` `/report` `/expand` `/history [关键词]`
- **`@` 快捷** —— `@lang`（zh/en/ja）· `@skill` · `@file` · `@folder` · `@refs`
- `/` 菜单与 `/help` 把命令分成「会话 / 安全 / 模型 / 工具」四组。

### 输入与输出

- **输入** —— `Enter` 发送，`Alt+Enter` / `Ctrl+J` 换行，`Ctrl+R` 逐条往回翻历史，`/history dsk` 按关键词模糊找。
- **长输出** 会被卡片折叠，`/expand` 重印完整输出（单次最多 4000 字符，被截断时如实标注）。
- **写入类卡片** 给上色 diff 与 `exit N` 退出码；↑/↓ 与 `Ctrl+R` 翻的是跨会话的 `~/.ace_history`，`ACE_NO_HISTORY=1` 可让它只留在进程内。

**延伸阅读** —— 完整命令表、`/provider` 全示例、启动参数：`docs/COMMANDS.md`。

---

## 安全边界

### 四层，默认启用程度不同

| 层 | ACE 的做法 |
|---|---|
| Prompt 层 | 提示词只做引导，**不承诺安全** |
| Application 层（默认） | 执行层策略：三级权限 + AST 行为检测 + 写前快照/回滚 + 路径边界 + 网络 SSRF/白名单闸门 + 外发目的地确认（含项目外覆盖/删除要人点头） |
| OS 层（可选，Windows） | `--sandbox job`：Job Object 进程树/内存上限 + 受限令牌 |
| Container 层（可选） | `--sandbox docker`：一次性容器，`network none` + `cap-drop ALL` + `read-only` 根 + `--init` + 只挂工作目录 |

沙箱镜像本地构建一次（`docker/Dockerfile.sandbox`）；放在 registry 里的可用 `ACE_SANDBOX_PULL=1` 自动拉。

### 诚实边界

**不开 OS / Container 档时**，上述只是进程内策略 —— AST 黑名单与 AST 求值无法闭合，`terminal_exec` 的判定只是止血层。**这不是 OS 级隔离。**

`job` 档是 Windows 专属原语；Docker 容器共享内核，逃逸仍是逃逸。job / docker 拿不到边界一律 503，**绝不静默回退宿主执行**。

### 外发闸门的范围

它管的是**模型挑的目的地**。内置端点（搜索引擎、图片服务）不逐次问，其中 `image_generate` 会把 prompt 明文交给第三方服务。

`terminal_exec` 仍能删项目内的审计日志，但那一步**每次都过人**。这两条都写进了文档，不是隐藏行为。

**延伸阅读** —— 完整安全模型与生产部署必读：`docs/SECURITY-MODEL.md`。漏洞报告：`SECURITY.md`。

---

## 配置入口

### 配置文件

```python
# ~/.ai_code.json（命令行参数 > 本文件 > ~/.claude/settings.json > 环境变量）
config = {
    "permission": "readonly",   # readonly / write / full
    "sandbox": "off",           # off / job / docker
    "max_snapshots": 20,        # 快照硬上限，自动清理最旧
}
```

**延伸阅读** —— 全部配置项，以及出站白名单 / 检索边界 / `str_replace` 编码 / `db_query` 只读等机制说明：`docs/CONFIGURATION.md`。

---

## 测试

### 跑测试

```bash
python test_all.py                      # 全量测试（纯 stdlib，退出码非 0 即失败）
python test_all.py --only 40            # 只跑一段（它会自动带上声明的前置段）
python test_all.py --list               # 列出各段及依赖
ruff check . --select E9,F63,F7,F82     # CI 硬错误子集
```

### 承诺守卫

其中三节是**给文档与安全承诺用的守卫**：`[38]` 权威目录树 ↔ 真实文件、`[39]` 文档口径数字 ↔ `PROVIDERS` / `TOOL_SPECS`、`[40]` 安全审计里那些原始 payload。

它们的作用是让"文档说要问人"这件事不会某天悄悄变成"代码里从来没问过"。

### 已完成与仍未验证

这一节两半都留着是有意的：README 曾经把**已经做完**的事写成"未完成"，而过期的坦白本身也是一种不实。**真正需要警惕的是后半段** —— 别把它当成"应该没问题"。

**最近收口**（写在这里，免得旧说法继续挂着）：

- **R-03 双前端引擎合并：已完成，两侧验收都有证据。** `core/ace_client.py` 就是唯一一份模型 HTTP 客户端（唯一出网点、唯一拼 `/chat/completions` 的地方；两个前端只保留各自的调用契约）。
    - **无凭证那一半**：`python e2e/r03_contract_smoke.py` 起真监听 socket、两种线格式都答、两个前端都真跑一遍。
    - **厂商那一半**：`python e2e/real_model_smoke.py` + `ACE_E2E_*`，在 DeepSeek 真实端点上跑通 —— exit 0、命中 `🤖 Agent:` 单行契约、模型先调 `datetime_now` 再依据真实结果作答。
- **REL-03 真机冒烟：已在 Windows 真机走通。** `ace.cmd` → 解释器自解析 → 真实控制台对话，离线 `--mock`，退出码 0，中文与 emoji 都正常。`e2e/rel03_native_smoke.ps1` 把它固化成三档。
- **这次冒烟抓出并修掉的缺陷。** `_generate_text`（不带 `--tools` 的文本协议回退）过去把模型的纯文本直接交给执行层，而执行层的契约是协议文本；于是 `agent_runner.py --base-url …` 永远走不到最终回复。mock 分支与 `--tools` 分支都会包装，所以此前没有任何测试覆盖到它。现已与 `_generate_tools` 同口径，并在 `[8]` 补了断言。

**仍未验证：**

- **真 TTY 下的 Textual 全屏界面**（没装 `textual` 时那几段会跳过）、以及任何**非 Windows 控制台**。
- **darwin/amd64 执行器产物没有原生冒烟** —— 交叉编译出来了，但没有 Intel Mac 实机跑过。

**延伸阅读** —— 测试框架说明、CI 矩阵、基准 / e2e / 冒烟细节：`docs/TESTING.md`。

---

## 文档

### 文档地图

| 想了解 | 去这里 |
|---|---|
| **第一次来先看这个** —— 5 分钟跑起来 · 三维度矩阵 · 十个坑 | `docs/GETTING-STARTED.md` |
| **演示与截图** | `docs/SHOWCASE.md` |
| **跑起来看场景** —— 安全实验室 / 文档解析 / 多轮任务 | `examples/` |
| 分层架构 · 完整目录树 · ADR 索引 | `docs/ARCHITECTURE.md` |
| 安全模型 / 审计 / 漏洞报告 | `docs/SECURITY-MODEL.md` · `docs/SECURITY-AUDIT.md` · `SECURITY.md` |
| 配置全项与机制 | `docs/CONFIGURATION.md` |
| 命令与启动参数 | `docs/COMMANDS.md` |
| 测试与 CI | `docs/TESTING.md` |
| 打包与 Windows 发行包 | `docs/PACKAGING-EXE.md` · `docs/PACKAGING.md` |
| 开发流程 / 契约 / 待办 | `docs/DEVELOPMENT.md` · `docs/INTERFACES.md` · `docs/BACKLOG.md` |
| 版本历史 | `CHANGELOG.md` |
| 历史立项卡 / 会话纪要 / 调研 | `docs/design/` · `docs/history/` |

### 开发与贡献

改动前请读 `CONTRIBUTING.md`；开发者标准化流程见 `docs/DEVELOPMENT.md`，接口与类型契约见 `docs/INTERFACES.md`，待办见 `docs/BACKLOG.md`。

### 许可

[MIT](LICENSE) © 2026 jincheng3870682453-hash

### 设计参考

架构决策与以下工作对齐 —— **让模型只负责"理解、选择、输出"，把权限、安全、回滚、记忆全部下沉到执行层**：

- [Agent Harness 工程最佳实践](https://github.com/Delphoa/study-awesome-harness-engineering) —— 工具 / 权限 / 记忆 / 沙箱 / 可观测性
- [DeepSeek Harness 设计解析](https://developer.aliyun.com/article/1756780) —— 对应内部调研 `docs/history/dsh_research.md`
- [20 章中文 AI Agent 架构实战](https://github.com/ryzqi/learn-agent)
