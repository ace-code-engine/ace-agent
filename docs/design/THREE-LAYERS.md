# 三层脊柱设计卡 —— 驱动层 / 响应层 / 自愈层

> 编号：`DL-`（驱动）/ `RL-`（响应）/ `HL-`（自愈）／`LDG-`（共用账本）
> 上级：`docs/ROADMAP.md` §0.5。 状态：**设计；`RL-01`（结果信封）、`RL-02`（拒绝六分类）、`DL-01`（目标可判定的 acceptance）已实施**（见 **§9**），其余未开工。
> 缘起：立项走到"功能模块（§3.1）+ 工作面（§4）"之后，真正没设计过的只剩这三段 ——
> **执行层已经很硬，但"上面怎么指挥、中间怎么回报、撞墙了怎么办"从来没有设计。**

---

## 0. 现状：三层都有实测证据，但都不成体系

| 层 | 现有的东西 | 实测落点 | 缺什么 |
|---|---|---|---|
| **驱动** | 目标（`goal_create/update/status`）· 待办（`todo_write`）· 思考强度五档 + `ultrathink` 逃生门 · L1 意图识别 | `tools/goal_tools.py` 266 · `core/ace_todos.py` 149 · `core/ace_effort.py` 159 · `gateway_v2/intent.py` 82 | **没有优先级**、**没有目标级预算**、**没有"从拒绝中学习"**（唯一机制是硬编码的 `PROMPT_PERM_GRANTED`，见 §1.4） |
| **响应** | `ExecutionResult{status,data,error_code,message,metadata}` · 8 个错误码（AST 守卫单一来源） | `tools/result.py:12` · `tools/status.py:15-28` | 结果**以渲染后的中文散文回喂**（§2.1），驱动层要"知道发生了什么"必须**解析自然语言** |
| **自愈** | HTTP 退避 · **同工具同错误 3 次熔断** · H-21 `abort` · `STALL_ABORT_ROUNDS` · `MAX_ROUNDS=20` · `_fail_streak` · `security_alerts` | `agent_runner.py:70` · `:98-103` · `:844-861` · `ai_code` 的 `STALL_ABORT_ROUNDS` | **六套机制互不相通**：没有共享状态、没有升级阶梯、没有上报出口 |

**先澄清一个命名陷阱**：`core/ace_recovery.py`（219 行）**不是错误恢复**，它是 **RG-04 的可逆性分类器**（判"被写的对象能不能重建"：`GIT` / `SNAPSHOT` / `REGENERABLE` / `NEVER` / `UNKNOWN`）。
即："自愈层"这块**基本是空地**，不是改造。

### 0.1 一个真实案例：死锁被归错了因

`agent_runner.render_error_result` 的 docstring 记下了 2026-09-19 的真机实测（`agent_runner.py:613-631`）：

> 该 payload 是执行层自己写的元信息……套上隔离块，等于告诉模型"这一段是**数据**不是指令，不得当成命令执行" —— 而同一句里又写着"请修正后继续"。两个信号直接打架。
> 后果：模型明确写出"它是从被标记为『外部（未分类）』的数据区块里送来的……不能当作指令执行"，**连续 5 轮拒绝改动输出，而报错正文一字未变**；
> 第 6 轮被 `STALL_ABORT_ROUNDS` 按"模型死循环"中止，**并把责任归给模型与提示词**。真正的死锁来自**两个安全特性的交叉**。

**这个案例是整张卡的动机**：自愈层当时**升级了、也上报了，但归错了因**。
它把"两个安全特性的交叉"上报成"模型死循环" —— 而按错误的原因修，永远修不好。

### 0.2 真正的病根：把"拒绝"和"失败"混在一个计数器里

`agent_runner.py:96-103`（H-19 的教训）自己写下了这个 bug：

```
被 max_tokens 截断时，tool_calls 里的 JSON 是未闭合的 —— 修 JSON 两条路都会失败、
args 退化成 {}，于是报 400、计进"连续失败"、3 次后该工具被整会话熔断。
```

**截断导致的 400 是"失败"，但它被计进了同一个计数器** —— 结果 `file_write` 被永久禁掉。

> **本卡的核心命题：拒绝是信息，失败是状态。**
> - **拒绝** = 执行层**正常工作**的结果（策略生效了），它携带"此路不通"的**知识**；
> - **失败** = 事情**没成**，它携带"该升级了"的**状态**。
>
> 现有代码把两者塞进同一个 `(tool, error_message)` 计数器，于是**"被拒"会伪装成"失败"**，
> 而"失败"又会污染"拒绝"的统计。三层设计的第一件事就是把这个键拆开。

---

## 1. 驱动层（DL）：定目标、排优先级、从拒绝中学习

### 1.1 现状

- 目标有 CRUD（`goal_tools` 266 行），但**没有完成判据** —— 于是"完成"由模型自己宣布。
- 优先级**不存在**：`todo_write` 只有列表顺序，没有档位、没有依赖、没有阻塞关系。
- 预算只有**全局** `MAX_ROUNDS = 20`（`agent_runner.py:70`），没有目标级配额。
- 学习**不存在**：唯一机制是 `PROMPT_PERM_GRANTED = "用户已授权，请重试刚才被拦截的工具。"`（`:649`）——
  这是在**鼓励原样重发**，与"从拒绝中学习"正好相反。

### 1.2 DL-01 · 目标必须**可判定**

每个目标必须带 **acceptance（怎么算完成）**，否则无法排队、无法判完成、无法上报。

