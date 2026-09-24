# 立项卡：结构重构 R-01 ~ R-07（进行中）

> 状态：**R-01 / R-02 / R-04 / R-05 / R-07 已闭环 · R-03 客户端合并已落地，两侧验收（无凭证契约 7/7 + 真实厂商端点）均已通过**
> 来源：`docs/BACKLOG.md` P2「结构级（择机）」。P1 已在 v3.8 全清；本卡记录 P2 的实测规模、做法与验收。

## 0. 收口结果（v3.9 一轮做完的部分）

| 项 | 结果 | 关键数字 |
|---|---|---|
| **R-01** 状态机化 | ✅ 早已闭环（本轮核对） | `process_agent_output` **288 → 17 行** |
| **R-02** file_tools 拆域 | ✅ 完成 | 1237 行 → `file_common`(40) + `file_ops`(768) + `terminal_view`(200) + `terminal_exec`(298) + 兼容层(25)；**25 个方法体逐字节未改**（脚本校验） |
| **R-04** 斜杠表驱动 + 前端瘦身 | ✅ 完成 | `run_command` **125 → 25 行**（`_resolve_command` 再抽 32 行）；`converse` **234 → 175 行**（`_model_turn` 46 + `_note_round_progress` 25） |
| **R-05** 分段运行 | ✅ 完成 | 35 个段包进 `if _want(N)`；`--only/--skip/--upto/--list`；`--only 40` 从 14s → **0.3s**；`[41]` 运行器自检 |
| **R-07** 根目录瘦身 | ✅ 完成 | 根级 `.py` **24 → 4**（`ai_code.py` / `agent_runner.py` / `execution_layer.py` / `test_all.py`）；20 个模块下沉 `ui/` `cli/` `core/`；导入改写 **77 处 / 19 文件** |
| **R-03** 双前端引擎合并 | ✅ **客户端合并已落地**：`core/ace_client.py`（493 行）是唯一一份模型 HTTP 客户端；`core/ace_model.py` 继续管共用纯逻辑 | 见 §5 |

### 这一轮踩到的两个"重构陷阱"（都写进代码注释了）

1. **脚本切方法会漏类属性**：`_ABS_PATH_WRITE_TOOLS` / `_NT_SWITCH_RE` / `_DOS_DIR_SWITCH_RE` 是类级赋值，不在 `def` 范围里，第一版拆分把它们丢了 —— 被测试当场抓住（`'ToolExecutor' object has no attribute '_ABS_PATH_WRITE_TOOLS'`）。
2. **源码守卫会假失败**：有 4 条断言直接读 `tools/file_tools.py` 找字符串；代码搬了房间，断言就报错。现在统一走 `_tools_src(...)`（按模块名拼读），日后调整文件划分只改一行。

## 1. 现状实测（不是照抄 BACKLOG 的描述）

| 目标 | 文件 | 当前规模 | 最长函数（实测） |
|---|---|---|---|
| R-01 状态机化 | `execution_layer.py` | 1611 行 | `process_agent_output` **17 行**（`_run_round` 52、14 个 `_stage_*`） |
| R-02 拆 FileTools | `tools/file_tools.py` | 1237 行 | `_exec_terminal_view` 157 / `_exec_terminal_exec` 148 / `_exec_str_replace` 128 |
| R-03 双前端合并 | `ai_code.py` + `agent_runner.py` | 3114 + 764 行 | `converse` 234（ai_code）/ `main` 96（agent_runner） |
| R-04 表驱动 | `ai_code.py` | 3114 行 | `run_command` **46 行**（重构前 125）/ `converse` 234 |
| R-05 测试拆分 | `test_all.py` | 5118 行 | 无法按段运行（`--only/--skip` 不存在） |
| R-06 命名/检索索引 | — | — | ✅ 已完成（`INTERFACES.md §11`） |

## 2. 已完成

### R-01 · `process_agent_output` 拆状态机 —— ✅ 结构性完成

`process_agent_output` 现在只有 **17 行**：解析 → 建 `RoundCtx` → `_run_round` → 轮末 `finally` 回收。单轮逻辑落在 `_run_round`（52 行）与 14 个 `_stage_*`（`_stage_parse` / `_stage_route` / `_stage_permission` / `_stage_code_gate` / …）。

- 验收：`test_all` 有「阶段可脱离整轮单测」「顺序守卫」「轮末回收」三组断言（含显式传 `RoundCtx` 的调用方式）。
- 剩余：`_stage_permission` 103 行（外发闸门 + 项目外确认 + 逐次确认 + 权限裁决挤在一处），下一步可拆成 `_gate_confirm_*` 三块。

### R-04（前半）· 斜杠命令表驱动 —— ✅ 完成

