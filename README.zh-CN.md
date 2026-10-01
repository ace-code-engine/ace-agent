<p align="center">
  <a href="https://github.com/ace-code-engine/ace-agent/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ace-code-engine/ace-agent/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="发布状态" src="https://img.shields.io/badge/release-v1.0.0%20Public%20Beta-brightgreen">
  <img alt="安全核心依赖" src="https://img.shields.io/badge/safety%20core-zero--dep-orange">
  <img alt="模型调用" src="https://img.shields.io/badge/model%20API-requires%20requests-blue">
  <a href="CHANGELOG.md"><img alt="Latest" src="https://img.shields.io/badge/latest-v1.0.0%20(2026--10--01)-brightgreen"></a>
  <a href="CHANGELOG.md"><img alt="Changelog" src="https://img.shields.io/badge/%E6%9B%B4%E6%96%B0%E6%97%A5%E5%BF%97-CHANGELOG-blue"></a>
</p>

<h1 align="center">ACE · AI Code Engine</h1>

<p align="center">
  简体中文 · <a href="README.md">English</a> · <a href="CHANGELOG.md">更新日志</a> · <a href="docs/README.md">文档索引</a>
</p>

<p align="center">
  <strong>把安全边界放在模型<b>之下</b>的执行层。<br>
  模型提出动作，权限、隔离、快照与回滚由它无法辩解的代码裁决。</strong>
</p>

---

## 名称说明 —— 此 "ACE" 非彼 "ACE"

有多个互不相关的项目、框架与认证都叫 **ACE**。本仓库是 **ACE · AI Code Engine**
（`ace-code-engine/ace-agent`）：一个面向编码代理的**执行层** —— 在每次工具调用执行之前裁决
它能不能执行，并记录发生过什么。

本仓库**不是**以下任何一个，且与其无任何关联：

- **ACE 编辑器**（Ajax.org Cloud9 Editor，以 `ace-builds` 发行）—— 一个浏览器端源代码编辑器；
- **ACE 框架**（Adaptive Communication Environment）—— C++ 网络编程工具包，发行包名为 `libace`；
- **ACE-Step** —— 一个开源的音乐生成模型；
- **ACE: Agentic Context Engineering** —— 一种演化模型上下文的研究方法；
- **Adobe Certified Expert** 与 **American Council on Exercise** 两项认证。

若你是为找代码编辑器、音乐模型、C++ 框架或上下文工程方法而来，那是另一个项目。
本项目可辨识的事实：入口文件是 `ai_code.py`，安装后的命令是 `ace`，裁决逻辑在
`execution_layer.py`，安全核心零第三方依赖。

---

## 一、概述

ACE（AI Code Engine）是面向编码代理的**执行层**。每一次工具调用 —— 文件访问、命令执行、出网、
调用 MCP server —— 在执行之前都要经过同一个裁决点：权限闸门、路径与敏感目标边界、写前快照、
可审计记录。提示词失效时这道边界仍然成立：越狱、注入的网页内容、被篡改的工具输出，都不改变它，
因为它并不写在提示词里。

安全核心为**纯标准库**实现；整条链路中只有模型调用需要 `requests`。其余性质：本地执行（裁决路径
不含云）、模型无关（**9 家厂商 · 10 个入口**由一个 `/provider` 切换，兼容 OpenAI 与 Anthropic
两种报文格式）、所有工具共用一条声明路径（`tools/registry.py`，原生工具 / MCP server / `SKILL.md`
技能同一口）。

## 二、发布状态

| | |
|---|---|
| **版本** | **1.0.0 — 公测（Public Beta）**，2026-10-01 |
| **成熟度** | 能力路线图范围内功能完备；1.0 正式版之前接口仍可能调整 |
| **运行环境** | Python 3.10 / 3.11 / 3.12 |
| **许可** | MIT |
| **验证平台** | Windows 11 x64（主要）· Linux 与 macOS（CI） |

版本号自 1.0.0 起重新起算。此前的 3.x 为内部能力路线图迭代版本，保留在
[更新日志](CHANGELOG.md) 中以便追溯。

## 三、交付形态

每个版本发布三种产物；它们是**并列的三条路**，不是要叠加的层。

| 形态 | 产物 | 装了什么 | 什么时候选它 |
|---|---|---|---|
| **① 直接用 ACE 当你的 agent** | `ace-1.0.0-windows-amd64.msi` · `ace-1.0.0-windows-amd64.zip` | 完整终端 agent：Python 外壳（REPL + Textual）、51 工具、写前快照、`/undo` | 你需要一个能自己干活的 agent |
| **② 把 ACE 当*你的* agent 的 MCP 服务** | `ace-mcp-server-1.0.0.zip` | 非侵入式 MCP 服务；你的 host agent 获得唯一的裁决与审计点 | 你已经在用 Cline / Claude Desktop / Cursor 等 MCP host，只想加边界、不改它 |
| **③ MCP 服务 + 沙箱底座（一体包）** | `ace-sandbox-bundle-1.0.0.zip` | 形态 ② 加**虚拟化底座**的引导，使不可信代码跑在硬件隔离的 microVM 中 | 你既要裁决边界，也要执行边界 |