```
Goal {
  id, statement,            # 要做什么
  acceptance,               # 怎么算完成 —— 可执行判据，不是形容词（落点：§6 ACC-02 指标语义契约）
  deps: [goal_id],          # 依赖 DAG（参照 vibe-kanban `parent_workspace_id`）
  blocks: [goal_id],        # 挡着谁
  budget: { rounds, tokens, refusals },   # 目标级预算（§3.6）
  state: pending | active | blocked_on_auth | blocked_on_human | done | abandoned
}
```

**`blocked_on_auth` 与 `blocked_on_human` 必须分开**（§2.3 的 `AUTH_PENDING` 与 L4 上报）——
前者等一个授权，后者等你重新决定目标；混在一起就会让"等人授权"看起来像"任务失败"。

> **明确拒绝**：让模型自己声明"我完成了"。判据必须是**外部可复核**的（测试通过 / 文件存在 / 断言成立）。

### 1.3 DL-02 · 优先级 = 依赖 DAG 拓扑序 + 三档

| 档 | 判据 | 排序 |
|---|---|---|
| `blocking` | 挡着别的目标（`blocks` 非空且下游未完成） | 最前 |
| `enabling` | 解锁别的目标 | 次之 |
| `filler` | 无下游依赖 | 最后 |

**明确拒绝**："按模型觉得重要排" —— 那是**不可复现**的，同一输入两次运行会给出不同顺序。

### 1.4 DL-03 · **拒绝账本（Refusal Ledger）** —— 从拒绝中学习

每次拒绝产生一条**结构化**记录（不是一句散文）：

```
Refusal {
  goal_id,
  tool,
  fingerprint,      # 关键参数归一化后的哈希 —— 同一意图的不同写法 → 同一指纹（关键！）
  class,            # §2.3 的六类之一
  count, first_at, last_at,
  hint,             # 执行层给的替代路径（不是只有"不行"）
}
```

学习动作**四种，按证据强度升序**：

| # | 触发 | 动作 | 现有可复用的东西 |
|---|---|---|---|
| 1 | 同 `fingerprint` + 同 `class` 已拒 | **不再原样重发** —— 回喂时明确"这条路已关" | 无（**现在是反例**：`PROMPT_PERM_GRANTED` 在鼓励重发） |
| 2 | 同上 | **给替代路径**：带上 `hint.alternatives` 与 `hint.missing` | 无 |
| 3 | 同 `fingerprint` 被拒 **N 次** | **提议固化成规则** | **已有**：`core/ace_rules.py` 278 的 3 scope + 一键固化 —— 只需接线 |
| 4 | 同 `class` **跨目标**频繁出现 | **上报给人**：这说明**规则本身有问题**（不是模型有问题） | 无 |

**第 4 条是这张卡最值钱的一条**：它把 §0.1 那个"归错因"的失败模式，变成一个**有出口的设计** ——
"同一类拒绝在多个目标上反复出现"必然指向**规则**，而不是模型。

### 1.5 DL-04 · 约束：学习只能让人更严，不能自动放宽

**硬约束（S-1）**：拒绝账本的学习结果**只允许**产出两种东西 ——
① 更严的规则（提议固化，**由人确认**）；② 更会绕的路径（换实现，不改权限）。
**绝不允许**任何形式的老化自动放宽（例如"被拒 3 次后自动批准"）。**放宽只能是人的动作。**

---

## 2. 响应层（RL）：把执行结果（含拒绝信号）高效回传驱动层

### 2.1 现状：结果以**渲染后的中文散文**回喂

```
PROMPT_TOOL_RESULT  = "工具执行结果：\n{rendered}\n请根据结果继续…"
PROMPT_ERROR_RETRY  = "执行层返回了错误，请修正后继续：\n{rendered}\n注意：必须严格按…格式输出。"
```
（`agent_runner.py:652-655`，`rendered` 来自 `render_tool_result` / `render_error_result`）

**问题**：驱动层要"知道发生了什么"必须**解析自然语言**。而 `tools/status.py` 明明已经有 8 个结构化错误码、
`ExecutionResult` 明明有 `status` / `error_code` / `metadata` —— **这些结构化信息在回喂时被丢掉了**。

### 2.2 RL-01 · 结果信封：**结构给机器，渲染给人**

```
ExecutionResult {
  # ── 机器通道（驱动层/自愈层读这个）──
  outcome:     success | denied | failed | partial | deferred          # 闭集
  class:       RefusalClass | None        # 仅 denied/partial（§2.3）
  retryable:   bool                       # 驱动层唯一必答的问题
  fingerprint: str                        # 供两个账本（§4）
  hint:        { alternatives: [...], missing: [...] }
  budget:      { rounds_used, tokens_used, refusals_used }
  # ── 人通道（UI / 模型读这个）──
  status, error_code, message, display
}
```

`outcome` 是**闭集**，与 `tools/status.py` 同一套 AST 守卫纪律（新增值必须先登记，散落字面量被拒）。

### 2.3 RL-02 · **拒绝分类（Refusal Taxonomy）** —— 本卡最重要的产物

现有 `status` 的 5 个值里 **3 个都是"拒绝"类**（`guard_violation` / `bait_triggered` / `permission_denied`），
但对驱动层它们是**同一种信号** —— 于是驱动层只能一律"重试"。

必须**正交拆分**，并给每一类**唯一**的驱动层处置：

| 类 | 触发 | **驱动层唯一动作** | 依据 |
|---|---|---|---|
| `POLICY` | 策略 / 黑名单拒绝 | **换路径**，别重试 | `core/ace_execpolicy.py` 439 |
| `BOUNDARY` | 越界 / 敏感目标 / 不可逆 | **换路径**；同指纹再犯 → 提议固化（DL-03 第 3 条） | `core/sensitive.py`、`core/ace_recovery.py` |
| `AUTH_PENDING` | 需要人授权 | **停下等人**（**不是失败**） | `PERMISSION_REQUEST` 流程 |
| `CAPABILITY` | 环境/能力缺失（503 沙箱不可用、501 未实现） | **降级并声明，或上报** | `tools/status.py:10` 的 503 语义 |
| `TRANSIENT` | 超时 / 抖动 / 429 | **退避重试** | `core/ace_http.py` 已实现 |
| `MALFORMED` | 输出畸形 / 截断 | **永不计入熔断**，重新生成 | `agent_runner.py:96-103`（H-19） |

