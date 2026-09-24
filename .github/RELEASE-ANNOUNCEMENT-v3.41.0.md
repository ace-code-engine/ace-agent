# ACE v3.41.0 · 现在有预编译 Windows 发行包了

> 本条同时作为 v3.41.0 的发布说明，可直接粘进 Release。
> 一行摘要：**不用装 Python，下载解压就能跑；模型可以完全跑在你自己机器上（离线演示不需要任何密钥）。**

---

## 中文

### 这一版给你什么

**① 预编译 Windows 发行包（新）**

`ace-3.41.0-windows-amd64.zip` —— 解压到任意目录，运行 `ace\ace.exe`。**那台机器上不需要装 Python。** 没有安装程序，也不会往你选的目录之外写东西。

```powershell
.\ace\ace.exe --mock     # 离线先确认这个包是完整的，不需要账号也不需要密钥
.\ace\ace.exe            # 接真实模型：进首页选 2 走配置向导
```

跑之前两件小事：**SmartScreen 会拦一下**（这个构建没有代码签名，点"更多信息 → 仍要运行"即可，这是未签名二进制的正常样子）；**它是一整个目录，不是单个文件**——`ace.exe` 必须和旁边的 `_internal\` 待在一起。

**② 两个前端合并到同一份模型客户端**

以前 CLI 和无头运行各有一份自己的模型调用实现（一份流式 + requests + 重试 + Anthropic 兼容，一份 urllib 一次性调用，输出契约也不同）。现在只剩 `core/ace_client.py` 一份：全仓**一处**出网点、**一处**拼 `/chat/completions`。`ai_code.py` −307 行，`agent_runner.py` −44 行。两个前端只保留自己的调用契约（CLI 走流式，无头拿整段）。

**③ 顺带修掉一个"永远答不出来"的缺陷**

`_generate_text`（不带 `--tools` 的文本协议回退）过去把模型的**裸文本**直接交给执行层，而执行层要的是协议文本。结果是：不带 `--tools` 时，模型无论答什么都进不了最终回复，屏幕上只会反复出现"达到最大轮数"。

这个缺陷藏了很久，因为 mock 分支和 `--tools` 分支**都会**正确包装——**"两条路都对"不等于"第三条路也对"**。是在真实模型端点上跑验证时才露出来的。

### 包里有什么

| 能力 | 状态 |
|---|---|
| 对话、工具、文件读写、终端、权限裁决、写前快照与回滚 | ✅ |
| 9 家厂商 · 10 个入口（智谱 / DeepSeek / Moonshot / OpenAI / Anthropic / 通义千问 / SiliconFlow / OpenRouter / Ollama），42 个工具 | ✅ |
| `code_execute` | ❌ 如实返回 **501**，并说明原因 |
| `--install-ui` / `--setup` | ❌ 无意义（包里已自带解释器与界面依赖） |

`code_execute` 在打包形态下不提供，是因为它靠 `sys.executable` 去跑 Python 代码，而冻结后那就是 `ace.exe` 自己——机器上没有第二个解释器可用。**它不会静默失败，而是明确告诉你这一档不提供该能力**；需要它请用源码运行。同理，我们**没有**让它去"猜一个系统 Python"：那会让同一份发行包在不同机器上能力不同，比明确禁用更难排查。

### 怎么开始

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python test_all.py         # 端到端测试；核心是纯标准库
python ai_code.py --mock   # 离线演示：完整跑一遍 模型 ↔ 执行层 闭环
```

接真实模型：`python ai_code.py` → 首页 `2` 走配置向导 → `1` 进聊天，或一行 `/provider deepseek <key>`。

### 关于安全边界（这是这个项目的重点）

大多数 agent 把安全放在提示词里（"请不要删除文件"）。ACE 不这么做：**每一次工具调用都要穿过一个独立的执行层**，由它做权限裁决、危险行为检测，并在任何写入之前做物理快照。提示词失效时——越狱、注入的网页、被篡改的工具输出——**那一层还在**。

三档隔离（off / job / docker）**拿不到边界就返回 503，绝不静默降级**；`terminal_exec` **每次**都问人（它的黑名单可以被绕过，所以人本身才是边界）；出站目的地不认识就要确认。

### 验证到什么程度

- 全套测试 **1985 / 1985 通过**，跳过 13 项（本机缺 `requests` 与 `textual` 时的能力探测项）。
- 真实模型端到端：对 DeepSeek 跑通——模型先调用时间工具、再依据**真实返回**作答，不是编的。
- 打包有**冒烟门禁**：产物必须真跑过 `--version` / `--preview` / 离线工具往返 / 原生工具调用四条路径才允许发布，任一失败即中止发布。

### 已知未验证

- **darwin/amd64 执行器产物没有原生冒烟**：交叉编译成功了，但没有 Intel Mac 实机跑过。
- **真 TTY 下的全屏界面**（Textual）：本机缺该依赖时相关用例会跳过。
- 非 Windows 控制台未做真机冒烟。