已安装 ACE 的环境**不需要** ② 或 ③：让 host 指向 `ace.exe --mcp` 即可。② 与 ③ 面向"要边界、
但不装 agent"的场景。

## 四、架构

```
  模型 / host agent             提出一个动作
          |
          v
  ACE 执行层                    裁决：权限、路径、敏感目标、
  （唯一裁决点）                审批、写前快照、审计记录
          |
          +--> 宿主工具          文件、命令、网络、MCP server
          |
          +--> 虚拟化底座（可选，形态 ③）
                                 不可信代码跑在 KVM microVM 中
```

两道边界彼此独立，且**不要求同机**：虚拟化底座可以是一台共享的 Linux 服务，供多台 agent 主机连接。

## 五、快速开始

离线自验 —— 不需要密钥、不需要网络：

```bash
python ai_code.py --mock
```

接入 host agent（形态 ②）：解压包 → 运行 `install-cline.ps1`（或把 `configs/` 中的配置合进你的
host MCP 配置）→ 用 `python verify-mcp.py` 验证。

<p align="center">
  <img src="demo/demo.svg" alt="真实录制的一次离线 ACE 会话：提问、工具调用、回答、状态栏" width="820">
</p>

<p align="center"><sub>由真实会话录制，非效果图。可用 <code>python demo/record_demo.py</code> 重录；用 <code>--check</code> 验证已发布的图仍可复现（CI 每次推送都跑）。更多画面：<a href="docs/SHOWCASE.md">演示与截图</a>。</sub></p>

## 六、安全边界

MCP 形态在标准工具集之外额外提供两个安全工具：

- **`ace_security_scan`** —— 路径级静态扫描（凭据文件、敏感目录、可执行后缀、网络路径）。
  `deep: true` 时追加内容级检查，且**只读文件名已命中凭据清单**的那些文件。每份报告的第一行
  都写着自己的范围声明 —— 因为**扫描完成不等于结论安全**。
- **`ace_sandbox_exec`** —— 在 CubeSandbox microVM 中执行不可信代码。沙箱不可达时**拒绝**（Tier 0），
  **绝不**退回本机执行；宿主凭据不注入沙箱。

其余工具全部经过同一个权限 / 审批 / 审计点。默认权限档为 `readonly`。

两条硬化性质值得写明：克隆来的仓库里的 `.ace/permissions.json` 不能静默放宽审批 ——
它的 `allow` 规则在**信任工作区之前会被丢弃**（`trust_project_hooks` / `trusted_workspaces`），
而 `deny` 规则仍然生效；文件工具也拒绝写 `.git/`（hooks/config）、`.gitmodules`、
`.ace/permissions*.json` —— 模型不能给自己植后门或发通行证。

> 形态 ③ 的包内含 `preflight`，**先报告**这台机器能否承载底座，而不是让安装失败来告诉你。
> Windows 与 macOS 不能承载：KVM 是 Linux 内核机制。

延伸阅读：[安全边界 FAQ](docs/security/SECURITY-FAQ.md) · [MCP server 立项卡](docs/design/MCP-SERVER.md) · [一体包说明](packaging/allinone/README-ALLINONE.md) · [MCP 包说明](packaging/mcp/README-MCP.md)

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