**这六行就是"响应层 → 驱动层"的全部契约。** 每类只有一个动作，互不重叠 ——
现有代码已经用血证踩出其中两条（H-19 截断不许计熔断、H-21 畸形不许重复回喂），但**没有分类就没有统一的处置表**。

### 2.4 RL-03 · 三段式回传（治"回喂越来越长"）

现在每条结果都**全文**渲染进 prompt —— 这同时造成两件事：吃前缀（与 `WP-3` 冲突）、
以及 H-19 那类"回喂变长 → 更容易被截断 → 更要回喂"的**正反馈**。

| 段 | 进不进上下文 | 内容 |
|---|---|---|
| **摘要行** | **必进** | 一行结构化：`[denied] file_write · BOUNDARY · fp=a3f2 · 可换路径` |
| **证据块** | **按需**（模型显式索取） | 全文，参照 Codewhale 的 `retrieve_tool_result` 延迟取回 |
| **指纹压缩** | 必进 | 同 `fingerprint` + 同 `class` 重复出现时压成 `(同上，第 N 次)`，**不长出来** |

### 2.5 RL-04 · 两条已血证的回喂纪律（**不许回退**）

1. **执行层自己的报错不套外部内容隔离块**（`agent_runner.py:613-631`）—— 套了会让模型按约定拒绝纠错，形成死锁。
   若某条错误路径必须携带外部正文，**那段正文单独走** `wrap_untrusted`，**不要**把整个 payload 包起来。
2. **截断证据必须与"参数写错"分开回喂**（H-19）—— 两者原因完全不同，混在一起模型永远修不好。

> **已在断言里钉住（2026-09-30 复核，见 §9.6）**：纪律 ① = `test_all`「错误回喂不带外部内容定界块」
> （含对照组「工具结果仍然隔离」，SEC-011 没被顺手削弱）；纪律 ② =「H-19 `finish_reason=length`
> 抛 `TruncatedOutput`（不再退化成 `args={}` → 400 → 连续失败熔断）」。

---

## 3. 自愈层（HL）：连续失败时降级或上报

### 3.1 现状：**六套互不相通的机制**

| 机制 | 落点 | 键 | 动作 |
|---|---|---|---|
| HTTP 退避 | `core/ace_http.py` | 传输 | 429/5xx/抖动重试，`retry_notice` 可见 |
| 工具熔断 | 执行层 | `(tool, error_message)` | **3 次 → 整会话禁掉该工具** |
| H-21 `abort` | 执行层 → `agent_runner.py:848` | 同段畸形输出 | 中止 |
| `STALL_ABORT_ROUNDS` | `ai_code` | 连续无进展轮数 | 中止，**归因给模型/提示词**（§0.1 的错因） |
| `MAX_ROUNDS = 20` | `agent_runner.py:70` | 全局轮数 | 中止 |
| `security_alerts` | `agent_runner.py:851-856` | 安全拦截次数 | **只告警，不动作** |

**六套机制没有共享状态、没有升级阶梯、没有上报出口。** 而且键不一致（`(tool,error)` / 输出段 / 轮数 / 次数），
所以它们**不可能互相知道对方已经数到几了**。

### 3.2 HL-01 · 统一失败账本（Failure Ledger）

把键统一为 `(goal_id, fingerprint, class)`：

- **现有键太粗**：`(tool, error_message)` 会让 `file_write` 的**两种不同 403** 互相压制、一起熔断。
- 改成 `(fingerprint, class)` 后，熔断的是**那条路**，不是**整个工具**。
- 与 DL-03 的拒绝账本**同一个键空间**，但**寿命不同**（§4）。

### 3.3 HL-02 · 五级升级阶梯

| 级 | 触发 | 动作 | 可见性 |
|---|---|---|---|
| **HL-L0 重试** | `TRANSIENT` | 退避重试 | stderr 一行（现有 `retry_notice`） |
| **HL-L1 换路径** | `POLICY`/`BOUNDARY` 首次 | 回传 `hint.alternatives` | 摘要行 |
| **HL-L2 熔断** | 同 `fingerprint`+`class` **第 3 次** | **禁掉这个指纹**（不是整个工具） | 明确告知模型"这条路已关" |
| **HL-L3 降级** | 同工具第 5 次 / `CAPABILITY` | **走降级路径并声明**（现有先例：`ToolsUnsupported` → 降级文本协议，`agent_runner.py:504-509`） | **必须声明**，不许静默 |
| **HL-L4 上报** | 同 `class` 跨目标 ≥ N / **任一级预算耗尽** | **停下来问人**，附**上报物料**（§3.5） | 阻塞式，等回答 |

### 3.4 HL-03 · 三条硬规则（全部来自现有 bug，必须写成契约）

1. **`MALFORMED` 永不计入熔断** —— H-19 的血证（`agent_runner.py:96-103`）。
2. **降级必须声明，不许静默回退** —— `tools/status.py:10` 已经把 503 定义为"沙箱档不可用（**不静默回退**）"，扩到全部降级路径。
3. **降级方向只朝"更严"** —— 与 `ROADMAP` WP-9 同一条：CubeSandbox 不可达时降级到**拒绝**，**绝不**降级到本地无边界执行。

### 3.5 HL-04 · 上报物料必须**可判定**（接 §6 ACC 门槛）