`COMMANDS`（name → i18n 键）保留为类属性；新增 `COMMAND_HANDLERS`（name → (方法名, 是否收 parts)），`run_command` **125 → 46 行**：

- 分发从中缀 if/elif 变成查表 + 调用 + 返回值归一（只有显式 `False` 表示退出，`None` 仍视为继续——与旧口径一致，这点在卡片里写明，免得后人"顺手改成真值判断"）。
- 三张用途合一：`/help` 列表、前缀补全、实际分发都从这两张表派生。
- **漂移守卫**：`test_all` 断言两张表键集一致、每个 handler 真实存在、`/exit` 是唯一退出命令。
- **已完成（v3.9）**：前缀补全抽成 `_resolve_command(cmd) -> (name, parts) | None`，`run_command` 46 → **25 行**；`converse` 234 → **175 行**（`_model_turn` 46 + `_note_round_progress` 25）。
- 顺带修掉一处**源码守卫的假失败**：原先"压缩紧跟在 trim_messages 之后"是盯字面相邻的，提函数后语义没变但字面变了；现在改盯语义顺序（trim 在 `_model_turn` 内、压缩紧随其调用）。

## 3. 剩余与过程中的结论

### R-07 · 根目录瘦身（包化）—— ✅ 完成（v3.10.0）

触发：根目录躺着 **24 个 `.py`**，找一个模块要在滚屏里翻；`ui` / `cli` / `core` 的边界早就存在，只是没在文件系统上表达出来。做法与实测：

| 包 | 收进去的模块 | 依据 |
|---|---|---|
| `ui/` | `ace_theme` `ace_selector` `ace_cards` `ace_chatscroll` `i18n` | 终端表现层：只负责画，不参与任何裁决 |
| `cli/` | `ace_doctor` `ace_context` `ace_sessionlog` | 操作者侧工具：自检 / 上下文判定 / 事件日志 |
| `core/` | `ace_execpolicy` `ace_net` `ace_isolation` `ace_http` `ace_executor` `ace_model` `work` `guardian` `archive` `nuwa` `universal_document_parser` `version` | 引擎支撑：策略 / 网络 / 执行器客户端 / 记忆与快照 |

根目录只留 **`ai_code.py`（前端入口）、`agent_runner.py`（交互循环）、`execution_layer.py`（执行层）、`test_all.py`（测试）**。

- 机制：脚本做机械改写（`import X` → `from pkg import X`、`from X import …` → `from pkg.X import …`），**77 处 / 19 个文件**；随后用全量测试与 `[38]` 结构守卫当验收。
- 三处 `__file__` 相对资源是唯一天然陷阱：`i18n.py`(`locales/`)、`ace_doctor.py`（仓库根）、`ace_executor.py`（`executor/` 二进制）——下沉一层后都要 `parent.parent`。`locales/` 与 `executor/` 保持根级不动。
- 两类"不是 import 的引用"必须单独找：① `mock.patch("ace_net.safe_request")` 这类**点号字符串**；② 断言源码里**导入写法**的守卫（`"from ace_net import check_url" in src`）。前者改 `core.ace_net.safe_request`，后者改 `from core.ace_net import check_url`。
- 命令入口随包名变：`python ace_doctor.py` → `python -m cli.ace_doctor`（模块内 `from core import version` 需要仓库根在 `sys.path`，`-m` 满足）。
- 构建接线同步：`ci.yml` 的 `compileall` 由 20 个文件名换成 `cli core ui` 三个包目录；`release-executor.yml` 两处 `python -c 'import version'` → `'from core import version'`。
- 历史记录不动：`CHANGELOG.md`、`docs/history/**`、以及 `ARCH-TREE-CHECK.md` 的旧示例保持原样（那是当时的记录），只在 `ARCH-TREE-CHECK.md` 顶部加一行"模块已下沉、R1-R4 规则未变"的导流说明。
- 验收：全量测试 **1081/1090 —— 与本机基线逐项一致**（9 项 Go 执行器环境性失败，改动前后同名同数）；`[38]` 结构守卫 5/5 全绿；`ruff` 零命中；文档链接 113 条 0 死链；演示动画 `--check` 两张图均与 CLI 输出一致。（过程中确实先红过两条：`[38]` 树里有 20 条幽灵条目 + 仓库根级漏登记 `ui/cli/core`，以及 `mock.patch("ace_net.safe_request")` 与一条源码守卫——这些是搬家必须付的账，补完后归零。）

### R-05 · 测试可按段运行 —— ✅ 完成（v3.9）

