# 立项卡：凭据回显边界 —— `hidden` 从不生效（H-33 ~ H-35）

> 编号：承接 `docs/design/CONFIRM-BOUNDARY.md` 的 **H-** 命名空间（那张卡 H-27 ~ H-31 已全部实施并收敛，
> 本卡是**新一批**，`H-33` 起；不改那张卡的状态、也不回填 BACKLOG 的 SEC-/Q-/R-/REL- 编号）。
> 上级：`docs/ROADMAP.md` **§3.3 第三条根因** · **§7.2 批次 -1（闸门）** 的 **G6**。
> 状态：**H-33 / H-34 / H-35 已实施**（2026-09-27；「先看它红」与改后全绿的双向证据、以及回归结果，见 **§6**）。
> 来源：2026-09-27 复核 `ROADMAP` §3.3 第三条时，在现码上**逐环节追完整条链**（下面每一条都是实测，不是推断）。
> 纪律：头部不手抄断言总数（`SAFETY-HARDENING` 的规矩）；每个工作包一个可独立回滚的提交。

---

## 0. 一句话诊断

> **向导把 API key 标记成 `hidden=True`，而这个标记最远只走到"谁去问"的分支 —— 一旦有界面，它就消失了，值被明文画在屏幕上。**

这不是"某一处忘了传参"，是**通道里根本没有这个属性**（§0 的 H-33）：三个 `ask_text` 实现、
以及 `choice_request` 协议的字段表，**都没有 secret 这个概念**。所以每个外壳都"没做错"，
但它**全都**不回显掩码。

### 0.1 实测链条（每一步都可在现码上复核）

| # | 环节 | 落点 | 实测 |
|---|---|---|---|
| 1 | 密钥步骤**确实**声明了 hidden | `ai_code.py:3005-3007` | `WizardStep("api_key", …, default="", **hidden=True**, help_text=…)` |
| 2 | `hidden` 的**唯一**消费点 | `ai_code.py:2961-2967` | `else:` 分支里 `if step.hidden: getpass.getpass(...)` —— **只在"没有组件界面"时生效** |
| 3 | 有界面时走另一条路 | `ai_code.py:2956-2960` | `if self._ui_can_prompt(): raw = self._ask_text(f"{step.prompt} [{current}]: ", current)` —— **`hidden` 没有传下去** |
| 4 | `_ask_text` 的签名里没有 hidden | `ai_code.py:4007` | `def _ask_text(self, prompt: str, default: str = "")` —— 而它**有** `current`（当前值）且会把它拼进 prompt |
| 5 | 协议层的 `ask_text` 也没有 | `core/ace_serve.py:509` | `def ask_text(self, prompt, default="")` → `_ask("text", prompt, default=…)` → 发 `choice_request(kind="text", title=…)`；`EVENT_REQUIRED["choice_request"]` = `("kind", "title")`（`ace_events.py:79`），**无 secret 字段** |
| 6 | TUI 的 `ask_text` 也没有 | `tui/app.py:1140` | `def ask_text(self, prompt, default="")` —— 同样不带 |
| 7 | 值被**明文渲染** | `frontend/src/components/ChoiceDialog.tsx:166-171` | `{kind === 'text' ? (<Text>{text}</Text>) …}` —— `text` 就是当前值，直接画出来 |

**⇒ 有界面时一共两条泄漏路径**（H-34）：

- **路径 A**：`ui.ask_text` 存在 → 走外壳自己的文本渲染 → Ink 是明文（第 7 步）；`ui/`、`tui/` 同样没有掩码概念。
- **路径 B**：`ui` **有 `choose` 但没有 `ask_text`** → `_ask_text` 落到 `input(prompt)`（`ai_code.py:4021`）→ **`input()` 本身就回显**。
  而准入判据是 `_ui_can_prompt()`（`ai_code.py:3964-3967`）—— 它查的是 **`choose`**，不是 `ask_text`；
  两个判据不一致，于是"能弹选择器但不会问文本"的界面**必然**走明文。