L4 上报时给人看的**必须能被复核**，**不允许**只上报"失败了 8 次"：

- **指标语义契约**（五要素）：`Metric` / `Anchor` / `Population` / `Excludes` / **`Reads as`**
- **缺陷可达性契约**（六要素）：`Constructed state` / **`Production producer`** / `Transition path` / `Persistence boundary` / `Authority` / `Observed`
- **五种偷换**：unknown→true、latest→all、accepted→closed、attempted→judged、**未评估→false**

> 这正是 §0.1 那个案例缺的东西：它上报了"模型死循环"，但没有给"**Production producer**"——
> 而这个缺陷真正的生产者在**两个安全特性的交叉处**。

### 3.6 HL-05 · 三级预算（替换全局 `MAX_ROUNDS`）

| 级 | 配额 | 耗尽时 |
|---|---|---|
| **目标级** | 该目标的 `budget.{rounds,tokens,refusals}` | L4 上报（这个目标做不完） |
| **分类级** | 该 `class` 的总拒绝次数上限 | 提议固化规则（DL-03 第 3 条） |
| **会话级** | 总 token / 总轮数 | L4 上报并**结束** |

**明确拒绝**：只靠全局轮数上限。它今天会把"一个目标卡住"和"整个会话失控"报成同一件事。

---

## 4. 三层共用的两个账本（本卡的架构核心）

| | **拒绝账本**（DL-03） | **失败账本**（HL-01） |
|---|---|---|
| 回答 | "这个意图是不是**此路不通**" | "现在该**升到哪一级**" |
| 键 | `(goal_id, fingerprint, class)` | `(goal_id, fingerprint, class)`（**同一键空间**） |
| 寿命 | **长期 / 跨会话** —— 它是**知识**（该固化进 `/rules`） | **短期 / 本会话** —— 它是**状态**（会话结束即清） |
| 读者 | 驱动层 | 自愈层 |
| 出口 | 提议固化规则 / 上报规则缺陷 | 熔断 / 降级 / 上报 |

**为什么必须分开**：它们的**时效不同**。
把"被拒过"当状态会丢掉知识（每次重学）；把"失败过"当知识会污染规则（一次截断就永久禁掉一个工具 —— 这正是 H-19 的 bug）。
两者**同键不同命**，是三层设计的枢纽。

---

## 5. 非目标

| ID | 不做 | 理由 |
|---|---|---|
| **NG-D1** | 让模型自己决定"什么算完成" | 判据必须外部可复核；否则"完成"不可信，支柱 D 塌 |
| **NG-D2** | 自动放宽权限（拒绝 N 次后自动批准） | 违反 S-1 与 DL-04；**放宽只能是人的动作** |
| **NG-R1** | 把 `status` / `error_code` 推倒重来 | 它们是 AST 守卫的单一来源（Q-10 的成果），只做**正交扩展** |
| **NG-R2** | 用自然语言解析来驱动决策 | 那正是现在的问题；结构必须走 §2.2 信封 |
| **NG-H1** | 无限重试或无限轮数 | 本卡存在的理由就是"不无限撞墙" |
| **NG-H2** | 静默降级 | HL-03 第 2 条 |

---

## 6. 验收

| # | 断言 | 说明 |
|---|---|---|
| **A1** | **六类拒绝各有唯一动作**，且可用一张表穷举 | 新增拒绝路径必须归类，否则测试红 |
| **A2** | **`MALFORMED` 不计入熔断**（回归 H-19） | 构造 `finish_reason=length` → 断言该工具**未**熔断 |
| **A3** | **同指纹第 3 次熔断的是"指纹"不是"工具"** | 构造同工具两种不同 403 → 断言两种互不压制 |
| **A4** | **降级必声明**（无静默回退） | 构造 `CAPABILITY` → 断言输出里含降级声明 |
| **A5** | **拒绝账本跨会话存活，失败账本会话结束即清** | 键相同、寿命不同的直接验证 |
| **A6** | **L4 上报物料满足 ACC 四要素** | 缺 `Production producer` 即红 |
| **A7** | **回喂不因重复拒绝而变长** | 同指纹重复 N 次 → 断言 prompt 长度**不**单调增长 |
| **A8** | **§2.5 两条纪律不许回退** | 断言执行层报错 payload **不含**隔离块 |

---

## 7. 与 `docs/ROADMAP.md` 工作面的关系

| 本卡 | 关系 |
|---|---|
| **DL-01 目标可判定** | 依赖 `ROADMAP` §6 **ACC-02**（指标语义契约） |
| **DL-02 优先级** | 与 **WP-4**（工作区四层）共用依赖 DAG |
| **DL-03 拒绝账本** | 接线到已有的 `core/ace_rules.py`；**WP-6**（per-agent 权限）是它的消费方 |
| **RL-01 结果信封** | 与 **WP-0**（事件协议）同源：**给机器的结构与给前端的事件是同一份数据** |
| **RL-03 三段式回传** | 直接服务 **WP-3**（前缀缓存 / 工具面伸缩） |
| **HL-01 统一账本** | 与 **`ROADMAP`** 的 HMAC 链式台账**共用写入路径**（审计时同一份序列） |
| **HL-04 上报物料** | 就是 `ROADMAP` §6 **ACC-01~04** 的消费场景 |
| **三层全部** | 服务于 `ROADMAP` §0 的四支柱：DL→**C**、RL→**B/D**、HL→**A/C** |

---

## 8. 风险

