# 待办事项(BACKLOG)

> 由 2026-09-05 四视角体检(安全复核 / 架构 / 测试与 CI / 文档产品化)+ 实测复现整理。
> 约定:编号 `SEC-`(安全)、`Q-`(快速赢项/质量)、`R-`(结构重构)、`REL-`(发布)。
> 已完成项进 `CHANGELOG.md`;领取后在此勾选。工作量:S/M/L;来源列 = 审查视角。

## P0 — 安全(全部经真实复现验证,建议最先做)

| ID | 事项 | 证据/说明 | 建议 | 工作量 |
|---|---|---|---|---|
| ✅ SEC-01 | **code_execute 沙箱可绕过 → RCE/任意写** | `code_tools.py:80-91` 只拦 Call.func 精确名;实测 `f=open;f(..)('a','w')`、`(lambda:open)()(...)` 成功落盘、`(lambda:exec)()('print(1)')` 成功执行 | Name/引用级白名单或去 builtins;叠 Go 执行器/job 边界;补 6 条回归测试 | M |
| ✅ SEC-02 | **parse_document 只读越界读** | `parse_tools.py:22-29` 不过 confine/sensitive;readonly 下读项目外 README/execution_layer.py 实测 SUCCESS(file_read 同路径 403) | 与 file_read 同口径路径判定+敏感目标+回归测试 | S |
| ✅ SEC-03 | **默认权限矛盾 + 外发零确认** | 已闭合(v3.8)：前半——`agent_runner.py:668` / `execution_layer.py:1344` / `ai_code.py:656` 三入口默认均为 `readonly`；后半——注册表新增 `ToolSpec.egress`（`api_get`/`api_post`/`browser_open`/`browser_navigate`/`notify_send`），执行层在目的地不在内置清单也不在用户 `egress_allowlist` 时**逐次弹确认**，并拒绝会话级授权（授权按工具名给 = 出口全开，要免问请用白名单指定域名）；`notify_send` 按渠道判（console/file/toast 不问，email 每次问）。测试覆盖 8 条（未配清单要问 / 内置端点不问 / 白名单内不问 / 白名单外仍问 / 已批准不重复问 / 会话级降级 / email 要问 / console 不问） | S-M |
| ✅ SEC-04 | 快照 HMAC 默认关 + 敏感文件明文入 `.guardian` | `guardian.py:142/60`;signing_key 不配即无签名;.env/.pem 无排除 | 默认生成项目外密钥;敏感文件只记哈希;补测试 | M |
| ✅ SEC-05 | `browser_screenshot` 属只读且无确认 | `registry.py:117-119` | 归 WRITE + 逐次确认 | S |
| ✅ SEC-06 | execpolicy allow 档小洞 | `ace_execpolicy.py:314` 跳过 `-` 开头 token 可越区;`git config` 被当只读可 `--global` 写 | 选项值含路径不跳过;config 限 `--get/--list` | S |

## P1 — 快速赢项(低风险,按序做)