**唯一正确的那条路是无界面分支**（第 2 步的 `getpass`）—— 也就是说：**有界面反而更弱**。

**而提示词本身就在承诺这件事**（三个语种都承诺，实测）：
`locales/zh.json:156` "API Key（输入时不显示）" · `locales/ja.json:158` "API Key（入力は表示されません）" ·
`locales/en.json:160` "API Key (not echoed)"。
修复**前**跑 H-35 断言时，送进外壳的提示串正是 `API Key（输入时不显示） []: ` ——
**说不显示，而它正在显示**。

### 0.1b 四个外壳的点名（H-33 的施工图，2026-09-27 实测）

| "外壳" | `choose` | `ask_text` | 说明 |
|---|---|---|---|
| `core/ace_serve.py`（Ink 经 `ace --serve`） | `:486` ✅ | `:509` ✅ | **真正的宿主之一**；`secret` 从这里进事件流 |
| `tui/app.py`（Textual 全屏） | `:1113` ✅ | `:1140` ✅ | **另一个真宿主**；掩码落 `TextScreen(password=)` |
| `ui/`（Python REPL） | —— | —— | **根本不挂宿主**（`attach_ui` 没人调它）⇒ 走 `_ui_can_prompt()` 的 `else` 分支用 `getpass`，**本来就是对的**；它的画法是 `render_wizard`（H-34c 已修） |
| 测试假宿主 | `test_all.py:10801` | `:10805` | `[63]` 的 `_AutoUI63`；本卡给它加了 `**_kw` 容错 |

> **结论：真正的宿主只有两个**，所以 H-34c"两个 fallback 也要接"实际落在
> `ui/` 的**纯渲染器**（`render_wizard`）与 `tui/` 的 `TextScreen` 上，而不是四处各改一遍。
> 另有**第二个向导循环** `ai_code.py:4510-4536`（`term_probe`）有同一缺陷类 —— 今天无隐藏步骤
> （`ace_term.probe_steps` 只有 color/unicode/mouse），本卡已顺手接上（UI 分支传 `hidden`，
> 非 UI 分支改走 `getpass`），并在 §6 记为"**预防性**，非修复"。

> **一处我自己复核时纠正的错误**：`tui/app.py:983` 的 `if _hidden:` 看起来像"TUI 处理了隐藏"，
> 实际那个 `_hidden` 来自 `_strip_invisible()`，指的是**不可见 Unicode 字符**（bidi 覆写等），
> 与密码掩码**无关**。所以 **没有任何外壳掩码**，不存在"唯一例外"。

### 0.2 为什么这是安全问题而不是体验问题

1. **它落在"凭据"这条线上**：`hidden=True` 的用途就是 API key（`wizard_help_key`）；屏幕上有值、
   还有终端回滚缓冲与录屏面。
2. **它与既有立场矛盾**：`SAFETY-HARDENING` 的两条主线之一就是**把 fail-open 改成 fail-close**
   （快照失败 → `403`；审批非交互一律拒）。而这里恰好相反：**能力越强（有界面）就越松（明文）**。
3. **现有断言看不见它**：`test_all.py:8555` 断言的是 `_cfg_steps50[1].hidden is True` ——
   钉的是"步骤**声明了** `hidden`"，**不是"`hidden` 被尊重"**。这正是 `ROADMAP` §6 **ACC-04** 的
   第四种偷换 **`attempted → judged`**：拿"意图"当"结果"。

---

## 1. 目标与非目标

### 目标

1. **`hidden` 成为通道属性**：从 `WizardStep` 一路到外壳渲染，这条信息不再在"谁去问"的分支上丢失。
2. **有界面不比无界面弱**：加密路径（`getpass`）与界面路径**同口径**，不再出现"有 UI 就静默降级"。
3. **断言钉结果，不钉声明**：验收看的是**渲染输出里没有密钥原文**，不是"步骤声明了 hidden"。
4. **两个 fallback 也是安全的**：`ui/` 与 `tui/` 必须一起接上 —— 否则这次修完，它们就成了新的泄漏面。