| # | 风险 | 缓解 |
|---|---|---|
| **TH-R1** | 拒绝分类（RL-02）如果**不穷举**，未归类路径会落回"一律重试" | A1 用测试强制：新增拒绝路径必须归类 |
| **TH-R2** | 两个账本"同键不同命"容易被实现成一个（省事） | A5 直接验证时效差异；键相同是**巧合**，寿命不同是**设计** |
| **TH-R3** | DL-03 第 3 条自动提议固化规则 → 可能**把误报固化成规则** | 固化**必须人确认**（DL-04）；提议带完整证据 |
| **TH-R4** | 五级阶梯在简单任务上**过度工程** | L0/L1 必须零额外开销（现有退避路径不变），阶梯只在 L2+ 生效 |
| **TH-R5** | 改动 `ExecutionResult` 会波及 **4 个前端** | 只做**正交新增**字段（`outcome`/`class`/`retryable`/`hint`/`fingerprint`），不动 `status`/`error_code`；配合 **WP-0** |

---

## 9. 实施记录：`RL-01` 结果信封（2026-09-27）

> 依据本卡 **§2.2** 的信封定义。与 `WP-0` **同批**（`ROADMAP` §7.1 **C1**：
> `RL-01` 与前端收敛是"同一份数据的两端"，拆开做就等于让新字段**漏给四个外壳一次**）。

### 9.1 交付物

| 文件 | 改动 |
|---|---|
| `tools/status.py` | **`outcome` 闭集**（`OUTCOMES` = `success` / `denied` / `failed` / `partial` / `deferred`）+ **`outcome_for(status, error_code)`** —— "拒绝 vs 失败"的**唯一判定处**（登记纪律与 `ERROR_CODES` 同源） |
| `tools/result.py` | 信封的**五个正交字段**（`outcome` / `refusal_class` / `retryable` / `fingerprint` / `hint`）+ `__post_init__` **自动补 `outcome`** |
| `ai_code.py` | **外发事件** `tool_result` 带 `outcome`（外壳与驱动层读的那条） |
| `cli/ace_sessionlog.py` + `execution_layer.py` | **账本** `tool/result` 带 `outcome`（拿到才写，空串不落盘） |
| `core/ace_events.py` + `frontend/src/protocol/types.ts` | 契约表与 TS 类型**登记** `outcome` |

### 9.2 两个设计决定（都是动手时才看得见的）

1. **推导放 `__post_init__`，而不是让 250+ 个构造点各填一次**：`ExecutionResult(` 在 `tools/` 下有
   **250+ 处**，逐个改既改不完、也一定会漏。放这里 ⇒ **每个结果都自动带上机器通道**，
   而调用方仍可显式覆盖（显式值优先）。
2. **`class` 改名为 `refusal_class`**：`class` 是 **Python 关键字**，本卡 §2.2 的字段名不能照抄。

### 9.3 红 → 绿：**撤掉接线，两条端到端当场红**

这一包是"实现在前"，于是补了一次**接线演示**（撤掉 `execution_layer` 传 `outcome=` 那一行）：

- **6 条单元断言全绿**（规则在、也算得对）；
- **两条端到端红**，而且 dump 出来的两条事件**形状完全一样**：

  `{'tool': 'file_read', 'status': 'error', 'message': '路径越界…'}` —— 403
  `{'tool': 'file_read', 'status': 'error', 'message': '文件不存在: …'}` —— 404

  **在账本里分不出来。** 这正是本卡 §0.2 记的病根，现在它是**可见**的了。

> 又一个"纯规则一致 ≠ 接上了"的例子（与 `WP-0` 的 R-6 同源）：
> **只有端到端断言能证明那个字段真的流到了账本里。**

### 9.4 边界（`RL-01` 没做的）

- **`refusal_class` / `retryable` 只留位、不填值** —— 它们的判据是 **`RL-02` 的六分类（批次 1）** ⇒ ✅ 已由 RL-02 填上（见 §9.5）；
- **`budget` 不在信封里**：它是**目标**的属性（`HL-05` 三级预算），不是一次工具调用的属性；
- **`partial` 尚无生产者**（`RL-03` 三段式回传时才有）；
- **前端还没有消费者**：`types.ts` 已登记，但 `store` / 组件还没用 `outcome`
  （"拒绝与失败分开展示"属 `WP-0` 的活）——《边界》一节的意义就在这句：**字段到了，用途还没到。**

### 9.5 实施记录：`RL-02` 拒绝六分类（2026-09-30）

> 依据 §2.3。RL-01 的信封把 `refusal_class`/`retryable` 留空了 —— RL-02 填上判据。

| 文件 | 改动 |
|---|---|
| `tools/status.py` | **`REFUSAL_CLASSES` 六分类**（`POLICY`/`BOUNDARY`/`AUTH_PENDING`/`CAPABILITY`/`TRANSIENT`/`MALFORMED`）+ **`classify_refusal(status, error_code)`**（唯一判定处，与 `outcome_for` 同一条登记纪律）+ **`retryable_for(class)`**（只有 `TRANSIENT`/`MALFORMED` 为真） |
| `tools/result.py` | `__post_init__` 自动填 `refusal_class`（空时按 `classify_refusal` 推导）+ `retryable`（由类派生）—— 250+ 构造点一个不改 |

**映射**（`classify_refusal`，13 条逐条钉在 `test_all [36]`）：

| 类 | 触发 | `retryable` |
|---|---|---|
| `POLICY` | `GUARD_VIOLATION`/`TOOL_BANNED`/`BAIT_TRIGGERED`/`AST_FAILED`/`HOOK_BLOCKED` | False（换路径） |
| `BOUNDARY` | `error_code=403` | False（换路径） |
| `AUTH_PENDING` | `PERMISSION_REQUEST` | False（停下等人） |
| `CAPABILITY` | `503`/`501` | False（降级并声明） |
| `TRANSIENT` | `504` | **True**（退避重试） |
| `MALFORMED` | `FORMAT_ERROR` | **True**（重新生成） |