| ID | 事项 | 说明 | 工作量 |
|---|---|---|---|
| ✅ Q-01 | ruff 扩选 F401/F841/E711/F811 | 实测 F401=42 死导入全可 autofix(execution_layer.py:27-31 os/ast/html) | S |
| ✅ Q-02 | bench 功能 check 失败应 exit≠0;`benchmarks/results/` 入 .gitignore | 现在退出码恒 0、结果入库致本机跑即脏树 | S |
| ✅ Q-03 | test_all 环境敏感自识别(SKIPPED 通道 + `--strict`) | Go Job Object 附加失败/缺 requests/禁联网/系统 temp 只读应跳过并如实标注,不许假绿/整脚本 traceback;9 处裸 mkdtemp 统一走 `.test_tmp` | M |
| ✅ Q-04 | 文档/CI 手抄数字单一来源 | 已完成(v3.8)：README 里的提供商家数（原写 10 家）改为"9 家厂商 · 10 入口"；CHANGELOG 头部去掉写死的断言总数（改为"以 test_all 输出为准"）；`test_all.py` 新增 `[39]` 节自动校验——文档中"家厂商 · 入口"/"家提供商"/"个工具"三类口径必须与 `PROVIDERS` / `TOOL_SPECS` 实测一致，且 README/CONTRIBUTING/CHANGELOG 头部不得出现硬编码的用例/断言总数 | S |
| ✅ Q-05 | `ace.cmd` 硬编码 `C:\aider_env\...` | 第 10 行,换机器必炸;改 PATH 探测 python/py | S |
| ✅ Q-06 | CI 结构一致性校验 | 已完成(v3.8)：权威树迁至 `docs/ARCHITECTURE.md` 并补齐 13 条缺口(根级 9 + `.github` 2 + `tools` 2)；`test_all.py` 新增 `[38]` 节自动校验"树↔文件"(R1 存在性/R2 根级/R3 已展开目录/R4 compileall)，随 CI 三档 Python 顺带执行，无需新增 job。立项卡 `docs/design/ARCH-TREE-CHECK.md` | S |
| ✅ Q-07 | prompts 工具清单 ↔ registry 差集 | 已完成(v3.8)：实测差集——`agent_system_prompt_tools.md` 漏 11 个、`agent_system_prompt_v7.md` 漏 13 个（kb_/skill_/goal_/subagent/search_read/browser_navigate/plan_propose/request_permission 等族全部缺席），`v8` 已齐；已按 registry 的真实权限分组重写 tools 版的【可用工具】并给 v7 补 22-34 条（参数照抄 `ToolSpec.example`，不臆造）。同时修掉两处**可用性谎言**：v7/tools 都写着"browser_click / browser_type 尚未实现(501)"，实际早已实现；v7 的"email 暂未接入(501)"实际是"未配 SMTP 才 501"。CI 守卫：test_all 的提示词断言从"只查 v8"扩到三个运行时提示词全覆盖 | S-M |
| ✅ Q-08 | e2e smoke 抗抖动 | 已落地：`e2e/real_model_smoke.py` 最多 3 次尝试、每次 150s 超时，第 1 次带工具调用、后两次换浅提问，任一成功即通过；次数可用 `ACE_E2E_ATTEMPTS` 调。v3.8 订正了 docstring 里"单次 240s"的旧描述 | S |
| ✅ Q-09 | 死代码清理（BehaviorConstraint 已移除） | `work.py:326 BehaviorConstraint` 仅测试引用、AST 规则无人用;执行层死 import | S |
| ✅ Q-10 | 错误语义与文案解耦 | 靠 message 中文子串判 403;`error_code` 自由字符串散落 ~30 处;状态码无集中常量 | error_code/status 枚举化,文案走 i18n | M |
| ✅ Q-11 | CONTRIBUTING 更新 + demo --check 入 CI + Docker run 示例补 `--project-root` | 已完成(v3.8)：CONTRIBUTING 已改为"总数随平台浮动、不写死数字"；`demo/record_demo.py --check` 进入 CI 的 test job（Py 3.12 单跑）；Docker run 示例补 `--project-root /app/project`。过程中发现演示脚本早就腐化：提示符仍认旧字形 `❯`（v3.6 已改 `▊`）导致用户输入行消失，且录制会吸入录制者的 `.ace_sessions/`（"已恢复上次会话"）、`.ace_kb` 绝对路径与快照数——已改为"临时工作目录 + 临时 HOME"的封闭录制、路径折叠成 `…/`，并重录 `demo/demo.svg`（29 行完整会话，结尾不再被 MAX_LINES 截断） | S |
| ✅ Q-12 | 版本单源 `__version__` + 里程碑 tag/Release | 已落地：`version.py` 是唯一来源，登录/聊天横幅由 `{ver}` 占位符注入（zh/en/ja），`python ai_code.py --version` 可查，`ace_doctor` 报版本，发布流水线用 `-ldflags -X main.serverVersion=…` 把同一版本号注入 Go 执行器；远端已有 `v3.3`~`v3.7` 里程碑 tag（v3.7.0 随 GitHub Release 发布 5 平台执行器产物） | S-M |
| ✅ Q-15 | 模块 docstring 检索词/命名说明 | 已落地（与 R-06 同一批）：`docs/INTERFACES.md §11` 有"历史命名 ↔ 真实职责 ↔ 检索词"索引（`Archive`=记忆 / `Nuwa`=报告 / `work`=诱饵+AST / `guardian`=快照回滚），且每个旧模块 docstring 首行已写清职责；约定"新模块一律 `ace_` 前缀" | S |

## P2 — 结构级(择机)