### 非目标（明确不做，避免本卡膨胀）

- **不改 `WizardStep.hidden` 的公开语义**：含义不变，本卡只是让它**第一次真正生效**。
- **不动既有事件字段**：`secret` 是**正交新增**（与 `THREE-LAYERS` TH-R5、S-2 同一条纪律）。
- **不做密钥存储加固**：存储加密 / 文件权限 / 环境变量优先级**不在本卡**（落盘面列为开工第一件**待核实**的事，
  见 §5，**不写进本卡验收** —— 没核实过的东西不立为门槛）。
- **不改非凭据的文本输入**：拒绝理由、向导的 provider/model 步骤行为不变。

---

## 2. 工作包

### W0 · 通道层：让 `hidden` 走到底（H-33）

| ID | 事项 | 证据（现码 + 实测） | 改法形状 |
|---|---|---|---|
| **H-33** | **`ask_text` 通道没有 secret 概念** | 三处签名都不带：`ai_code.py:4007`、`core/ace_serve.py:509`、`tui/app.py:1140`；`WizardStep` 有 `hidden`（`ui/ace_dialog.py:404/412`）而它最远只到 `ai_code.py:2963`；`EVENT_REQUIRED["choice_request"]` = `("kind","title")` | `_ask_text(prompt, default, *, hidden=False)` → `ui.ask_text(prompt, default, hidden=…)` → `core/ace_serve.py` 的 `_ask("text", …, secret=True)` → `choice_request` **正交新增 `secret`**；**必须同时**登记进 `ace_events.EVENT_REQUIRED` 的字段说明 + `frontend/src/protocol/types.ts` + `frontend/test/protocol.test.ts`（否则 parity 测试红 —— `WP-0` 的 P-06 同一条纪律） |

**W0 验收**：`choice_request(kind="text")` 在密钥步骤上**带 `secret: true`**；非密钥步骤**不带**（不误伤）；
`EVENT_TYPES` ↔ `EVENT_REQUIRED` 的既有断言（`test_all.py:7491`）仍绿。

---

### W1 · 表现层：两条泄漏路径（H-34）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| **H-34a** | **Ink 明文渲染当前值**（路径 A） | `frontend/src/components/ChoiceDialog.tsx:166-171` | `kind === 'text' && secret` 时**不回显值**（只画掩码占位 + prompt），与 `getpass` 同口径 |
| **H-34b** | **`input()` 兜底也回显，且准入判据不一致**（路径 B） | `ai_code.py:4021` 的 `input(prompt)`；准入是 `_ui_can_prompt()`（`:3964-3967`，查的是 **`choose`**），而实际用的是 **`ask_text`** | `hidden=True` 时**不再回落到明文 `input()`**：走 `getpass`，或按 H-30 的 fail-close 立场**直接拒绝**并说明原因；同时**把 `_ui_can_prompt` 的判据与实际使用的能力对齐**（查 `ask_text` 就不该拿 `choose` 当准入） |
| **H-34c** | **两个 fallback 必须同时接** | `ui/`（`ace_dialog` 的向导渲染）与 `tui/app.py:1140` 都没有掩码概念 | 两条 fallback 也接 `hidden`；**不接就等于把它们变成新的泄漏面** |

**W1 验收**：

- 有界面时**渲染输出里不含密钥原文**（断言渲染结果，不是断言入参）；
- 无界面时**仍走 `getpass`**（既有行为不许回退）；
- "有 `choose`、没 `ask_text`"的界面**不再**走到明文 `input()`（用 mock 钉住）；
- `ui/` + `tui/` 的向导路径各有一条掩码断言。

---

### W2 · 断言层：钉结果，不钉声明（H-35）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| **H-35** | **断言只钉"声明了 hidden"** | `test_all.py:8555`：`_cfg_steps50[1].hidden is True` —— 钉的是**意图**；**没有任何断言**看"值有没有被画出来" | 换成**端到端**：构造向导 → 走**有界面**路径 → 断言送往外壳的请求带 `secret` **且**渲染结果**不含**密钥原文；**改之前先看着它红** |

