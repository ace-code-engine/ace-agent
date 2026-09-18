# 立项卡：结构重构 R-01 ~ R-05（进行中）

> 状态：**R-01 / R-02 / R-04 / R-05 已闭环 · R-03 完成安全半边（引擎合并仍开放）**
> 来源：`docs/BACKLOG.md` P2「结构级（择机）」。P1 已在 v3.8 全清；本卡记录 P2 的实测规模、做法与验收。

## 0. 收口结果（v3.9 一轮做完的部分）

| 项 | 结果 | 关键数字 |
|---|---|---|
| **R-01** 状态机化 | ✅ 早已闭环（本轮核对） | `process_agent_output` **288 → 17 行** |
| **R-02** file_tools 拆域 | ✅ 完成 | 1237 行 → `file_common`(40) + `file_ops`(768) + `terminal_view`(200) + `terminal_exec`(298) + 兼容层(25)；**25 个方法体逐字节未改**（脚本校验） |
| **R-04** 斜杠表驱动 + 前端瘦身 | ✅ 完成 | `run_command` **125 → 25 行**（`_resolve_command` 再抽 32 行）；`converse` **234 → 175 行**（`_model_turn` 46 + `_note_round_progress` 25） |
| **R-05** 分段运行 | ✅ 完成 | 35 个段包进 `if _want(N)`；`--only/--skip/--upto/--list`；`--only 40` 从 14s → **0.3s**；`[41]` 运行器自检 |
| **R-03** 双前端引擎合并 | ◐ **安全半边完成**：`ace_model.py`（历史裁剪 + 错误码提示，两边共用）；**流式客户端合并仍开放**，理由见 §3 | `_trim_history` 口径统一到 2N 条 |

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

### R-03 · 双引擎合并 —— ◐ 只做了安全半边（见下）

`ai_code.AgentCLI.converse` 原先 234 行；两个前端各有一份模型调用（`ai_code` 的 `ModelClient` ↔ `agent_runner` 的 `ModelProvider`）。

**已完成的安全半边（v3.9）**：新增 `ace_model.py`——把两边**确实重复、且是纯函数**的部分收拢：

- `trim_history(messages, max_history)`：口径统一在"最近 N 轮 = 2N 条消息"。原先 ai_code 的 `trim_messages` 与 agent_runner 的 `_trim_history` 各写一份，而后者是就地改 `self.history`；现在两边都调它。
- `error_hint(exc, translate)`：HTTP 错误码 → i18n 键（原先只在 ai_code 里）。
- 这个模块**不 import 项目内任何模块**（与 `ace_isolation` 同一取态），谁都能安全引它；i18n 的 `t` 由调用方注入，它自己不认识界面语言。

**未做、且不建议硬做的部分**：把两个客户端合成一个。原因不是"没时间"，是**风险与收益不成比例**：

- 两者形态不同：`ModelClient` 是"流式 + requests + 重试 + Anthropic 兼容"，`ModelProvider` 是 urllib 一次性调用；
- 输出契约不同：交互式前端边流边渲染，无头前端只认 `🤖 Agent:` 那一行（`e2e/real_model_smoke.py` 与 CI 都依赖它）；
- 现有测试**只覆盖 mock 路径**，真机行为要靠真实模型才能验证——合并等于重写无头前端的行为，属于"改行为"，按本卡纪律（重构不夹带行为变更）必须先单独立项 + 真机验证。

要推进它，建议顺序：① 先给无头前端补一个"真实模型下的输出契约"冒烟（已有 `e2e/real_model_smoke.py` 可扩展）→ ② 抽 `session_state`（把会话状态从 `AgentCLI` 里拿出来）→ ③ 最后才合并客户端。

## 4. 纪律（沿用本仓库既有约定）

- 每步一个独立快照，可单独 `git revert`；重构不夹带行为变更（要改行为就单独一个提交 + 断言）。
- 改动前跑 `python test_all.py` 取基线（本机 9 项环境性失败是基线，别把它们当新问题）。
- 重构后 `ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` 必须零命中。
- 不为了"看起来整齐"改公开接口：`registry.py` 的 handler 名、`COMMANDS`/`COMMAND_HANDLERS` 的键、`INTERFACES.md` 里的契约都算对外。