现状：`test_all.py` 5118 行、40 个 `[N]` 段，**只能整跑**（本机一轮约 1-3 分钟）。改一行杀毒规则要等整轮，这直接拖慢本仓库所有后续工作。

- 难点（必须先认清）：段与段之间**共享顶层状态**（`el_h`、`_TE_CLS`、`t()` 之类），单纯按 `print("[N] …")` 切文本会得到"单独跑某段就 NameError"的假能力。
- 做法：按依赖顺序把段整理成 `section(name, requires=[...])` 的注册表——每段声明自己依赖的前置段，`--only N` 时**连带跑它依赖的前置段**（前置段只跑一次、可静默），这样"单跑一段"是真的能跑。
- 分期：①加注册表与 `--only/--skip`（不改段内代码，只加依赖声明）→ ②把无共享状态的段搬进 `tests/` 模块 → ③剩下的共享状态显式化（fixture）。
- 验收：`python test_all.py --only 40` 能在 3 秒内只跑审计回归段并给出与非选择性运行一致的结果；`--skip 20,21` 同理；CI 仍整跑。

### R-02 · `file_tools.py` 拆域 —— ✅ 完成（v3.9）

1237 行里挤着文件读写、只读终端、命令执行三条执行路径。拆成 `FileOps` / `TerminalView` / `TerminalExec` 三个 mixin（`ToolExecutor` 已经由 mixin 组合，扩展点现成）。

- 风险：`registry.py` 的 handler 名是**字符串**（`"_exec_terminal_view"`），拆文件后要保证方法仍挂在组合类上；`_exec_via_go` 与沙箱判定是三条路径共用的，先抽到 `base.py` 再拆。
- 验收：`test_all` 全绿（无新增跳过）；`tools/__init__.py` 的组合类不变；`registry.py` 零改动（handler 名不变）。

### R-03 · 双引擎合并 —— ✅ 客户端已合一（验收的厂商半边另计，见 §5）

`ai_code.AgentCLI.converse` 原先 234 行；两个前端各有一份模型调用（`ai_code` 的 `ModelClient` ↔ `agent_runner` 的 `ModelProvider`）。

**第一步：安全半边（v3.9）**——新增 `core/ace_model.py`，把两边**确实重复、且是纯函数**的部分收拢：

- `trim_history(messages, max_history)`：口径统一在"最近 N 轮 = 2N 条消息"。原先 ai_code 的 `trim_messages` 与 agent_runner 的 `_trim_history` 各写一份，而后者是就地改 `self.history`；现在两边都调它。
- `error_hint(exc, translate)`：HTTP 错误码 → i18n 键（原先只在 ai_code 里）。
- 这个模块**不 import 项目内任何模块**（与 `ace_isolation` 同一取态），谁都能安全引它；i18n 的 `t` 由调用方注入，它自己不认识界面语言。

**第二步：客户端合一（本轮，见 §5）**——`core/ace_client.py` 成为唯一一份模型 HTTP 客户端。原先"不建议硬做"的三条理由，逐条被**契约**而不是被"反正能跑"化解：

| 当初的顾虑 | 现在怎么处理 |
|---|---|
| 两者形态不同（流式+requests+重试+Anthropic vs urllib 一次性） | 客户端同时提供 `chat_stream`（流式，CLI 用）与 `chat_once`（一次性，无头用），**两种线格式**都在同一份实现里；重试与错误规范化只写一遍（`ace_http`） |
| 输出契约不同（边流边渲染 vs `🤖 Agent:` 单行） | 契约**留在前端**：`on_delta` 回调由 CLI 提供，无头前端拿整段。客户端不认识"谁在渲染" |
| 现有测试只覆盖 mock 路径 | 补 `e2e/r03_contract_smoke.py`：真监听 socket + 两种线格式驱动两个前端（7/7），钉住请求形状与输出契约；`[8]`/`[42]` 另有 17 条静态守卫（唯一出网点、唯一拼端点处、降级循环只一份） |

**厂商那一半也已走通（2026-09-25）**：`python e2e/real_model_smoke.py` + `ACE_E2E_BASE_URL=https://api.deepseek.com/v1` / `ACE_E2E_MODEL=deepseek-chat` —— **exit 0，命中 `🤖 Agent:` 单行契约**。日志里能看到完整闭环：模型先按提示调用 `datetime_now`，再依据工具真实结果作答（"今天是 2026 年 9 月 25 日"），不是编的。这一跑走的正是**不带 `--tools`** 的文本协议路径 —— 也就是下面那条缺陷的现场，修好之前它会打 `FAIL`。