**W2 验收（两个方向都可证伪，沿用 `CONFIRM-BOUNDARY` W0 的做法）**：

- 去掉掩码渲染 ⇒ 红；
- 去掉密钥步骤的 `hidden=True` ⇒ 红。

---

## 3. 与既有卡的关系

| 卡 | 关系 |
|---|---|
| `WP-0-FRONTEND-CONVERGENCE.md` | **同一条通道**：`choice_request` 是 `WP-0` W0-B 的 P-05/P-06 的地盘，`kind='text'` 的回传路径（该卡 **P-10**）与本卡的 `secret` 字段**改的是同一个事件**。**本卡排在 `WP-0` 之前（批次 -1）**，否则同一条通道要在两批里被拆开改两次 |
| `ACC-GATES.md` **ACC-04** | 本卡 H-35 是 **`attempted → judged`** 的现场实例：`test_all.py:8555` 把"声明"读成"生效" |
| `ACC-GATES.md` **ACC-03** | 上报 H-33 时的 `Production producer` 是 **`ai_code.py:2956` 那个分支**（"有界面 ⇒ 走不带 hidden 的 `_ask_text`"），**不是**任何单个外壳的渲染代码 |
| `SAFETY-HARDENING.md` H-30（已闭环） | 同一条立场：**能力要么有边界、要么如实拒绝**。H-34b 的"拒绝"选项直接沿用它的形状 |
| `CONFIRM-BOUNDARY.md`（H-27 ~ H-31，已闭环） | 同一 H- 命名空间的上一批；H-28（"人批的是空白"）与本卡同族 —— **都是"人看到的和实际发生的不一致"** |
| `ROADMAP` §2.7 硬契约 | 本卡只做**正交新增字段**，与"不许静默降级"同向 |

---

## 4. 风险

| # | 风险 | 缓解 |
|---|---|---|
| **CR-R1** | **4 个外壳都要改一遍**，回归面与 `WP-0` 同级 | 本卡的验收**逐个外壳**列（§2 W1 四条），且 W0 只加**一个**协议字段 —— 新增而不改语义 |
| **CR-R2** | 掩码被"顺手"做成**加密**，于是界面口径与 `getpass` 分叉 | 非目标已写明：掩码**只影响回显**；加密/落盘是另一件事（且未核实） |
| **CR-R3** | 某外壳选择"拒绝"而非"掩码" ⇒ 与"有界面就能配"冲突 | 先掩码；"拒绝"只作**最后兜底**并在消息里给出出路（沿用 H-30 的三条出路写法） |
| **CR-R4** | 只修 Ink，忘了 `ui/` + `tui/` ⇒ 泄漏面转移 | H-34c 是**独立一行**，不是"顺带"；验收里两条 fallback 各有一条断言 |
| **CR-R5** | 把"落盘权限"顺手写进验收，但**从未核实** | 明确列入 §5 的**待核实**，不写进 §2 验收（沿用 ACC 的"没核实不立门槛"） |

---

## 5. 开工检查单

- [ ] **先核实密钥落盘面**（本卡未核实、**不写进验收**）：`save_cli_config` 写下的文件在 Windows 上的 ACL、
      以及它是否在 `.gitignore` 覆盖范围内
- [ ] **4 个外壳逐个点名**：谁实现了 `ask_text`、谁只实现了 `choose`、谁两者都没有（这决定 H-34b 的兜底形状）
- [ ] **改之前先让 H-35 的断言红**（否则无法证明这次确实修好了）
- [ ] 与 `WP-0` 排序对账：**本卡在批次 -1，先于 `WP-0`**（`ROADMAP` §7.2）
- [ ] 每个工作包一个可独立回滚的提交
- [ ] `ruff` + `py_compile` + `python test_all.py` + `cd frontend && npx tsc --noEmit && npx vitest run` 全绿
- [ ] 完成时登记 `CHANGELOG.md` → push

