# ACE v3.46.0 —— 能力路线图批次 -1 ~ 5：工具 42 → 51、三层脊柱 13 项落地

> 面向用户。发布说明索引见 [docs/README.md](../README.md)；完整条目见 [CHANGELOG.md](../../CHANGELOG.md)。

## 一句话

把 `docs/ROADMAP.md` 里**批次 -1 ~ 5** 做完：**工具 42 → 51**、`test_all` **2438 → 2672** 条断言，
并且把驱动/响应/自愈**三层脊柱的 13 项**全部落地。**权限架构一行未动** —— 追的是产品面，不是护城河。

## 能摸到的新东西

| 面 | 你现在能做什么 |
|---|---|
| **git 工具族（8 个）** | `git_status` / `diff` / `log` / `show` / `blame` 只读免确认；`commit_plan` / `fetch` / `merge_tree` 写类逐次确认；**aider 式 auto-commit**（`auto_commit`，**默认关**）+ `/undo` 与既有快照回滚**同一条路** |
| **会话树** | `/tree`（同文件内移动）· `/fork`（从早期消息建新会话）· `/clone`（复制当前分支）**三态严格区分**；**老会话 JSONL 照读不误**；`/compact` 加摘要但**原始条目一条不删** |
| **Skill 系统** | `skills/<name>/SKILL.md` + `scripts/` `references/` `assets/`；**只广告 name+description**（实测广告 7.7 KB vs 正文 226 KB = **29×**），正文按需加载；无效字段**只 warning 不阻塞启动** |
| **agent 预设** | `agents/*.md` 的 per-agent 权限（`permission: {read,edit,webfetch,bash}`）—— **预设只许比全局更严**（S-1 写成断言，复用同一个 `RelaxationForbidden`） |
| **三级预算** | 目标级 / 分类级 / 会话级各自配额，耗尽**报得出是哪一级**（会话失控 ≠ 某个目标卡住）；不配则行为逐字不变 |
| **目标依赖 DAG** | `goal_create/goal_update` 的 `deps`/`blocks`；优先级 = 拓扑序 + 三档（`blocking`/`enabling`/`filler`），**可复现**且带环检测 |

## 用户看不见、但决定了上面这些能不能长期跑得住的东西

- **前缀缓存后两半**：SHA-256 前缀指纹 + **变化强制归因**（空理由当场拒绝）+ **恒等快路径**（指纹不变则跳过 snapshot 与 stringify）+ drift 上报但**原 pin 不丢**。
- **两个账本（同键不同命）**：拒绝账本是**知识**（跨会话、可落盘、出口=提议固化规则）；失败账本是**状态**（本会话、无落盘 API、出口=熔断/降级/上报）。**熔断的是那条路（指纹），不是整个工具。**
- **五级阶梯**：`L0` 重试 → `L1` 换路径 → `L2` 熔断指纹 → `L3` 降级**必声明** → `L4` 停下问人。`MALFORMED`（截断）**永不计入熔断**。
- **上报物料可判定**：L4 的物料必须齐**五要素 + 六要素**、五种偷换各一条被拒；**生产者必须是代码定位符**（H-21 的教训：按错误的原因修，永远修不好）。

## 修掉的一个真问题

推上 CI 后暴露两条**本地永远看不见**的问题（已修）：

1. `[74]` 依赖本机装了可选重依赖 `textual` —— CI 不装，于是 ImportError 被当成**失败**（注释却写着"记跳过"）。现在真跳过。
2. 前端 `EVENT_TYPES` 与 Python 侧 `core/ace_events.EVENT_TYPES` **不同步**（`agent_preset` 只加了 Python 侧）—— 跨语言 parity 测试红。

> 教训：**"本地全绿"不等于"CI 会绿"**。一次是 CI 验了代码，这次是 CI 验了**验证流程本身**。

## 没做的（如实）

- **批次 6**：WP-8 出网与快照 · WP-9 沙箱后端（**C6**：先过 ACC + 领 SEC 编号 + 单独立卡）。
- **WP-10** Rust 核心化（横向）。
- **WP-4 后续切片**：四层持久化 / `/workspace` / `authorize` 接入 / 快照基运行时切换。
- 几条一行接线：WP-6 的 `execution_layer` 接线（补丁已 dry-run 4/4）· `ai_code` 调 `note_tokens` · L4 物料进会话账本 · "确认固化"交互。
