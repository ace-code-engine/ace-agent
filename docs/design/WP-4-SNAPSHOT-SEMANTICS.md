# WP-4 前置 · 快照语义统一（C5）

> 状态：**卡已立**（`ROADMAP` §7.1 **C5** 要求："`WP-4` 开工前必须先立'快照语义统一'卡"）。
> 上级：`docs/ROADMAP.md` §4 WP-4 · §8 **R-2** · `tools/git_ops.py`（WP-2 收尾）。
> **规则 3 已按"如实声明"落地（2026-10-01）**，实现口径见文末「六」。

## 一、要防的是什么

WP-4 引入**工作区四层**：`Task → Workspace → Session → ExecutionProcess`，其中一个
**workspace = 一个 worktree + 一个 branch**。而 ACE **已经有**一套回滚：`core/guardian.py` 的
写前快照 + `/undo` / `/rollback`。

**两套回滚同时存在 = 灾难**（`ROADMAP` §8 **R-2**）：用户按 `/undo` 时，"撤销的是哪一套"没有答案 ——
文件被快照还原了、分支指针还指着后一个提交（或反之），用户看到的状态**谁也没定义过**。

## 二、统一口径（**唯一回滚入口**）

| 层 | 角色 | 谁负责 |
|---|---|---|
| **文件内容** | 一次写操作**前**的字节 | **`guardian` 快照**（不变） |
| **工作区隔离** | 哪份文件在哪个 worktree / 哪个 branch | **worktree**（隔离，不是回滚） |
| **长期历史** | 提交图 | **git**（`git_ops` / auto-commit，见 WP-2 收尾） |
| **回滚入口** | `/undo` / `/rollback` | **只有一个** —— 见下 |

**规则（三条，缺一不可）**：

1. **回滚 = 快照还原文件 + （必要时）指针同步**，**不是**在 worktree 上再做一次"另类回滚"。
   这与 WP-2 收尾时落地的 `/undo` 完全同构：`guardian.rollback()` 还原文件；只有当那次写**已被提交**
   才再 `git reset --mixed` 把分支指针同步回同一个"写前"时刻。**worktree 里同一套**。
2. **worktree 只做隔离，不做回滚**：删 worktree（`worktree_deleted`）**不等于**回滚 ——
   它是"这个工作区不再用了"，**语义上必须与 `/undo` 分开**（两个动词、两条状态、两句文案）。
3. **切换 worktree ≠ 切快照基**：进入另一个 worktree 时，guardian 的快照基**跟着换到那个 worktree 根**
   （`allowedRoots` 之内），否则 `rollback` 会把 A 工作区的文件"还原"到 B 工作区的树上。

## 三、`allowedRoots`（照 orca 的硬一层）

- agent 的读写被限制在**注册过的 worktree 根**之内；`allowedRoots` 是那份注册表的唯一来源。
- 与既有闸门的关系：它是 `confine_files` / `sensitive.py` 的**上位约束**（先问"这个根注册过吗"，
  再问"路径越界吗"）—— **不是第二套**越界判定。
- 拿不到 worktree 注册表（非 git / 未启用四层）→ **如实声明并回落到当前单工作区语义**，**不静默**（HL-03②）。

## 四、验收（WP-4 的实现必须带）

- **单回滚入口断言**：任何"撤销"动作都只经 `guardian` 快照那条路；worktree 删除**不**触发文件还原。
- **跨 worktree 不串**：切到另一个 worktree 后 `/undo` 还原的是**那个** worktree 的写前字节。
- **`allowedRoots` 之外的路径** → 拒绝（不是静默放行）。
- **无 worktree 支持时**：如实声明 + 单工作区语义（行为与本卡之前逐字一致）。

## 五、边界（不做什么）

- 不改 `guardian` 的快照格式（它是既有契约，被 `test_all` 钉住）。
- 不引入第二套"回滚状态机"；`/undo` 与 `/rollback <id>` 的语义**不在本卡改**。
- worktree 的**创建/删除**由 WP-4 实现；本卡只定"它与回滚的边界"。

## 六、规则 3 的落地口径（2026-10-01）

> 先把规则 3 的标题改对：原文写的是"切换 worktree **≠** 切快照基"，正文却说"快照基**跟着换到**
> 那个 worktree 根"—— 标题与正文相反。以正文为准：**切工作区 ⇒ 换快照基**。

**ACE 里"换快照基"就是"以那个根重开会话"，不是进程内改 `project_root`。**

按 `--project-root <worktree>` 重开会话时，`Guardian(str(project_root))` 自然就以该 worktree 为基，
`_collect_files()` 走的是它、`rollback()` 还原的是它、`anchor_dir_for(project_root)` 按根派生
**各自独立的签名锚**（每个根一把密钥，互不干扰）—— 规则 3 的两条要求（基正确、跨根不串）
**由构造方式直接满足**，没有需要"运行时切换"的东西。

**为什么不做进程内切换**：`project_root` 是构造期不变量，被 `executor` / `guardian` / `archive` /
`sessionlog` / MCP 根 / 技能根 / 权限规则根 / `.ace/workspaces.json` 自身的路径**同时**持有。
逐处改是几十个点，漏一处就得到本卡开头那句"用户看到的状态谁也没定义过"。更硬的一点：
若给每个 worktree 各建一个 `Guardian` 又共用/混用一个 store，`rollback(snap_id)` 会用**当前实例**的
`project_root` 去解析快照里的相对路径 —— 那恰恰就是"把 A 工作区的文件还原到 B 工作区的树上"。
**半途实现严格劣于不实现**，所以这条明确不做。

**做了的是"如实声明"这一半**（缺它，规则 3 就是一句没人验得了的口号）：

| 事实 | 此前 | 现在 |
|---|---|---|
| 快照基盖不住本轮要动的路径 | 一行 stderr，`snapshot_state` 仍写 `created` | `snapshot_state="partial"` + `RoundCtx.snapshot_outside`，**走结果**，CI/无头看得见 |
| 某个工作区到底有没有回滚 | 没有任何地方说 | `/workspace` 逐行打「撤销覆盖：是/否」；「否」时给出路：`--project-root <该根>` 重开会话 |

放行与否**一个字没改**：项目外绝对路径写是既有产品意图（SEC-009 之后的口径，"放到桌面"），
此前就是"照写 + stderr 提醒"。本切片只把同一个数从 stderr 挪进结果 —— 想让绝对路径写也
受 `allowedRoots` / 快照基约束，是**收紧既有已测行为**的独立决策，不塞进这里。

判据不分叉：`snapshot_outside` 直接复用 `Guardian._relative_targets()`（H-10 已处理 `..`、
8.3 短名、大小写、尾点，且**相对路径起点是项目根而非 cwd**）。第一版自己写了一遍，当场把
项目内的写误判成"盖不住" —— 被 `[83]` 那条"基内的写仍是 created"抓住。