| ID | 事项 | 说明 | 工作量 |
|---|---|---|---|
| ✅ R-01 | `process_agent_output` 拆状态机 | 已完成：`process_agent_output` **288 → 17 行**（解析 → RoundCtx → `_run_round` → finally 回收），单轮逻辑落在 `_run_round`(52) 与 14 个 `_stage_*`；断言覆盖「阶段可脱离整轮单测 / 顺序守卫 / 轮末回收」。剩余：`_stage_permission` 103 行可再拆（外发闸门 / 项目外确认 / 逐次确认）。见 `docs/design/STRUCT-REFACTOR.md` | L |
| ✅ R-02 | FileTools 拆 FileOps/TerminalView/TerminalExec | 已完成(v3.9)：拆成 `file_common`(共享常量) + `file_ops` + `terminal_view` + `terminal_exec`，`file_tools.py` 只留 25 行兼容层；**25 个方法体经脚本逐字节校验未改**，`registry` 的 handler 名与 `FileTools` 组合一个没动。过程中被测试抓到「脚本只切方法、漏了 3 个类属性」 | M-L |
| ◐ R-03 | 双前端对话引擎合并 | **安全半边完成**(v3.9)：`ace_model.py` 收拢两边重复的纯逻辑（`trim_history` / `error_hint`）。**客户端合并未做**：两者形态（流式+requests+重试 vs urllib 一次性）与输出契约（边流边渲染 vs `🤖 Agent:` 单行）都不同，而现有测试只覆盖 mock 路径——属「改行为」，须单独立项 + 真机验证，卡片里写了推进顺序 | M |
| ✅ R-04 | ai_code.py slash 表驱动 + 会话状态对象 | 已完成(v3.9)：`COMMAND_HANDLERS` 与 `COMMANDS` 分离，`run_command` **125 → 25 行**（前缀补全抽成 `_resolve_command`）；`converse` **234 → 175 行**（`_model_turn` 46 + `_note_round_progress` 25）；3 条表一致性断言 + 2 条语义顺序断言。「会话状态对象」仍未抽（并入 R-03 的推进顺序） | M |
| ✅ R-05 | test_all.py 拆 [N] 段 + runner(`--only/--skip`) | 已完成(v3.9)：35 段各自包进 `if _want(N)`（脚本整体缩进 + 行数守恒校验），新增 `--only/--skip/--upto/--list` 与显式依赖表；`--only 40` **14s → 0.3s**；`[41]` 运行器自检 + 段注册表覆盖断言。**没做的**：把段搬进 `tests/` 模块（依赖声明已够用） | M |
| ✅ R-06 | 命名/检索索引(INTERFACES §11)+ 新模块 ace_ 前缀约定;深层改名不强制 | | 新模块统一 ace_ 前缀;旧模块补导流 docstring | S |

## REL — 对外发布前

- ✅ REL-01 已建 `SECURITY.md` + Issue/PR 模板（`v3.3`）；GitHub topics/主页属仓库设置，需人工在网页维护
- ✅ REL-02 已处理：README 顶部"生产级"表述在二轮重构时对齐；关键数字动态化由 `test_all [39]`（Q-04）自动校验，文档里不再写死
- ⏳ REL-03 真实 Windows 冒烟：`ace.cmd` 与真机对话需人在有控制台的机器上走一遍（本仓库的自动化只覆盖 `--mock` 与无头链路）
- ✅ REL-04 云端 e2e 激活说明已落文档(README secrets 指引 + e2e 头注释);配置 ACE_E2E_* 后 CI 自动启用

## 建议顺序

1. ✅ **P0 全批**（SEC-01→SEC-06）已完成 + 各自回归测试
2. ✅ **P1 快速项全清**（Q-01 ~ Q-15）：2026-09-18 的 v3.8 一轮把最后四项（Q-04/Q-06/Q-07/Q-11）连同 Q-08/Q-12/Q-15 的核对一起收口
3. ✅ **P2 结构重构**：R-01 / R-02 / R-04 / R-05 / R-06 已闭环（v3.9）；**只剩 R-03 的引擎合并**（安全半边已完成，剩下的属"改行为"需真机验证）。详见 `docs/design/STRUCT-REFACTOR.md`
4. ⏳ 剩余：`REL-03` 真机冒烟（`ace.cmd` + 真实终端对话，需人在有控制台的机器上走一遍）