---

## 6. 实施记录（2026-09-27）

### 6.1 「先看着它红」—— 三条效果断言的红（`test_all [50]`，当时 **56/59**）

| 断言 | 红出来的证据 |
|---|---|
| **H-34c** 隐藏步的默认值不许被渲染 | `['┌ 向导 1/1 · 密钥 ─…┐', '│ Key  [sk-preset-leak] │', '├…┤', …]` |
| **H-33** 密钥步必须把「隐藏」送到外壳 | `[{'prompt': '提供商编号 []: ', 'kw': {}}, {'prompt': 'API Key（输入时不显示） []: ', 'kw': {}}, …]` —— 三次调用的 `kw` **全空** |
| **H-34b** 不许掉进明文 `input()` | `['提供商编号 []: ', 'API Key（输入时不显示） []: ', '模型名 [glm-4.7-flash]: ']` —— 密钥提示**出现在明文输入路径里** |
| （对照）非隐藏步不许被误标 | ✅ 当天就是绿的 —— 它是"不误伤"守卫，不是缺陷证据 |

**另有两条是实施之后补的**（`choice_request` 的 `secret` 字段本身）：

| 断言 | 状态 |
|---|---|
| H-33 凭据步的 `choice_request` **带 `secret`** | ✅ —— 这是卡里 **W0 的验收条文**，第一轮漏了 |
| H-33 普通文本步**不带** `secret`（不误伤） | ✅ |

> **一次纪律偏差，如实记下**：这两条**没有走"先看着它红"**（它们是实现完成后才补的）。
> 它们的"红"可以从 diff 直接读出来 —— 改动前 `ServeUIHost.ask_text` 根本不接受 `hidden`，
> 事件里也没有这个键。但"能从 diff 读出来"不等于"看过它红"，所以记在这里。

> 第 2、3 条的价值在于它们是"**说不显示、正在显示**"的字面现场：提示串与路径都在眼前。

### 6.2 改了什么

| 文件 | 改动 |
|---|---|
| `ai_code.py` `_ask_text` | 签名加 `*, hidden=False`；把 `hidden` 与 `default` 一起交给宿主；宿主不认就说出来（`TypeError` → stderr）；`hidden=True` 走不到外壳时**拒绝**，**绝不**回落明文 `input()` |
| `ai_code.py` `/config` 向导 | 隐藏步**不带 `[当前值]`、不预填默认值**，并把 `hidden=step.hidden` 传下去 |
| `ai_code.py` `term_probe` 循环（`:4510`） | 同一缺陷类：UI 分支传 `hidden`，非 UI 分支改走 `getpass`（**预防性** —— `ace_term.probe_steps` 今天没有隐藏步） |
| `core/ace_serve.py` `ask_text` | 接受 `hidden`；为真时事件带 **`secret: true`**（正交新增字段） |
| `core/ace_events.py` | `choice_request` 的契约表登记 `secret` 的含义 |
| `tui/app.py` | `TextScreen(password=…)`（掩码**且不预填**）+ `ask_text(..., hidden=…)` |
| `ui/ace_dialog.py` `render_wizard` | 隐藏步不打印 `[default]`（`ui/` 回落路径的画法） |
| `frontend/src/protocol/types.ts` · `state/store.ts` · `App.tsx` · `components/ChoiceDialog.tsx` | `secret` 一路到渲染；为真时只画 `•` 掩码、不预填 |
| `frontend/test/credential.test.tsx` | **新增** 4 条渲染断言（含对照组） |

### 6.3 Ink 侧的坑：**假通过**（值得单独记一笔）

`ChoiceDialog` 的 `text` 分支此前**零渲染断言**。新测试第一版"通过"了 H-34a，但其实是**假通过**：
`render()` 返回时 Ink 还没挂上输入监听，紧接着的 `stdin.write` 按键**直接落空** —— 哨兵根本没进状态，
于是"画面不含密钥"**毫无意义地成立**。

修法（两条同时要，缺一条就还是假的）：