到 [Releases 页面](https://github.com/ace-code-engine/ace-agent/releases) 下载 `ace-<版本>-windows-amd64.zip`，
解压到任意目录，运行 `ace\ace.exe` 即可 —— 自带解释器的完整包，那台机器上**不需要装 Python**。

```powershell
.\ace\ace.exe --mock     # 离线：不需要账号也不需要密钥，先确认这个包是完整的
.\ace\ace.exe            # 接真实模型：进首页选 2 走配置向导
```

两件容易意外的事：**SmartScreen 会拦一下**（没有代码签名 —— 点 *更多信息* → *仍要运行*），
以及**它是一整个目录，不是单个文件**（`ace.exe` 必须和旁边的 `_internal\` 待在一起）。

**冻结发行里哪几项能力不成立、以及"包没跑过就不算构建成功"的那道冒烟门禁** —— [`docs/PACKAGING-EXE.md`](docs/PACKAGING-EXE.md)。

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

**首页**：↑/↓ 选择 · 数字直选 · Enter 确认 · Esc/q 退出。聊天内 `exit` 回首页，首页 `7` / `Esc` / `q` 才真正退出。

```bash
/provider                    # 列出 9 家厂商 · 10 入口（当前标 ✓）
/provider zhipu              # 一键切智谱（自动换到 glm-4.7-flash）
/permission write            # 提权（默认 readonly）
/undo                        # 写入前快照 → 一键回滚
```

输入输出：`Alt+Enter` / `Ctrl+J` 换行 · `Ctrl+R` 逐条往回翻历史（`/history dsk` 按关键词模糊找）·
长输出被卡片折叠，`/expand` 重印 · 写入类卡片给上色 diff 与 `exit N` 退出码。

**完整命令表**（全部斜杠命令、所有 `@` 快捷、每个启动参数）—— **[`docs/COMMANDS.md`](docs/COMMANDS.md)**。

---

## 安全边界

> **先读这个：** **[安全边界 FAQ](docs/security/SECURITY-FAQ.md)** —— 11 个问题，讲清 ACE 挡住了什么、没挡住什么，
> 其中两条最容易反直觉：*无人值守时哪些动作会 fail-close*，以及 *快照不覆盖哪些东西*。

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

**延伸阅读** —— 完整安全模型与生产部署必读：[`docs/security/SECURITY-MODEL.md`](docs/security/SECURITY-MODEL.md)。漏洞报告：[`SECURITY.md`](SECURITY.md)。

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

**最近收口**（R-03 双前端引擎合并 · REL-03 Windows 真机冒烟 · 以及那次冒烟抓出的 `--tools` 回退缺陷）—— 记在 [`CHANGELOG.md`](CHANGELOG.md)。

**仍未验证：**

- **真 TTY 下的 Textual 全屏界面**（没装 `textual` 时那几段会跳过）、以及任何**非 Windows 控制台**。
- **darwin/amd64 执行器产物没有原生冒烟** —— 交叉编译出来了，但没有 Intel Mac 实机跑过。

**延伸阅读** —— 测试框架说明、CI 矩阵、基准 / e2e / 冒烟细节：[`docs/TESTING.md`](docs/TESTING.md)。

---

## 工程债（还没做完的部分，附权威记录）

这一节是**交接清单**，不是待办的第二份副本：每行只说一句"欠什么"，
真正的证据、决定与边界都在那份**立项卡**里 —— **别把这张表当完整说明，点进去看卡**。

| 欠什么 | 一句话 | 权威记录 |
|---|---|---|
| **验收门槛还剩收尾** | 四道 ACC 门槛的机器那一半、A0b（`measured_*` 聚合）、**阈值判据**（`token_verdict`，暂用阈值 50%）都已落地；**只剩** `benchmarks/results/` 接校验器（要等 WP-10 的"下沉前/后可复核数据"） | [`docs/design/ACC-GATES.md`](docs/design/ACC-GATES.md) §7.5 / §8.6 / §10.4 |
| **三层脊柱只剩 HL-04 一条** | `RL-01~04` 与 `DL-01~04` 全部落地；`HL-01/02/03/05` 已落地 —— 只剩 `HL-04`（上报物料必须可判定，接 ACC 门槛）未开工 | [`docs/design/THREE-LAYERS.md`](docs/design/THREE-LAYERS.md) §9 |
| **只剩批次 6 与 WP-10** | 批次 −1…5 已关闭；**批次 6** = 非 URL 出网通道（WP-8 后半）＋ CubeSandbox 沙箱后端（WP-9）；**WP-10** = Rust 核心化（快照哈希 / 流式客户端 / grep / LSP / 路径判定下沉） | [`docs/ROADMAP.md`](docs/ROADMAP.md) §7.2 |

**为什么停在这里：作者要上学。** 这份清单就是交接 ——
每一行都指到那张卡，卡里写着证据、边界，以及"下一步该做什么"。

---

## 文档

### 文档地图

**全部文档都索引在 [`docs/README.md`](docs/README.md)** —— 一张"我想干什么 → 读哪篇"的表，外加完整分组。
最常先要的几篇：

| 想了解 | 去这里 |
|---|---|
| **第一次来先看这个** —— 5 分钟跑起来 · 三维度矩阵 · 十个坑 | [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) |
| **它挡住了什么、没挡住什么** | [`docs/security/SECURITY-FAQ.md`](docs/security/SECURITY-FAQ.md) |
| 演示与截图 · 可直接照做的剧本 | [`docs/SHOWCASE.md`](docs/SHOWCASE.md) · [`examples/`](examples/) |
| 分层架构 · 完整目录树 · ADR 索引 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 安全模型 / 审计 / 漏洞报告 | [`docs/security/`](docs/security/) · [`SECURITY.md`](SECURITY.md) |
| 版本历史 | [`CHANGELOG.md`](CHANGELOG.md) · [`docs/releases/`](docs/releases/) |

### 开发与贡献

改动前请读 `CONTRIBUTING.md`；开发者标准化流程见 `docs/DEVELOPMENT.md`，接口与类型契约见 `docs/INTERFACES.md`，待办见 `docs/BACKLOG.md`。

### 许可

[MIT](LICENSE) © 2026 jincheng3870682453-hash

### 设计参考

架构决策与以下工作对齐 —— **让模型只负责"理解、选择、输出"，把权限、安全、回滚、记忆全部下沉到执行层**：

- [Agent Harness 工程最佳实践](https://github.com/Delphoa/study-awesome-harness-engineering) —— 工具 / 权限 / 记忆 / 沙箱 / 可观测性
- [DeepSeek Harness 设计解析](https://developer.aliyun.com/article/1756780) —— 对应内部调研 `docs/history/dsh_research.md`
- [20 章中文 AI Agent 架构实战](https://github.com/ryzqi/learn-agent)