**顺带抓到的真缺陷（本轮真机冒烟）**：`_generate_text` 过去把模型的纯文本直接返回，而 `generate()` 的契约是"返回执行层能解析的协议文本"——于是不带 `--tools` 时永远到不了 `FINAL_REPLY`，只打印"达到最大轮数，Agent 未给出最终回复"。mock 分支与 `_generate_tools` 都会包装，所以此前无测试覆盖。已按同口径修好，`[8]` 补两条断言（先看着它红，再修）。真实模型跑通那一跑，就是这条修复的验收。

## 4. 纪律（沿用本仓库既有约定）

- 每步一个独立快照，可单独 `git revert`；重构不夹带行为变更（要改行为就单独一个提交 + 断言）。
- 改动前跑 `python test_all.py` 取基线（本机 9 项环境性失败是基线，别把它们当新问题）。
- 重构后 `ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` 必须零命中。
- 不为了"看起来整齐"改公开接口：`registry.py` 的 handler 名、`COMMANDS`/`COMMAND_HANDLERS` 的键、`INTERFACES.md` 里的契约都算对外。

## 5. R-03 收口的实测与验收（本轮）

**改动规模**（合并提交 `refactor(model): R-03 收口 —— 两个前端共用唯一一份模型 HTTP 客户端`）：

| 文件 | 变化 |
|---|---|
| `core/ace_client.py` | **新增 493 行** —— 唯一一份客户端：`chat_stream` / `chat_once`、OpenAI 与 Anthropic 两种线格式、`ChatHTTPError` 规范化、`resolve_error`、`openai_payload` / `anthropic_payload(_variants)` |
| `ai_code.py` | **−307 行**（自有请求/重试/降级实现移除） |
| `agent_runner.py` | −44 行（`_post_chat` 改为一行委托） |
| `core/ace_model.py` | 微调（与客户端的职责边界写清） |
| `test_all.py` | +136 行断言 |

**与 `main` 的合并**：`git merge-tree` 预演零冲突；实做 `--no-ff` 合并后仅 6 个文件变化（`core/ace_client.py` 新增 + 上述），没有一处需要人工裁决。

**验收证据**（都在本机实跑，不是读代码得出的）：

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量回归（合并前基线，`main`） | `python test_all.py` | **1979 / 1980** —— 唯一失败是 `[38] 树中路径全部存在`，因为新加的 `e2e/*` 在权威树里已登记、在这个分支上还是未跟踪文件 |
| 全量回归（合并后） | `python test_all.py` | **1993 / 1993 全绿 · 跳过 13**（跳过=缺 `requests` / 缺 `textual` 的能力探测） |
| 双前端输出契约（无凭证） | `python e2e/r03_contract_smoke.py` | **7 / 7** —— 真监听 socket、两种线格式、两个前端；请求日志确认无头走 `stream=false`、CLI 走 `stream=true`，`--tools` 确实出现在 payload 里，429 会退避重试 |
| 真机启动器冒烟（REL-03） | `powershell -ExecutionPolicy Bypass -File e2e/rel03_native_smoke.ps1` | **3 / 3** —— 启动器 / 直接入口 / `chcp 936` |

| 真实厂商端点（R-03 厂商半边） | `python e2e/real_model_smoke.py`（`ACE_E2E_*=DeepSeek`） | **OK · exit 0** —— 命中 `🤖 Agent:` 单行契约；模型先调工具再依据真实结果作答。**注意跑它的解释器必须装了 `requests`**：第一跑用仓库内那个精简 venv 时失败在 `No module named 'requests'`，那是环境不是代码 |
| 全量 | `python test_all.py` | **1980 / 1980 全绿 · 跳过 13** |

**没做的**：`session_state` 抽取（`R-04` 遗留，与本卡解耦，属独立重构）。

**方法论上值得留一句的两个坑**：

1. `e2e/r03_contract_smoke.py` 的第一版对**每个**请求都回 SSE、对工具调用模型**每次**都回工具调用，于是两个前端都被逼到轮数上限——看起来像前端的 bug，其实是手具的形状错了。假端点必须**照着请求的 `stream` 标志**回答，且工具调用只在第一轮给。手具本身也会说谎，先怀疑它。
2. **两套守卫各自是绿的，合起来才第一次碰面。** `main` 上有 3 条 R-03 之前写的接入点守卫（断言"ai_code 里恰好 3 处 `ace_http.request_with_retry`"），而 R-03 用 `[8]`/`[42]` 的新守卫替换过它们——替换只发生在 `r03-verify` 上。合并前，用 `r03-verify` 的测试跑 `r03-verify` 的代码永远是绿的；那三条守卫从未与 R-03 后的代码一起运行过。合并后的第一次全量才把这件事翻出来（1977/1980）。已按新架构改写（见提交 `fix(test): [21] 接入点守卫对齐 R-03 后的新架构`）。