1. 每次 `stdin.write` **之前**先 `await tick()`（`app.test.tsx:30` 早就记过这个坑："界面在、但打不进字"）；
2. **加一组对照**：`secret=false` 时同一个哨兵**必须**出现在画面上 —— 它证明输入路径真的生效，
   上一条的"不含"才有意义。

> 这与 **ACC-04** 的「**未评估读成 `false`**」同源：**没有对照的否定断言等于没断言。**

### 6.4 回归结果

| 项 | 结果 |
|---|---|
| `test_all --only 50` | **61 / 61 全绿**（六条新断言：3 条先红后绿 + 1 条对照 + 2 条后补） |
| `test_all --only 38,39` | **19 / 19 全绿**（权威树 / 文档数字 / 已展开目录子项登记） |
| `tsc --noEmit` | 退出码 **0** |
| `vitest run` | **20 文件 / 279 测试全绿**（含新增 `credential.test.tsx` 4 条、真引擎集成 9 条） |
| 全量 `test_all.py` | **全绿 · 0 失败 · `🎉 全部测试通过`**（2026-09-27，HEAD `b94ab7f` + 本卡改动；跳过 3 项 = job 档能力探测）。此前的全量中断是环境/夹具问题，见 §6.5 —— 修正后**本卡改动不构成任何失败项**，六条新断言在日志里逐条 ✅ |

### 6.4b 已实施但**未断言**的三处（如实列出，各是一条可补的断言）

| 位置 | 为什么没断言 | 风险 |
|---|---|---|
| `tui/app.py` `TextScreen(password=…)` | `[60]` 覆盖 Textual 骨架，但没有"掩码真的开了"的断言 | 中 —— TUI 是本卡唯一"改了但没钉住"的掩码点 |
| `ai_code.py` `_ask_text` 的 `TypeError` 分支（宿主有 `ask_text` 但不认 `hidden`） | H-34b 的断言覆盖的是"**没有** `ask_text`"那一路，不是这一路 | 低-中 —— 它决定"旧宿主"是**说出来并拒绝**还是静默 |
| `ai_code.py` `term_probe` 的 `getpass` 分支 | 预防性改动（今天没有隐藏步） | 低 |

> 这三处**不影响本卡的三个 H 项成立**（凭据路径的主干已被六条断言钉住），
> 但按 ACC-04 的口径，**"没断言"与"断言通过"不是一回事** —— 所以单列，不混进 §6.4 的绿里。

### 6.5 顺带修正：**[63] 违反了 `test_all.py:44` 自己写下的规矩**

`test_all.py:44` 写着："测试临时目录统一放在工作区（**部分受限环境禁止写系统临时区 / `mkdtemp` 目录**）"。
而 [63] 是**唯一的例外**：它用 `tempfile.mkdtemp()` 建临时目录。实测后果是确定性的：

```
mkdtemp() 之后：
  mkdir('plain')      → PermissionError [WinError 5]
  mkdir('.guardian')  → PermissionError [WinError 5]
  mkdir('sub/deep')   → PermissionError [WinError 5]
  chmod(dir, 0o777)   → PermissionError [WinError 5]      ← 连改权限都不行
```

于是全量在 `test_all.py:10896` 的 `AgentCLI({"project_root": str(_tmp63.mkdtemp())})` 构造里炸掉：
`execution_layer.py:823` → `core/guardian.py:176` `self.store.mkdir(...)` → `WinError 5`，
**整份全量连汇总行都打不出来**（表现是"exit 1，没有任何 ❌"）。

- **不是本卡引入的**：栈里没有任何本卡改过的帧（`AgentCLI.__init__` 在 `ai_code.py:3468`，
  本卡动的是 `:2958` / `:4007` / `:4522`）；
- 但它**挡住了本卡的验证**，所以改了：两处改用仓库自己的 `mktemp()`，并删掉 `import tempfile as _tmp63`；
- **没有为它单独领 H 编号** —— 编号空间是 `SAFETY-HARDENING` 的规矩，留给作者决定。