**边界（如实）**：① 认不出的**失败**（400/404/409/500）落 `""`（无更细的类，保守不自动重试）——
TH-R1 的"穷举"钉的是**拒绝**路径（3 类覆盖全部 denied），不是全部失败；
② 挂起（`PLAN_*`）落 `""`（停下等人，但不是"拒绝类"）；
③ `refusal_class`/`retryable` 仍**没流到账本**（`tool/result` 事件只带 `outcome`）—— 那是 **DL-03 拒绝账本**的活（§1.4）。

### 9.6 实施记录：`RL-04` 两条回喂纪律（2026-09-30）—— 确认已钉，不改代码

§2.5 的两条纪律是 **H-19/H-21 血证出来的既有实现**，RL-04 的活不是"补代码"而是
**确认它们已被断言钉住、可追溯**：

| 纪律 | 已钉在 | 内容 |
|---|---|---|
| ① 执行层报错不套隔离块 | `test_all`「错误回喂不带外部内容定界块」+ 对照组「工具结果仍然隔离」 | `render_error_result` 输出无 `UNTRUSTED_BEGIN`；`render_tool_result` 有（SEC-011 没被顺手削弱） |
| ② 截断证据与"参数写错"分开 | `test_all`「H-19 `finish_reason=length` 抛 `TruncatedOutput`」 | 截断抛独立异常（不再退化成 `args={}` → 400 → 熔断），且报错点名 `max_tokens` |

**结论**：RL-04 由**既有断言**满足（两条都在全量 `test_all` 里长绿）。本包只补可追溯性，
没有新代码 —— 这正是"已血证"的意思：血证已经在测试里了。

### 9.7 实施记录：`DL-01` 目标可判定的 acceptance（2026-09-30）

> 依据 §1.2。每个目标必须带 `acceptance`（怎么算完成的可执行判据），不能靠模型自己声明"我完成了"。

| 文件 | 改动 |
|---|---|
| `tools/goal_tools.py` | `Goal.acceptance` 字段；`_acceptance_error()`（必填 + 长度下限 + 形容词黑名单「完成/搞定/ok/done…」）；`create(..., acceptance=)` 校验，缺/形容词 → `GOAL_BAD_ACCEPTANCE` |
| `tools/registry.py` | `goal_create` 参数表加 `acceptance`（与 `objective` 同为必填）+ 描述/示例 |
| `prompts/`（v7/v8/tools） | `goal_create` 示例同步带 `acceptance`；`tools.md` 加"必填 acceptance"一句 |

**先红后绿**：`test_all [25]` 3 条（带可判定 acceptance → 成功且回传 · 缺 → `GOAL_BAD_ACCEPTANCE` ·
形容词 → `GOAL_BAD_ACCEPTANCE`）+ 4 处直接 `GoalStore.create()` 补传 acceptance。

**边界（如实）**：① 可判定性靠"必填 + 黑名单"这**第一道**，不是完整验证器（会绕弯子的形容词拦不住）——
真正的可判定性靠"外部可复核"这条纪律；② `blocked_on_auth`/`blocked_on_human` **还没拆成独立 state**
（现在仍用 `blocked` + `blocked_reason_code` 区分）—— 这是 DL-01 剩余部分，牵状态机；
③ `deps`/`blocks`（依赖 DAG）是 **DL-02**、`budget` 是 **HL-05**，不在本包；④ `/goal` 显示还没带 acceptance。

### 9.8 实施记录：`DL-01` 的 blocked 正交拆分（2026-09-30）

> §1.2 的剩余部分。§9.7 只做了 `acceptance`；这一包把 `blocked` 拆成两个独立 phase。

| 文件 | 改动 |
|---|---|
| `tools/goal_tools.py` | `PHASE_BLOCKED_ON_AUTH` / `PHASE_BLOCKED_ON_HUMAN` 进 `PHASES`；`AUTH_BLOCKED_CODES={permission_blocked}`（呼应 RL-02 `AUTH_PENDING`）；`_apply_phase` 新增 active → blocked_on_auth（要授权类机器 code）/ active → blocked_on_human（要人类可读 message），两者**互不直接转换**、均 `armed=False`；active 恢复来源扩为含两个新 phase，恢复即清 reason |

**兼容决定（重要）**：`blocked` **原样保留、语义零改动** —— 不静默改路由（`blocked + permission_blocked`
仍存 `phase="blocked"`，不自动升级成 blocked_on_auth）。理由：`test_all [25]` 的既有断言直接钉住
`phase == "blocked"` 的存储值，自动改路由会让既有调用方拿到的 snapshot 突然变 phase；"别静默改语义"
是硬约束。调用方要拆分就**显式**用新 phase。

**验收**：`test_all [75]` 14 条（常量/白名单/两个方向的进入与拒绝/互转拒/恢复清 reason/blocked 兼容）。

**边界**：① `resume()` 只重新 armed、不搬 phase（与既有 blocked 行为一致）—— 获授权/人决定后仍需显式
`goal_update(phase=active)`；② 未做 `pending`/`abandoned`（§1.2 参考态里的其余两个）；③ `ai_code` 的
续跑 prompt 与 `goal_update` 的 example 还没提新 phase（跨包，另开）。

### 9.9 实施记录：`RL-03` 三段式回传（2026-09-30）

> §2.4。把"每条结果全文渲染进 prompt"改成三段：**必进摘要行 / 按需证据块 / 指纹压缩**。

| 位置 | 内容 |
|---|---|
| `agent_runner.py` | 新节：`result_fingerprint` / `fingerprint_short` · **`summary_line`** · **`retrieve_evidence`**（索取入口）· **`FeedbackLedger`** · **`render_feedback`**；`run_conversation` 按会话建账本 + 每轮扫索取标记 |