我们把这些写在 README 的「已知未完成与未验证」里，而不是等你自己撞上。本项目有一条纪律：**没真正跑过的，不许说成"应该没问题"**。

---

## English

### What this version gives you

**① A prebuilt Windows bundle (new)**

`ace-3.41.0-windows-amd64.zip` — unzip anywhere, run `ace\ace.exe`. **No Python required on that machine.** No installer, and nothing is written outside the folder you pick.

```powershell
.\ace\ace.exe --mock     # offline: confirm the bundle is intact, no account or key needed
.\ace\ace.exe            # real models: pick 2 on the landing screen for the setup wizard
```

Two small things first: **SmartScreen will warn you** — the build is not code-signed, so choose *More info* → *Run anyway* (that is what an unsigned binary looks like, not a broken one); and **it is a folder, not a single file** — `ace.exe` must stay next to its `_internal\` directory.

**② Both frontends now share one model client**

The CLI and the headless runner each used to carry their own model-calling implementation (one streaming + requests + retries + Anthropic compatibility, the other a one-shot urllib call, with different output contracts). Now there is only `core/ace_client.py`: **one** egress point in the whole repo, **one** place that builds `/chat/completions`. `ai_code.py` −307 lines, `agent_runner.py` −44. Each frontend keeps only its own calling contract (the CLI streams, the headless runner takes the whole reply).

**③ A bug that made one path unable to ever answer**

`_generate_text` (the text-protocol fallback used when `--tools` is off) handed the model's **plain text** straight to the execution layer, which expects protocol text. The result: without `--tools`, whatever the model answered, it could never reach a final reply — the screen just said "max rounds reached", over and over.

It stayed hidden because the mock path and the `--tools` path **both** wrap correctly — **"two paths are right" does not mean "the third one is"**. A real-model endpoint run is what exposed it.

### What is in the bundle

| Capability | Status |
|---|---|
| Chat, tools, file I/O, terminal, permission decisions, pre-write snapshots and rollback | ✅ |
| 9 vendors · 10 endpoints (Zhipu / DeepSeek / Moonshot / OpenAI / Anthropic / Qwen / SiliconFlow / OpenRouter / Ollama), 42 tools | ✅ |
| `code_execute` | ❌ returns **501**, and says why |
| `--install-ui` / `--setup` | ❌ meaningless (the bundle ships its own interpreter and UI deps) |

`code_execute` is not offered in the frozen build because it runs Python code via `sys.executable`, which is `ace.exe` itself once frozen — there is no second interpreter to use. **It does not fail silently; it tells you this distribution does not provide that capability.** Use the source build if you need it. We deliberately did **not** make it hunt for a system Python: that would make the same bundle behave differently on different machines, which is harder to diagnose than an explicit refusal.

### Getting started

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python test_all.py         # end-to-end suite; the core is pure stdlib
python ai_code.py --mock   # offline demo: the full model <-> execution-layer loop
```

Real models: `python ai_code.py` → `2` on the landing screen for the setup wizard → `1` to enter chat, or `/provider deepseek <key>` in one line.

### About the security boundary (this is the point of the project)

Most agents put safety in the prompt ("please don't delete files"). ACE does not: **every tool call passes through a separate execution layer** that decides permissions, detects dangerous behaviour, and takes a physical snapshot before any write. When the prompt fails — a jailbreak, an injected web page, tampered tool output — **that layer is still there.**

Three isolation tiers (off / job / docker) **return 503 rather than silently degrading** when the boundary is unavailable; `terminal_exec` asks a human **every time** (its blacklist is bypassable, so the human *is* the boundary); an unknown outbound destination is confirmed before anything leaves the machine.

### How far it is verified

- Full suite: **1985 / 1985 passing**, 13 skipped (capability probes for absent `requests` / `textual`).
- Real-model end to end: green against DeepSeek — the model called the time tool first and then answered from the **real result** rather than inventing one.
- The build has a **smoke gate**: the packaged exe must actually run `--version`, `--preview`, an offline tool round trip and the native tool-call path before anything is published; any failure aborts the release.

### Known unverified items

- **The darwin/amd64 executor artifact has no native smoke test**: it cross-compiles, but no Intel Mac has ever run it.
- **The Textual full-screen UI under a real TTY**: those cases skip when the dependency is absent.
- No native smoke run on non-Windows consoles.

These live in the README's "Known gaps and unverified items" section rather than waiting for you to hit them. The project has one rule: **anything not actually run does not get described as "should be fine".**

---

**Source** · [Repository](https://github.com/ace-code-engine/ace-agent) · [README](https://github.com/ace-code-engine/ace-agent#readme) · [Getting started](docs/GETTING-STARTED.md) · [Security model](docs/SECURITY-MODEL.md) · [Changelog](CHANGELOG.md) · [Why no pip install](docs/PACKAGING.md) · [Packaging notes](docs/PACKAGING-EXE.md)
