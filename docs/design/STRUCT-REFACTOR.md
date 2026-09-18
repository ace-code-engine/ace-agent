# 立项卡：结构重构 R-01 ~ R-05（进行中）

> 状态：**R-01 已闭环 · R-04 完成表驱动部分 · R-02 / R-03 / R-05 待做**
> 来源：`docs/BACKLOG.md` P2「结构级（择机）」。P1 已在 v3.8 全清，P2 是剩下的最后一层。

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
- 剩余：`run_command` 里的前缀补全（约 20 行）可再抽成 `_resolve_command(cmd) -> (name, parts) | None`，让它降到 ~20 行。

## 3. 待做（按性价比排序）

### R-05 · 测试可按段运行（最高性价比，建议先做）

现状：`test_all.py` 5118 行、40 个 `[N]` 段，**只能整跑**（本机一轮约 1-3 分钟）。改一行杀毒规则要等整轮，这直接拖慢本仓库所有后续工作。

- 难点（必须先认清）：段与段之间**共享顶层状态**（`el_h`、`_TE_CLS`、`t()` 之类），单纯按 `print("[N] …")` 切文本会得到"单独跑某段就 NameError"的假能力。
- 做法：按依赖顺序把段整理成 `section(name, requires=[...])` 的注册表——每段声明自己依赖的前置段，`--only N` 时**连带跑它依赖的前置段**（前置段只跑一次、可静默），这样"单跑一段"是真的能跑。
- 分期：①加注册表与 `--only/--skip`（不改段内代码，只加依赖声明）→ ②把无共享状态的段搬进 `tests/` 模块 → ③剩下的共享状态显式化（fixture）。
- 验收：`python test_all.py --only 40` 能在 3 秒内只跑审计回归段并给出与非选择性运行一致的结果；`--skip 20,21` 同理；CI 仍整跑。

### R-02 · `file_tools.py` 拆域

1237 行里挤着文件读写、只读终端、命令执行三条执行路径。拆成 `FileOps` / `TerminalView` / `TerminalExec` 三个 mixin（`ToolExecutor` 已经由 mixin 组合，扩展点现成）。

- 风险：`registry.py` 的 handler 名是**字符串**（`"_exec_terminal_view"`），拆文件后要保证方法仍挂在组合类上；`_exec_via_go` 与沙箱判定是三条路径共用的，先抽到 `base.py` 再拆。
- 验收：`test_all` 全绿（无新增跳过）；`tools/__init__.py` 的组合类不变；`registry.py` 零改动（handler 名不变）。

### R-04（后半） + R-03 · 前端瘦身与双引擎合并

`ai_code.AgentCLI.converse` 234 行；两个前端各有一份模型调用/流式解析（`ai_code` 的 `ModelClient` ↔ `agent_runner` 的 `ModelProvider`）。

- 先做**低风险的一半**：把 `converse` 里"一轮对话"抽成 `_turn()`，把流式渲染抽成 `_render_stream()`——不改行为、不动协议。
- 再考虑合并引擎：两个前端的差异（TUI 交互 vs 无头管道、审批入口不同）集中在少数几处，合并需要先把"会话状态"从 `AgentCLI` 里抽出来（BACKLOG 里写的是"会话状态对象"）。**这一步风险最高**，建议单独立项、单独快照。

## 4. 纪律（沿用本仓库既有约定）

- 每步一个独立快照，可单独 `git revert`；重构不夹带行为变更（要改行为就单独一个提交 + 断言）。
- 改动前跑 `python test_all.py` 取基线（本机 9 项环境性失败是基线，别把它们当新问题）。
- 重构后 `ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` 必须零命中。
- 不为了"看起来整齐"改公开接口：`registry.py` 的 handler 名、`COMMANDS`/`COMMAND_HANDLERS` 的键、`INTERFACES.md` 里的契约都算对外。