真跑样例（摘要行 / 压缩）：

```
[denied] file_write · BOUNDARY · fp=a3f2 · 可换路径 · 替代: 写项目内 · 索取全文: [evidence fp=a3f2]
第1次 len=85 → 第2次 len=29 `(同上，第 2 次) fp=a3f2 · BOUNDARY` → 第3/4次 len=29
```

**三条纪律都没回退**：`render_result` / `render_tool_result` / `render_error_result` / `truncate_tool_output`
**一行未动**；证据通道仍分别走 `render_error_result`（不套隔离块，RL-04①）与 `render_tool_result`
（SEC-011 隔离，一字未改）。

**验收**：`test_all`（Lead 集成）+ 队友的 `.test_tmp/rl03_check.py`（34 条 A/B/C/D 组）与
`rl03_loop_check.py`（8 条主循环接线）。

**边界**：① **只接了 `agent_runner.run_conversation`** —— `ai_code.py` 三处回喂仍是全文（跨 scope，下一轮补）；
② 索取口是**文本协议** `[evidence fp=xxxx]`，不是新工具；**真实模型会不会自发索取未经真机验证**（本包最大落地风险）——
若不索取，下一步应把 `instruction` 前若干字符**内联进摘要行**；③ `partial` 仍无生产者；
④ 压缩键 = `(fingerprint, refusal_class)`，异指纹/异 class **不并**（宁少压不错压）；执行层的 `fingerprint` 生产者仍空。

### 9.10 实施记录：`HL-03` 三条硬规则（2026-09-30）

> §3.4。三条**全部来自现有 bug**，从"实现细节"升级成**契约 + 断言**。

| 规则 | 落点 |
|---|---|
| ① `MALFORMED` 永不计入熔断 | `tools/status.py` 新增 **`counts_toward_breaker(status, error_code)`**（= `classify_refusal(...) != MALFORMED`）；`execution_layer.py` 的**唯一熔断入口**早退。堵住的活违规：`_handle_permission_request`(:2300) 与 `_handle_ask_user`(:2337) 的 `FORMAT_ERROR`（RL-02 归 `MALFORMED`）曾被喂进账本 ⇒ "漏参数 → 3 次 → 整个控制工具熔断"的**死锁** |
| ② 降级必须声明 | `ExecutionLayer.degradations` + `_note_degrade()`（结构化 + stderr 一行，同一 kind 只播一次）；三处**纯静默**降级接上（待办加载 :817 / 持久规则加载 :830 / 意图路由 :1200）。`agent_runner.py` 的 tools→文本协议降级由 RL-03 同批补声明 |
| ③ 降级方向只朝更严 | `tools/status.py` 的 `DEGRADATION_TARGETS_STRICTER={deny,limited}`；**修掉唯一的朝松降级**：`_gated_identity` 在 `core.ace_net` 不可用时原 `return ""`（= 退回按工具名授权、悄悄拆掉 H-09 对象绑定）→ 改绑**本次调用参数指纹** + 声明 |

**Lead 裁决（写进 `test_all [10]`）**：`[10]` 原先把"request_permission 漏 target 连打 3 次 → 熔断"钉成期望值 ——
那**正是** `execution_layer.py:1749` 注释自述的 bug（"小模型总是漏 target 参数，最后熔断死循环"），
是**血证不是契约**。按 §3.4① + RL-02（`FORMAT_ERROR → MALFORMED`）改成"**不熔断**，第 4 次仍是 `FORMAT_ERROR`"。

**边界**：① **按指纹的升级（HL-02）尚未建** —— H-21 指纹只管 `_stage_parse` 那一层；
② `ai_code.py:999-1001` 的降级仍静默（跨 scope，下一轮）；③ `core/ace_rules.load_rules` 的"读坏就当空"
方向偏松（丢用户 deny），只补声明、未改 fail-close（牵会话可用性，**决策项**）。

### 9.11 实施记录：`DL-02` 优先级 = 依赖 DAG 拓扑序 + 三档（2026-09-30）

> §1.3。`Goal` 加 `deps` / `blocks`；**排序做成"目标集合"的纯函数**（`GoalStore` 的单目标 API 零改动 ——
> 它是既有契约，被 `test_all [25]/[75]` 直接钉死；而"排序"本来就不需要状态，需要的正是一份目标集合）。

| 位置 | 内容 |
|---|---|
| `tools/goal_tools.py` | `TIER_BLOCKING/ENABLING/FILLER` + `TIER_RANK`；id 归一（列表/逗号串/JSON 串 + 严格写 `GOAL_BAD_DEPS`）；`Goal.deps/blocks`（`__post_init__` 排序去重）；纯函数 `dependency_edges` / **`priority_tier`** / `find_dependency_cycle` / **`priority_order`**（Kahn + `(档位序, id)` 确定性 tie-break） |
| `tools/registry.py` | `goal_create`/`goal_update` 加可选 `deps`/`blocks`；`goal_status` 描述补依赖边 |

**⚠ Lead 裁决（三档消歧，本包的设计决定）**：§1.3 原文只给了 `blocking` 一条判据（"`blocks` 非空且下游未完成"）——
**它判不出 `enabling`**（凡下游未完成者都满足它 ⇒ `enabling` 恒空）。本包的消歧（**采纳**）：

```
blocking : 有未完成下游 且 自身前置已全完成  → 当前瓶颈，最前
enabling : 有未完成下游 但 自身还被前置卡着  → 迟早的解锁者，次之
filler   : 没有未完成下游（含下游都已完成）  → 最后
```

**可复现性是命门**：Kahn 拓扑 + `(档位序, id)` 取最小；id 唯一（重复 → `GOAL_DUPLICATE_ID`）；
deps 与 blocks 归一成同一条边；落盘排序去重 ⇒ 与输入顺序、dict 迭代顺序无关。
**跨进程证据**：`PYTHONHASHSEED=0 / 4242 / random` 三份 `ORDER_SIGNATURE` **逐字相同**。
**环检测**：`find_dependency_cycle`（迭代式 DFS、确定性）返回闭合路径，`priority_order` 抛
`GOAL_DEPENDENCY_CYCLE`（信息点名环上节点），不死循环。

**验收**：`test_all [80]`（Lead 集成）+ 队友 `.test_tmp/dl02_check.py`（39 条）。
**边界**：① 集合外 id 被忽略（可只对待办子集排序，代价是写错的 dep id 不报错）；
② 单目标 store 查不到跨目标环（由排序时查）；③ 排序不筛可执行性（`blocked/paused` 照排 —— 档位是杠杆不是可做性）；
④ 未给模型排序入口（单目标 store 拿不到 `all_goals` 真值源；建议 `/goal order` 跨包做）；⑤ 新增 code 未进 `tools/status.py` 登记表。

### 9.12 实施记录：`DL-03` 拒绝账本 + `HL-01` 失败账本（C3 同批）+ `HL-02` 五级阶梯（2026-09-30）

> §1.4 / §3.2 / §3.3 / §4。**同键不同命**是这一包的枢纽。

| 位置 | 内容 |
|---|---|
| `core/ace_ledgers.py`（**新**，700 行） | `LedgerKey(goal_id, fingerprint, class)` · **`RefusalLedger`**（知识 / 可 `save`/`load` / `propose_rule` / `report_defect`）· **`FailureLedger`**（状态 / **无落盘 API** / `is_fingerprint_banned`）· `RepeatFailView(dict)` / `BannedToolsView(set)` **兼容视图** · `ladder_step` |
| `tools/status.py` | HL-02 阶梯闭集 `LADDER_LEVELS`/`LADDER_ACTIONS`/`ladder_action`/`ladder_rank` + 阈值 3/5/3 · 六类唯一驱动动作 `DRIVER_ACTIONS` · **DL-04**：`LEARNING_ACTIONS` 闭集 / `RELAXING_ACTIONS` / `RelaxationForbidden` / `assert_no_relaxation` / `learning_action_ok` |
| `cli/ace_sessionlog.py` | 新事件 `ledger/refusal` · `ledger/ladder` · `ledger/proposal`；`record_tool_result` 按需补 `refusal_class`/`fingerprint`/`retryable`/`hint`（补上 §9.5 边界③） |
| `execution_layer.py` | 两账本 + 兼容视图；`current_goal_id()`；`_fingerprint_gate_reason` 闸门（只问 `is_fingerprint_banned(goal_id, fp)`）；**`_note_tool_failure` 换键**（`tool:fingerprint:class`）；`_stage_result` 成功只清自己那份失败计数、失败回喂 ①②；`answer_escalation` / `save_refusal_ledger` / `end_session` |

**熔断指纹不是工具**：闸门不再读 `banned_tools`（它降级成**兼容视图** —— `set` 子类，与账本同一份状态，`discard()` 真解禁）。
**DL-04 写成断言**：`RuleProposal(action="allow")` 当场抛 `RelaxationForbidden`；`accept_proposal(confirmed_by="")` 抛异常；
产物只能是 **deny** 规则；账本里**没有任何** `approve`/`grant`/`allow`/`relax` 入口。**放宽只能是人的动作**。

**Lead 裁决（两处，均采纳本包做法）**：
1. **§3.2 举例要更正**：卡里"`file_write` 的两种不同 403 互相压制"**在现行代码里不成立** —— `_note_tool_failure`
   对 403 早退（`test_all [40]` SEC-019 钉住"安全 403 不进熔断"）。粗键真正伤害的是**可计数的失败**（两条不同
   路径的 404 等）。所以"两条不同 fingerprint 互不影响"落在两处：**拒绝账本**（403 的**知识**按指纹分开、工具
   完全不熔断）+ **失败账本**（可计数失败一条熔断不压制另一条）。
2. **403 的分类缝隙**：持久规则 deny（403 字典）按 `classify_refusal("403","403")` 归 `BOUNDARY`，与 RL-02 把
   "策略/黑名单"叫 `POLICY` 有语义缝隙。**取舍**：宁可留缝隙也不新开第二份分类表（唯一判定处是 RL-02 的纪律）。

**兼容性（零断言改动）**：`RepeatFailView`/`BannedToolsView` 让 `[10]/[40]/[43]/[79]` 的 `repeat_fail == {}`、`.clear()`、
`"file_read" in banned_tools`、`banned_tools.discard()`、409 两倍阈值全部照旧。**`test_all` 一条都没改。**

**边界**：① 账本是内存 dict（非线程安全，执行层单会话单线程）；`RefusalLedger` 5000 条按 `last_at` 淘汰（**有损**）；
② **落盘默认关**（`config["refusal_ledger"]=<path>` 才跨会话），CLI 还没接线这个配置项；
③ `goal_id` 从 `goal_store.current()` 读，空 `goal_id` **不算**一个目标（单会话不会误触发跨目标 L4）；
④ **L4 是阻塞式**，靠 `answer_escalation(text)` 解除；**四个外壳还没消费它**（UI 接线跨包，同 RL-01 那句"字段到了、用途还没到"）；
⑤ **HL-05 三级预算只留接线口**（`config["refusal_budget"]` 默认 0 = 行为与现状一致）；
⑥ 学习出口只到"提议/上报"，`accept_proposal` 是唯一落地入口且强制人签字 —— **CLI/TUI 的"确认固化"交互尚未接**（TH-R3 的完整闭环还差这一段）。
