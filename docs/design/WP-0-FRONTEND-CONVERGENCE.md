# WP-0 立项卡 —— 前端收敛（一份协议，一个正式外壳）

> 编号：`WP-0`（`WP-` 是 `docs/ROADMAP.md` 的工作面命名空间，本卡是它的第一张）。
> 上级：`docs/ROADMAP.md` §4（工作面）· §7 **批次 0**（**前置**）· §8 R-1 / R-3。
> 状态：**批次 -1 两件事已完成**（**W0-D = D3** · **W0-A 三张点名表 + 收/不收清单**，含
> ✅ 头号发现**已修**（2026-09-27）：Ink 路径的防误触宽限期，承诺了、现在也有了 —— 见 §2 的
> 「✅ 头号发现已修」）。
> **批次 0 已开工**：口径对齐 **R-1 / R-3 / R-4 / R-5 / R-6 已收**（各带对拍或断言）·
> 同批的 **`RL-01` 结果信封已落地**（`THREE-LAYERS` §9）。
> **仍未完成**：**R-7（能力缺口，待决）· 本卡的 W0-B / W0-C
> （协议消费与外壳降级）** ⇒ **批次 0 的出口条件尚未达成**（"4 份重复对话框合一 + `ui/`/`tui/`
> 降为 fallback"都还没做）。W0-A 的"第 5 份实现就红"那条断言也仍**没做**（如实标注，见 §2 W0-A 验收）。
> 来源：2026-09-27（HEAD `b94ab7f`，v3.45.0，工作树干净）**逐项在现码上实测复核**；
> 凡与 `ROADMAP` 的转述不一致之处集中在 **§0.2**，**不改写 `ROADMAP` 原文**，以本卡为准并留档。
> 纪律：头部**不手抄断言总数**（沿用 `SAFETY-HARDENING` 的规矩），条数以 `python test_all.py` 输出为准；
> 每个工作包一个**可独立回滚**的提交。
> 站位：本卡是批次 0 存在的**唯一理由**（`ROADMAP` §1 S-2）—— 后面每个面的工作量是 ×1 还是 ×4，由这里决定。

---

## 0. 一句话诊断

> **协议已经有了，四个外壳也都连着它 —— 但"呈现逻辑"仍然每个外壳各写一遍，而且没有任何一条断言在数这件事。**

实测：`core/ace_events.py` 的 **13 个事件类型全部有发射方**（§0.1 ③），`ace --serve` 的双向 NDJSON 在跑，
`frontend/src/protocol/` **577 行**是现成的消费者。所以 WP-0 **不是造协议**。

没解决的是另一半：`frontend/src/render/` 有 **10 个模块 / 1,546 行**是 `ui/ace_*.py` 的**逐条重实现**，
靠 **10 个 TS 测试读 Python 源码对拍**钉住（§0.1 ④⑤）。这不是"协议没到位"，是"每个外壳自己实现一遍" ——
S-2 说的就是这个。

### 0.1 现状实测（2026-09-27）

**① 四个外壳的体量**（本卡实测：`Get-ChildItem -Recurse -File | Get-Content | Measure-Object -Line`，
排除 `node_modules` / `__pycache__`）：

| 外壳 | 落点 | 文件 | 行 |
|---|---|---|---|
| Python REPL（现为 fallback） | `ui/` | 25 | **5,050** |
| TUI（现为 fallback） | `tui/`（`app.py` 1609 + `bridge.py` 53 + `__init__.py` 22） | 3 | **1,684** |
| Ink 前端（**声明的唯一正式外壳**） | `frontend/src` | 29 | **4,487** |
| 同上（测试） | `frontend/test` | 20 | **2,749** |
| **合计呈现代码** | | **77** | **≈13,970** |

> `ROADMAP` §4 写的 5050 + 1684 + 4487 + 2749 ≈ 13,970 —— 本卡逐项复核，**一致**。

**② 协议侧**（本卡实测）：`core/ace_serve.py` 389 行（`PROTOCOL_VERSION = 1`、`FrameEmitter`/`EventEmitter`）
+ `core/ace_events.py` 184 行（13 类事件 + 每类必需字段的**唯一来源** `EVENT_REQUIRED`）
+ `core/ace_commands.py` 161 行；前端侧 `frontend/src/protocol/client.ts` 347 + `types.ts` 230 = **577 行消费者已在跑**。

**③ 13 类事件全部有发射方**（本卡实测：`grep '\.emit\("'` 单行 9 处 + 多行调用 2 处 + `--serve` 桥 3 处）：

```
session_start  user_message  model_request  tool_start  tool_call  tool_result
permission_request  choice_request  notice  final  session_end  model_delta  status
```

其中"两个时刻"已写进契约（`ace_events.py:27-29`）：**`tool_call` 是事后审计记录**，
想画"工具正在跑"必须用 **`tool_start`**。

> ⇒ `SAFETY-HARDENING.md:204` 那句"`model_delta` / `status` 两个事件在契约里却无发射方"**已不成立**
> （`model_delta` 在 `ai_code.py:6752`、`status` 在 `ai_code.py:2528` 均有发射点）。
> 本卡据此把 WP-0 的协议部分定为"补**字段与消费契约**"，不是"补发射方"。

**④ 真正的重复在呈现层**（本卡实测 `frontend/src/render/`）：

| 模块 | 行 | 对拍的 Python 源 |
|---|---|---|
| `vim.ts` | 439 | `ui/ace_vim.py`(333) |
| `menu.ts` | 331 | `ui/ace_menu.py`(269) |
| `text.ts` | 260 | `ui/ace_text.py`(89) |
| `markdown.ts` | 172 | `ui/ace_markdown.py`(324) |
| `diff.ts` | 148 | `ui/ace_diff.py`(145) |
| `match.ts` | 57 | `ui/ace_text.py` 的 `SEPARATORS` |
| `tasktree.ts` | 53 | `ui/ace_layout.py` |
| `spinner.ts` | 39 | `ui/ace_spinner.py`(86) |
| `glyphs.ts` | 33 | `ui/ace_text.py` |
| `logo.ts` | 14 | —— |
| **合计** | **1,546** | 再加 `theme/tokens.ts` 131 ⇒ **1,677** |

**⑤ 对拍测试是 10 个，不是 8 个**（见 §0.2 ①）。

### 0.2 与 `ROADMAP` 转述不一致的三处（**开工前必须先纠正，否则验收会写错**）

**① `ROADMAP:315` 的"8 个跨语言守卫测试"实为 10 个，且其中一个不读 Python。**
本卡实测：`frontend/test` 里**读另一套外壳的源码做 parity** 的文件共 **10** 个 ——

| 测试 | 读什么 |
|---|---|
| `theme.test.ts` | `ui/ace_theme.py`（token 名 + dark/light 调色板逐项相等） |
| `protocol.test.ts` | `core/ace_serve.py`(`PROTOCOL_VERSION`) · `core/ace_events.py`(`EVENT_TYPES`) · `agent_runner.py` |
| `spinner.test.ts` | `ui/ace_spinner.py`（5 个阶段 + 5 个字形） |
| `diff.test.ts` | `ui/ace_diff.py` |
| `tasktree.test.ts` | `ui/ace_layout.py`（逐行比对） |
| `match.test.ts` | `ui/ace_text.py` 的 `SEPARATORS`（**注意不在 `ace_selector.py` 里**） |
| `vim.test.ts` | `ui/ace_vim.py`（逐条差分） |
| `text.test.ts` | `ui/ace_text.py`（逐码点比对字符宽度） |
| `i18n.test.ts` | `ui/i18n.py`（`DEFAULT_LANG` / `SUPPORTED`） |
| `launcher.test.ts` | **`ace.cmd`**（不是 Python 源码） |

> `ROADMAP` 列的 8 个**漏了 `text` 与 `i18n`**；而 `launcher` 读的是 `ace.cmd`，
> 所以 `ROADMAP:315` 的"读 Python 源码做 parity"对它**不成立**。
> **影响**：WP-0 验收里"8 个守卫全部改指协议层"这条**目标数就是错的** —— 按 8 个改会漏掉 2 个漂移点，
> 而漏掉的正好是**字形**与**本地化**这两类最容易悄悄分叉的。

**② `ROADMAP:314` 的打包前置项没有可增补的对象**：`datas` 要增补的是"`frontend/` 构建产物"，而**本仓库没有构建产物**。
本卡实测：`packaging/ace.spec` 的 `datas` = `prompts` / `locales` / `assets` / `vendor` /
`README.md` / `SECURITY.md` / `LICENSE` / `executor`，**无 `frontend/`**；
而 `frontend/dist` **不存在**，`frontend/package.json` 的 `build` 就是 **`tsc --noEmit`（只类型检查，不产出文件）** ——
这一条由 `frontend/.gitignore` 自己写着：

> 构建产物（本包目前 `npm run build` 只做类型检查，不产出文件；留给将来）`dist/`

> **影响**：R-3 不是"往 `datas` 里加一行"，而是**三选一**（§2 W0-D）。
> 把它当一行改，会在打包阶段才发现**无产物可加**。

**③ `ROADMAP:194` 的"exe 只能跑 Python UI"要加一句前提**：那不是打包漏了文件，
而是 **Ink 外壳今天的运行方式就是"git checkout + `npm install` + `tsx` 直跑 TS 源码"**。
本卡实测：`ace.cmd:59-86` 要求 `where node`（Node ≥18）**且** `frontend\node_modules\tsx\dist\cli.mjs` 存在，
然后 `pushd frontend` 用 `node node_modules\tsx\dist\cli.mjs src\index.tsx` 起进程；
`frontend/.gitignore` 把 `node_modules/` 排除在版本库外（实测 `git check-ignore -v` 命中 `frontend/.gitignore:3`）。

> **影响**：WP-0 的三条出路在 W0-D，**结论是"要么发行包不再依赖 Node，要么承认 exe 只带 Python UI"** ——
> 但那是批次 0 的**前置项**（R-3），不是 WP-0 的副产品。

**④ `ROADMAP` S-2 的两个计数按字面不成立**（2026-09-27 实测，详见 §2 W0-A）：

- 「**权限对话框 ×4**」实为 **3 份**渲染器 —— 第 4 个候选（`ui/ace_dialog` + `ace_selector`）是
  REPL 的**选择**浮层，**不渲染权限请求**；
- 「**菜单 ×3**」实为 **2 个模型 / 4 个渲染宿主**；
- 「工具卡 ×3」**成立**，但其中**看板是 CLI+TUI 共用的**（`ui/ace_tools.py` 的 `ToolBoard`）。

> **影响**：这几个计数错在**把"同一职责写了几遍"与"几个外壳各写一遍"混为一谈** ——
> 而 WP-0 的工作量恰恰取决于前者。按"×4 个外壳各改一遍"排工，会把共用件算成四份。
> 另：`SAFETY-HARDENING.md:204` 的计数与 S-2 同源，同样需要按本节修正。

---

## 1. 目标与非目标

### 目标

1. **呈现逻辑朝着"只有一个实现"收敛**：引擎发结构化事件 → 外壳只渲染；
   `ui/` + `tui/` 降级为**无 Node 环境时的 fallback**，只修 bug 不加功能。
   > 诚实口径：`frontend/src/render/` 的 1,546 行里，**哪些该由协议承担、哪些是外壳自有的排版**，
   > 由 W0-A 先点名再定去留（见 §2 W0-A 的 P-03）—— **不做"全并"的假设**。
2. **重复度有名单、有断言**：把"权限对话框 ×4 / 工具卡 ×3 / spinner ×3 / 菜单 ×3"从**计数**变成**文件清单**，
   并且让"新增第 5 份实现"这件事**能被测试拦住**。
3. **`frontend/` 是唯一正式外壳，且它在 CI 里**（REL-09 已闭环：`.github/workflows/ci.yml:243` 的 `frontend` job，
   node 20 + `npm ci` + `tsc --noEmit` + `vitest`）。
4. **打包口径落定**：R-3 在批次 0 内给出结论并写进文档（D1/D2/D3 三选一，§2 W0-D）。

### 非目标（明确不做，避免本卡膨胀）

- **不造协议、不改协议语义**：只做**正交新增**（新事件 / 新字段），`PROTOCOL_VERSION` 与既有字段语义不动。
  理由：4 个外壳 + 外部消费者在同一条流上。
- **不删 `ui/` / `tui/`**：它们是"没有 Node 的机器"上唯一能跑的东西（`ace.cmd` 的回落路径）——
  删了等于把这类用户踢出产品。
- **不动 MCP 面**：`ace --mcp` 是**集成面不是外壳**（`MCP-SERVER.md:78` 自称"第四个前端"是指它借执行层，
  不是指它要参与 UI 收敛）。
- **不裁决"哪个栈才是产品"**：那是 `SAFETY-HARDENING.md:41` 明确划到本卡之外的产品决策；
  本卡只做"重复收敛"，裁决点已由 `ROADMAP` S-2 给出（`frontend/`）。
- **不重写 `frontend/` 的视觉**：只改"数据从哪来"。

---

## 2. 工作包

### W0-A · 把重复点名（**先做，且必须先做**）

现状：`ROADMAP` S-2 与 `SAFETY-HARDENING.md:204` 都给出**计数**（×4 / ×3），
但本卡实测 —— **全仓库没有一处给出文件清单**。所以开工第一件事不是改代码，是**点名**。

#### ✅ 已完成（2026-09-27）：三份点名表 + 一张"收 / 不收"清单

> 方法：两路独立只读侦察（一个查权限对话框，一个查工具卡/spinner/菜单），
> **每条论断都要求 `文件:行`**；关键论断由本卡复核过（复核记录见 §2 W0-A 末尾）。

##### P-01 · 权限对话框：**实测 3 份，`ROADMAP` 的「×4」按字面不成立**

| # | 实现 | 位置 | 角色 |
|---|---|---|---|
| 1 | `ask_grant` + `_read_answer` | `agent_runner.py:730` / `:669` | REPL **权限渲染器**（行式） |
| 2 | `PermissionScreen` | `tui/app.py:551` | Textual **权限渲染器** |
| 3 | `PermissionDialog.tsx` | `frontend/src/components/PermissionDialog.tsx:38` | Ink **权限渲染器** |
| 4 | `run_dialog`/`DialogSpec` + `run_selector` | `ui/ace_dialog.py:354`/`:85` · `ui/ace_selector.py:537` | REPL **选择**浮层，**不渲染权限请求** |
| 5 | `ChoiceScreen` | `tui/app.py:338` | Textual 选择/确认 |
| 6 | `ChoiceDialog.tsx`（choose/confirm/text） | `frontend/src/components/ChoiceDialog.tsx:39` | Ink 选择/确认 |
| 7 | `ServeUIHost` | `core/ace_serve.py:437` | **桥**，非渲染器（只发事件 + 等答案） |

引擎侧分发入口：`ai_code.py:3956 _ask_permission` → 无宿主时回落 `agent_runner.ask_grant`（`:3966-3975`）；
另有 `:2162 _pick_option` · `:3996 _select_index` · `:4062 _confirm`。对象来源：`execution_layer.py:1410 _gated_identity` · `:328 confirm_subject` · `:1747-1757`。

**字段级对照（三个真实权限渲染器）**

| 字段 | ① 终端 `ask_grant` | ② Textual `PermissionScreen` | ③ Ink `PermissionDialog` |
|---|---|---|---|
| 工具名 | ✓ 但**不由它渲染** —— 调用方先打印（`ai_code.py:5936` / `agent_runner.py:831`） | ✓ `perm_request_title`（`tui/app.py:595`） | ✓（`PermissionDialog.tsx:107`） |
| 请求理由 | ✓ 同样由调用方打印（`ai_code.py:5937-5938` / `agent_runner.py:832-833`）；`ask_grant` 只拿到一行 `perm_approve_q`（`locales/zh.json:90`，**无 `{tool}`/`{reason}`**） | ✓（`tui/app.py:596-597`） | ✓（`:109`） |
| **对象**（命令/路径） | △ **不在本渲染器里** —— 对象被折进 `reason`，由调用方打印 | △ 同左（渲染 `reason`） | △ 同左 |
| 三态 | ✓ `1/y 本次 · 2/a 本会话 · 3/n 拒绝`（`agent_runner.py:731` + `parse_grant_answer`） | ✓ `PERMISSION_OPTIONS`（`ui/ace_turn.py:59-63`） | ✓ **本地自抄一份 `OPTIONS`**（`:32-36`），注释声明须与 `ace_turn` 对齐（`:7-8`）—— **但没有断言** |
| 拒绝理由输入 | ✓ `n <理由>` → `on_deny_feedback`（`agent_runner.py:747-755`） | ✓ `Tab` 开备注框（`:575` / `:601-602` / `:620-631`） | ✓ `n` 进 typingReason（`:84-88`、`:111-116`） |
| 颜色 / 选项级 danger | ✗ 纯文本，**无颜色、无 danger** | ✓ 选项级 `perm_danger`（`:598-600`）+ `$warning` 边框（`:559`） | ✓ `color('warn')` 边框+标题（`:104-106`）；**无选项级 danger** |
| 档位 `level` | ✗ | ✗ | ✗ —— 载荷里**根本没这个字段**（`execution_layer.py:1754-1762` / `:2263-2270`） |
| **宽限期（防误触）** | ✓ `GraceGate`（`agent_runner.py:677-685`；`ui/ace_grace.py:33` 默认 200ms，`ACE_PERM_GRACE_MS` 可调） | ✓ `ui/ace_turn.py:212 _gate.admit` + 提示（`tui/app.py:1204-1207`） | ✓ **已补**（`core/ace_serve.ServeUIHost.ask_permission`，R-2）—— 三条路现在同一条口径 |
| 超时 | 无（阻塞 `input()`） | 600s（`tui/app.py:1187`） | 600s（桥侧 `core/ace_serve.py:461/472`） |

**结论**

1. **权限渲染器 = 3 份**。第 4 个候选（`ui/ace_dialog` + `ace_selector`）是 **REPL 的选择浮层**，
   不渲染权限请求 ⇒ S-2 的「权限对话框 ×4」**按字面不成立**。
2. 若把「向人请求**选择/确认**」也算同族，则共 **5 个渲染实现**（授权 3 + 选择 3 中的两个新面孔）。
   「同一职责写 2~3 遍」成立；「×4」是把 REPL 的**选择**浮层误算成了**权限**对话框。
3. **最完整 = Textual `PermissionScreen`**：唯一同时具备 tool + reason + 三态 + **选项级 danger 配色** + 备注输入 + **宽限期**。
4. **最弱分两轴**：表达能力最弱 = 终端 `ask_grant`（单行纯文本；tool/reason 靠调用方另行打印，
   且 `ai_code.py:5936-5938` 与 `agent_runner.py:831-833` **两处各打一遍**；`_ask_permission` 自身不打印任何东西）；
   **安全最弱 = Ink `PermissionDialog`（唯一没有防误触宽限期）**。
5. **对象是 `reason` 的搭车载荷**：`execution_layer.py:1747-1757` 把 `confirm_subject(tool_call)` 的预览
   塞进 `reason`（>300 字符截断 + " …"）—— H-28「确认框里没有对象」就是这么修的。
   ⇒ 对 WP-0 的含义：**对象没有独立字段**，任何改写/清空 `reason` 的路径都会连带丢掉对象；
   P-01 的对照表因此把"对象"标成**派生字段**，不是可独立搬运的字段。

##### P-02 · 工具卡 / spinner / 菜单

**工具卡 = 3 份（×3 成立，但落点不是"每个外壳各一份"）**

| 实现 | 落点 | 状态符号 | 耗时 | 输出折叠 |
|---|---|---|---|---|
| CLI 卡片 | `ui/ace_cards.py:296 tool_card()` | `:325 status_mark:218-236` → **✓/◌/✗/⚠（4 态）** | `:327-328` | `:339-343 collapse_lines`，默认 12 行（`:299`） |
| **看板（CLI + TUI 共用）** | `ui/ace_tools.py:93 ToolBoard` | `:48 DOT` = ○/●/✗ + running `:50 RUN_FRAMES ▁▃▅▇▅▃`（**另一套**） | `:184` | `:190-192` max_rows 兜底行 |
| Ink 卡片 | `frontend/src/components/ToolCard.tsx:42` | `:20-24 TOOL_GLYPHS` = ◐/✓/✗（**3 态、无 ⚠**） | `:63-65`（running 不显示） | `:111-115 firstLines(msg, 3)` |

> **看板不是 TUI 独有**：TUI 经 `board_provider`（`tui/app.py:697/706/865-873`，`ai_code.py:7275` 传入 `cli._board`）
> 渲染的是**同一个** `ToolBoard`。所以"×3"里的三份不是三个外壳各写一遍。
> 另：只读工具集 Python **14 个**（`ace_cards.py:42-46`）vs TS **7 个且名字不同**（`ToolCard.tsx:27`）——
> 而它是"成功不展开"的判据，分叉会让两边的折叠行为不同。

**spinner = 3 份（×3 成立；字形与速度**只有一份源**）**

| 实现 | 落点 | 阶段数 | 字形/速度来源 | 秒数 | 状态机 |
|---|---|---|---|---|---|
| 纯逻辑（**唯一来源**） | `ui/ace_spinner.py` | `:30-31` 5 个 | `:34-40`（0.08/0.24/0.12/0.10/0.16） | `:119-121` | 无（纯函数；stall 语义 `:74-104`，`DEFAULT_STALL_SECONDS=3.0` `:42`） |
| 动画线程 | `ai_code.py:1128 _Spinner` | 同 5 | 调 `ace_spinner.spinner_line` | 由它出 | phase / active_tool / `stalled` / `soft_stalled`（`:1151`）+ 文案防抖 |
| Ink | `render/spinner.ts` + `components/Spinner.tsx` | `spinner.ts:12` 5 个 | `spinner.ts:18-24` | `Spinner.tsx:63/69-74` | **无 stall**；`PHASE_VERB`（`Spinner.tsx:29-35`） |

> 对拍 `spinner.test.ts` **钉住的**：阶段集合、默认阶段、**每阶段 frames + interval**、单宽非 emoji。
> **没钉的（会各自漂）**：`stall_level` / `stall_color` / `DEFAULT_STALL_SECONDS`、`(无响应)` 文案、
> 动词表（`PHASE_VERB` vs `ace_layout.py:208-215 spinner_verbs`，TS 只自测自己）。

**补全菜单 = 2 个模型 / 4 个渲染宿主 ⇒ `ROADMAP` 的「菜单 ×3」也不成立**

| 实现 | 落点 | 候选来源 | 模糊匹配 | 窗口裁剪 | 说明列 |
|---|---|---|---|---|---|
| **Python 模型（唯一）** | `ui/ace_menu.py` | `:122-136` / `:139-160` / `:163-171` | `:248-266` 复用 `ace_selector.filter_items` | `:273-292` **黏边**（`sel - rows + 1`） | `:68-72` **只两个空格、不做列对齐**（`width` 参数收了但**没用**） |
| 自绘 / TUI 渲染 | `ui/ace_prompt.py:306`、`tui/app.py:941-942` | 同上 | 同上 | 同上 | 同上 |
| prompt_toolkit 浮层（活） | `ai_code.py:6553` → `:3807 build_menu` | 同上 | 同上 | 同上 | 同上 |
| **遗留 completer** | `ai_code.py:575 _build_slash_completer` → `:585 SlashCompleter` | **自己一套**（`:621`） | **纯前缀**（`:645`） | 无 | 无 |
| **TS 独立重实现** | `render/menu.ts` + `components/Menu.tsx` | `menu.ts:277` 等 | `render/match.ts` | `menu.ts:358-370` **居中**（`sel - h/2`） | `Menu.tsx:48-49/87-90` **两列**，labelW = 窗口内最长 + GAP2 |
| （不算）面板菜单 | `ui/ace_panel.py:108 menu_rows` | — | — | — | 主页/面板列对齐，**别混进这里** |

> **菜单模型没有任何跨语言对拍**：`menu.test.ts` **不读 Python 源码**
>（`readFileSync` 只出现在 theme / protocol / spinner / diff / tasktree / match / vim / text / i18n / launcher
> 这 **10** 个测试里 —— 与 §0.2 ① 的实测一致）。`match.test.ts` 只钉了 `match_score` / `SEPARATORS` / 排序。

##### P-03 · 「收 / 不收」清单（W0-B / W0-C 的**范围闸门**）

**要收**（同一个口径必须单一来源；括号里是当前的漂移形态）：

| # | 收什么 | 现状证据 | 状态 |
|---|---|---|---|
| R-1 | **权限三态选项集（含"危险档"）** | `ui/ace_turn.py:59-63` vs Ink 自抄 `PermissionDialog.tsx:32-36`（注释声明须对齐，**无断言**）；`session` 那档的 `danger=True` 在 Ink 侧**丢了** | ✅ 2026-09-27 |
| R-2 | **权限"必须有宽限期"这条要求** | 终端 ✓ / TUI ✓ / Ink **✅ 2026-09-27 已补**（`ServeUIHost.ask_permission`） | ✅ 已收（见上面「✅ 头号发现已修」；6 条 Python 断言 + 真引擎集成断言） |
| R-3 | **工具卡状态字形** | 三套：`ace_cards.py` 4 态 / `ace_tools.py DOT` 3 态 / `ToolCard.tsx` 3 态；**零对拍** | ✅ 三态对齐；`⚠` 缺口已**记账**（见下） |
| R-4 | **只读工具集**（"成功不展开"的判据） | `ace_cards.py:42-46` 14 个 vs `ToolCard.tsx:27` **7 个且 4 个名字注册表里没有** | ✅ 2026-09-27 |
| R-5 | **菜单窗口策略** | 黏边（`ace_menu.py:273-292`）vs **居中**（`menu.ts:358-370`）—— 同一种交互两种手感 | ✅ 2026-09-27（TS 改成黏边；**行为级**对拍） |
| R-6 | **菜单说明列的宽度** | Python 不做列对齐（`ace_menu.py:68-72`，`width` 收了不用）vs TS 两列 | ✅ 2026-09-27（两侧都对齐到同一条规则；**渲染级**对拍） |
| R-7 | **spinner 的 stall 语义与动词表** | Python 有 `stall_level`/`stall_color`/`DEFAULT_STALL_SECONDS=3.0` + 无动效时的 `(无响应)`（`ace_spinner.py:74-128`）；**Ink 侧完全没有 stall 判定**（`Spinner.tsx:61-74` 只有字形+动词+秒数） | 🔴 **能力缺口**（见下） |
| **R-8** | **菜单选中标记字形** | Python 用 `▶`（`ace_menu.py:319-321`，并注明"cp936 印不出 ▶"）；TS 用 `❯`（`Menu.tsx:83`） | ✅ 2026-09-27（**TS 三处改 `▶`**；依据是 Python 侧 **4:1** 的内部一致性，见下） |
| **R-9** | **菜单分组标题的格式** | Python `f"  {group}"`（`ace_menu.py:317`）；TS `'  ── ' + group`（`Menu.tsx:79`） | ✅ 2026-09-27（**Python 加 `── ` 前缀**；只收前缀，排版不收） |

> **R-8 / R-9 的决定依据（不是口味，是本仓的一致性证据）**
>
> | 语义 | Python 侧 | TS 侧（改前） |
> |---|---|---|
> | **列表选中** | **`▶`** —— `ace_menu:348` · `ace_selector:317` · `ace_dialog:324` · `ace_home:240`（**四处**） | `❯`（`Menu` / `ChoiceDialog` / `PermissionDialog`） |
> | **提示符 / 说话人** | `❯` —— `ace_cards:122`(user 前缀) · `ace_fullscreen:280/391` | `❯` —— `Input:268` · `Transcript:85` |
>
> ⇒ **R-8：TS 的"列表选中"改成 `▶`** —— 与 Python 的四处对齐，同时**修掉 TS 自己的内部不一致**
> （它把"选中"和"提示符"用了同一个字）。
> **如实记一个例外**：Python 的 `ace_panel.menu_rows`（主页/面板那份**编号菜单**，`❯ 1. 进入聊天`）
> 用的是 `❯` ⇒ Python 侧是 **4:1 而不是完全一致**。那一份语义更靠近"提示符列表"，**本卡不动它**。
>
> **R-9：只收前缀**。Python 的**设计版**分组标题是 `── 组名 ────`（`ui/ace_panel.section`，被主页/面板用着），
> `ace_menu` 里那个光秃秃的 `  group` 才是异类 ⇒ **给它加 `── ` 前缀**。
> **右侧补满不收** —— 那属于各外壳的排版（`THREE-LAYERS` **N-1**：同一份数据各自排版）。

**不收**（各自实现是对的，硬并会让协议承担排版）：

| # | 不收什么 | 成文先例 / 理由 |
|---|---|---|
| N-1 | **`status` 分段的最终排版** | `ace_events.py:41-47` 已定：引擎发**分段**，"有多宽只有前端知道"⇒ CLI 用 `fit_status_line`、前端用 `fitSegments`。**这是设计，不是重复** |
| N-2 | 工具卡的**视觉细节**（边框、颜色 token） | token 名已由 `theme.test.ts` 对拍；怎么画是外壳自由 |
| N-3 | 主页 / 面板的列对齐（`ui/ace_panel.py menu_rows`） | 与补全菜单**不是同一种东西**，混进来会把"×3"越数越乱 |

##### ✅ 批次 0 · 第一切片（2026-09-27）：R-1 / R-3 / R-4 三条已收并钉住

**手法**：新增 `frontend/test/shell-parity.test.ts`（9 条）—— 与 `theme.test.ts` / `spinner.test.ts`
同一套：**直接读 Python 源文件比对**。每条都先断言"解析成功"，否则解析一坏就会变成
"两边都空所以相等"的假绿（这个坑当场踩了一次，见下）。

**先红后绿**（先只导出常量、值照旧 ⇒ 看它红）：

```
× R-1 ★四项全一致        expected [ false, false, false ] to deeply equal [ false, true, false ]
× R-3 ★同一状态同一个字   expected '◐' to be '◌'
× R-4 ★两侧集合完全相同   expected [ 'file_glob', …(5) ] to deeply equal [ 'browser_screenshot', …(13) ]
× R-4 ★名字都真实存在     expected [ 'file_glob', 'file_grep', …(2) ] to deeply equal []
```

**改了什么**：

| 项 | 改动 |
|---|---|
| R-1 | Ink 的 `OPTIONS` → **导出 `PERMISSION_OPTIONS`** 并补上 `danger`；`session` 那档渲染成**告警色**（**未选中也看得出来**）—— 与 Python 的理由一致："一次真实的权力扩张，不该长得像'就这一次'" |
| R-3 | Ink 的 `running` 字形 **`◐` → `◌`**（`◐` 是 spinner 的，不是工具卡的）；`glyphs.test.tsx` 的 cp936 夹具补 `◌: 'o'`（反映引擎真实表） |
| R-4 | Ink 的只读集合改成**真实的 14 个**（删掉 `file_glob`/`file_grep`/`file_search`/`list_dir` 四个**注册表里不存在**的名字，补上 `search`/`search_read`/`terminal_view`/`kb_search`/`kb_list`/`skill_list`/`skill_load`/`goal_status`/`datetime_now`/`math_calc`/`browser_screenshot`） |
| R-3 缺口 | Python 的**第四态 `⚠`** 在 Ink 侧还没有对应状态 —— 由一条"**记账**"断言钉住：**缺口一旦被补上，那条会红**，逼人回来更新账本 |

> **R-4 是一处真缺陷，不是洁癖**：`search` / `search_read` / `terminal_view` / `kb_search` 是
> **最吵的几个工具**，而它们在 Ink 侧**不在**折叠集里 ⇒ 同一个操作在 Python 外壳里折叠、在 Ink 里刷屏。
> 而被写进集合的那 4 个名字**永远匹配不到任何东西**。

##### 🔎 收敛尝试顺手挖出的**引擎 bug**：`◌` 不在 `ASCII_FALLBACK` 里

为了对齐 R-3 去查两侧字形时发现：

- Python 工具卡的 `pending` 标记是 **`◌`**（`ui/ace_cards.py:233`）；
- 而 `core/ace_io.ASCII_FALLBACK` 里有 `◐`（spinner 那一套）**却没有 `◌`**；
- cp936 控制台上 `◌` 不可编码 ⇒ `glyph()` 走到 `ASCII_FALLBACK.get("◌", "?")` ⇒ **显示成 `?`**，
  且**不报任何错** —— 也就是说中文 Windows 上"执行中"的那张卡片一直是个问号。

**已修**：`ASCII_FALLBACK` 补 `"◌": "o"`。
**并加了守卫**（`test_all [33]`）：把**这些模块会画出来的字形**（`status_mark` 四态 +
看板 `DOT`/`RUN_FRAMES` + spinner 各阶段每一帧）全部与兜底表对一遍 ——
缺失即红。这条守卫先红后绿：`缺替身: ['◌']`（**只有它一个**，说明其余都齐）。

> 这类"画得出来但没替身"的字形，**没有任何现存断言会碰到** —— 它只能靠
> "把口径对齐"这件事顺手查出来，这正是 WP-0 的价值所在。

##### ✅ 批次 0 · 第二切片（2026-09-27）：R-5 已收 —— 这次是**行为级**对拍

`match.test.ts` 早就给出了更好的手法：**真调 Python**（`execFileSync` + `resolvePython()`，
失败则 `skipIf` 优雅跳过）。R-5 是纯函数对纯函数，正好用得上 ——
比"读源码文本"强得多：**同一组输入必须得到同一个输出**。

**先红**（把 `(total, selected, rows)` 的 33 个组合一起送进真 Python 比）：

```
× R-5 ★同一 (total, selected, rows) ⇒ 同一个可见窗口
     expected [ '(5,2,3) ts=[1,4) py=[0,3)', …(32) ] to deeply equal []
× R-5 策略本身写明了是**黏边**…
     expected '../../src/render/menu.ts 的 docstring' to contain '黏'
```

**33 例不同** —— 居中与黏边在"选中项不在两端"时必然分道扬镳。改法：**TS 采纳 Python 的黏边规则**
（Python 侧 docstring 写明了理由："滚动要黏，否则每按一下整屏都在跳"；且 4 个宿主里有 3 个走的就是它）。

**改完的验证**：`tsc` 0 · 前端 **21 文件 / 291 测试全绿**（+3 条来自 R-5）。
`menu.test.ts` 里原有的那 5 条窗口断言钉的是**不变量**（选中项可见、窗口不超高、遮挡数相加为总数），
**没有一条钉着"居中"** —— 所以换策略不必改任何旧断言，这件事本身也说明它此前**没被 pin 住**。

##### ✅ 批次 0 · 第三切片（2026-09-27）：R-6 已收 —— 而它教了一件事

`ui/ace_menu.MenuItem.line(mark, width)` 的 **`width` 参数收了却从来不用**，于是补全菜单从不做列对齐，
而前端那份做了两列 —— 同一份候选在两个外壳里排得不一样。改法：

| 侧 | 改动 |
|---|---|
| Python | 新增 `desc_column(labels)`（= 窗口内最宽标签 + `MENU_GAP`，按**显示列**算）+ `MENU_GAP = 2`；`MenuItem.line(mark, desc_col)` 让那个参数**真正生效**；`render_menu` 按窗口内的标签算列并传下去 |
| TS | 同一条规则抽成 `render/menu.labelColumn()` + `MENU_GAP`；`Menu.tsx` 改为调用它，并用 `padWidth`（按显示列补）替掉 `padEnd`（按码点补） |

**红 → 绿**（把 Python 的接线临时退回 `line("", 0)`）：

```
× R-6 ★**渲染结果**里"说明相对标签的偏移"两侧相同（规则真被用上了）
     expected [ '/help: ts=16 py=7', …(1) ] to deeply equal []
```

**这一条教了件事**：同一次运行里，**纯规则那条对拍是绿的** ——
`desc_column` 与 `labelColumn` 在五组标签上都给出同一个数。**规则一致，而两边都没在用它。**

> 所以"把规则抽成纯函数并对拍"**不足以**证明对齐成立；
> 必须有一条**渲染级**断言 —— 这正是本卡 §0.1 说的"纯函数测过 ≠ 画出来对"
> （`menu-render.test.tsx` 的头部也是这个教训）。R-6 三条断言里，
> **只有渲染级那条抓到了真问题**。

---

#### 🔴 R-7 是**能力缺口**，不是口径漂移（待决）

Python 的 spinner 有整套 stall 语义：`stall_level(idle, threshold)` 0→1 渐变、
`stall_color(level, truecolor)`（真彩平滑插值 / 低色深过半离散跳告警色）、
`DEFAULT_STALL_SECONDS = 3.0`、`active_tool=True` 时**不判**（"一条长命令跑 60 秒是正常的，
把它染成告警色只会教用户忽略颜色"），以及**无动效**时用文字 `(无响应)` 代替颜色动画。

**Ink 侧完全没有这一层**：`Spinner.tsx:61-74` 只有字形 + 动词 + 秒数。

⇒ 这跟 **R-2（Ink 无宽限期）** 同类：不是"两边写得不一样"，而是**主外壳少了一层能力**。
补齐它需要：阈值与渐变口径、i18n 化那句 `(无响应)`（它现在是**硬编码中文**，三语得一起加）、
以及"有活跃工具时不判"的判断（前端得知道工具在跑 —— 那正好是 `store` 里已有的 `tool_running` 阶段）。

**本卡不擅自补** —— 它要么是一张新卡，要么明确记成"这一层只做在 Python 外壳里"。

**另有两条不属"收敛"而属"**先把事实改对**"**（承诺与现码同口径）：

- `ToolCard.tsx:7` 声称"`test/` 里有一条断言把两边钉在一起" —— **实际上没有**
  （`glyphs.test.tsx` 只钉 cp936 降级后的字，不读 `ui/ace_cards.py`）。补断言，或改注释。
- `ai_code.py:3962-3964` 声称"协议前端那条的宽限期在 `core/ace_serve.ServeUIHost` 里" —— **实际上没有**（见下）。

##### ✅ 头号发现已修（2026-09-27）：协议前端那条路补齐了宽限期

**原先的事实**（留档，因为它是这条断言的由来）：

| 路 | 宽限期 | 证据 |
|---|---|---|
| 终端问答 | ✅ 有 | `agent_runner.py:677-685` → `ui/ace_grace.GraceGate`（默认 **200ms**，`ACE_PERM_GRACE_MS` 可调，上限 5000） |
| 组件界面（Textual） | ✅ 有 | `ui/ace_turn.py:212 _gate.admit` + 提示（`tui/app.py:1204-1207`） |
| **协议前端（Ink，声明的主外壳）** | ❌ **没有** | `core/ace_serve.py:467-484` 只有 `wait_for(..., timeout=600s)` —— 那是**超时**不是**宽限期**；前端侧 `frontend/src` 全域 `grace` 只出现在 `client.ts:197` 的**关闭**超时 |

而 `ai_code.py:3962-3964` 的注释**明说**"协议前端那条的宽限期在 `core/ace_serve.ServeUIHost` 里"。
⇒ **H-32 那一类**（承诺与现码不同口径），而且落在**安全侧**：宽限期存在的理由正是
"对话框刚出现那一瞬飞过来的回车不算数"（`tui/app.py:1155-1160` 的原话）。

**选的是出路①（补闸门）**，理由：宽限期存在的**理由**对 Ink 同样成立 ——
"声明的主外壳是三条路里唯一没有这层保护的"不是取舍，是缺口。

| 改动 | 位置 |
|---|---|
| 闸门与重问循环 | `core/ace_serve.ServeUIHost.ask_permission`：`GraceGate` → 判为飞行按键则**不采纳** → `notice` 说清原因 → **重发请求** → 用尽 `MAX_DISCARDS` 后采纳 |
| 提示文案 | `ai_code.py` 构造 `ServeUIHost` 时传 `grace_hint=t("grace_inflight")`（**与终端同一个 i18n 键**，三语早已齐全） |
| 可测性 | `ServeUIHost(..., grace_ms=)` 可显式传入（`None` = 读 `ACE_PERM_GRACE_MS`），测试不必去改环境变量 |
| 那条注释 | 改成**真话**，并把"第二句此前只兑现了两条路"写进去 —— 注释不许再替代码承诺 |

**为什么必须重发请求**：多数外壳在作答时就把对话框收起来了。只丢弃不重发，用户会看到
"我答过了、界面却没了"，然后一直等到 600s 超时 —— 那比不做保护更糟。

**算术与终端逐字一致**（`MAX_DISCARDS = 2`）：**N 次丢弃 → N−1 句提示**，
因为最后一轮的丢弃同时用尽了次数、那一轮直接采纳 —— 这是"别把自动化喂输入永久挡在门外"的出口。

**红 → 绿**（`frontend/test/integration.test.ts`，**真引擎**）：
第一版断言 `perms.length > 1` 因为**错误的原因通过**了（mock 剧本本来就有多次审批），
红只红在提示缺失 ⇒ 改成**次序**判据：`permission_request` → 飞行按键提示 → 之后才可能"已临时授权"。
`test_all [61]` 另加 **6 条**确定性断言（假 server + 可注入的 `grace_ms`），
其中一条专门钉"**改写这个循环没有破坏 fail-close**：拿不到答案 → deny"。

> **顺带清掉一个真环境问题**：早期几次全量失败留下的 `mkdtemp` 目录（25 个）
> 会让**受限沙箱**无法给工作区重授写权限 —— 表现是之后**每条受限命令**都
> `SetNamedSecurityInfoW failed (Win32 5)`。所谓"删不掉"只在受限模式下成立：
> 完整权限下一次 `Remove-Item -Recurse -Force` 全部清干净（25/25）。

**W0-A 验收（2026-09-27）**：

#### ✅ 同批的 `RL-01`（结果信封）也已落地 —— 见 `THREE-LAYERS.md` §9

`ROADMAP` §7.1 的 **C1** 说 `RL-01` 必须与本卡**同批**（"同一份数据的两端"）。它已实施：
`tools/status.outcome_for` 是"拒绝 vs 失败"的唯一判定处，`ExecutionResult` 的五个正交字段
（`outcome`/`refusal_class`/`retryable`/`fingerprint`/`hint`）**自动补**（250+ 个构造点一个都没改），
`outcome` 已流到**外发事件**与**账本**两处，TS 类型也已登记。

**四个外壳目前还没有消费者** —— 字段到了，用途还没到（那正是本卡 W0-B / W0-C 的活）。
`test_all [36]` 有 **8 条** RL-01 断言，其中两条是**端到端差分对**：
同一个 `status='error'`，403 落 `denied`、404 落 `failed`。

- ① ✅ **P-01~P-03 的清单进本卡**（上面三张表 + "收 / 不收"清单 + 头号发现）；
- ② ❌ **"第 5 份权限对话框出现就红"的断言没做** —— 本卡按自己写的"**退一档**"如实标注：
  这一档**只做了清单 + 人工复核，没有断言钉住**。
  理由：那条断言需要一份**机器可读**的"实现名单"（含每份的**角色**），而现在这份名单是
  人写的 Markdown 表；先把它变成数据（像 `core/ace_contracts.py` 那样一张声明表）再挂断言，
  才是同一种纪律 —— **拿正则去刮 Markdown 是假钉**。
  落点已定：**挂在既有的 `[38]`**（文档/仓库结构一致性）旁，等名单数据化之后一起做。

---

### W0-B · 协议侧：把"消费者需要的东西"变成契约

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| **P-04** | `status` / `tool_start` 两条"驱动 UI"的契约要被外壳**真正消费** | `ace_events.py:41-47` 已规定 `status` 发分段 + `level` 上色，且 `name == "permission"` 那一段由前端按 `meta.permission` 决定三档色 | 补一张"哪些外壳已消费 `status` / `tool_start`"的实测表；未消费的列出缺口 |
| **P-05** | 事件**必需字段**的唯一来源 | `ace_events.EVENT_REQUIRED`；`test_all.py:7491` 已有"`EVENT_TYPES` ↔ `EVENT_REQUIRED` 键集相等"的断言 | 新增字段必须**同时**进这两处；新事件必须先登记（登记是纪律，不是文档） |
| **P-06** | 前端协议消费者与 Python 契约的漂移 | `frontend/src/protocol/types.ts`(230) 是手抄的 TS 镜像；钉住它的是 `frontend/test/protocol.test.ts`(66) | 新事件必须**同时**补 `types.ts` 与 `protocol.test.ts`，否则 parity 测试红 |
| **P-10** | **"让用户自己输入选项"打通**（`ROADMAP` §3.3 的 **① 与 ② 归本卡**） | 协议侧**已经**支持：`choice_request.kind` = `choose / confirm / text`（`ace_events.py:20` 与 `:79`），发射点 `core/ace_serve.py:521`。丢的是**外壳侧**：`ai_code.py:4000` `return list(items).index(str(picked))`（**拿 label 当答案**）与 `ui/ace_dialog.py:367` `labels = [it.text() for it in selectable]`（**丢 key**） | 4 个外壳统一回传 **key** 而不是显示文本；`kind='text'` 的回传路径逐外壳打通；与 `WP-1` 的 `ask_user` 工具（G-04）共用这条通道 |

**W0-B 验收**：`python test_all.py` 的 `[38]`/`[39]` 全绿 + `cd frontend && npx vitest run` 里
**10 个** parity 测试全绿；`PROTOCOL_VERSION` 不变；`kind='text'` 的回答在**每个外壳**上都能回传到 `ai_code`（P-10）。

---

### W0-C · 外壳侧：`frontend/` 定为主外壳，`ui/` + `tui/` 降为 fallback

| ID | 事项 | 改法形状 |
|---|---|---|
| **P-07** | 路由声明**单一来源** | "谁是主外壳"今天散在 `ace.cmd:59-86`（Node 在不在 ⇒ 派发）与多份文档的散文里（`ARCHITECTURE.md:239` 的 `M-27 已有（唯一正式外壳）`）。落成**一处**可读判定 + 一条断言 |
| **P-08** | `ui/` + `tui/` 冻结 | 加"只修 bug 不加功能"的显式标记（`ui/__init__.py`(1) / `tui/__init__.py`(22) 是天然落点），并让"新功能只在 `frontend/` 落"可复核 |
| **P-09** | 回落必须**说出缺了什么** | **已实现**（`ace.cmd:66-77` 分别报 Node 缺失 / `node_modules` 未装）。本卡不改它，只把它**写成契约不许回退** |

**W0-C 验收**：重复对话框合一后 `python test_all.py` 全绿 + 10 个 parity 测试全绿；
`ace.cmd` 的两条回落路径**各有一条断言**（"缺 Node" / "缺 `node_modules`"）。

---

### W0-D · 打包口径（R-3，**批次 0 的出口**）

三条出路，**必须选一条写进文档**（不许留着"以后再说"）：

| 选项 | 代价 | 结果 |
|---|---|---|
| **D1 带源码 + `node_modules`** | 发行包要装 `node_modules`（`frontend/.gitignore` 明确排除，几万文件），且用户仍需 Node ≥18 | 与 `ROADMAP` §2.7 **硬契约 3**"终端用户不需要工具链"**冲突** |
| **D2 引入真正的打包**（bundle + 内嵌运行时） | 新增一条构建链；§2.7 硬契约 3 要求**复用既有通道、不新开** | 唯一能让 exe 用户真正看到 Ink 外壳的路 |
| **D3 明确"exe 只带 Python UI"** | 零成本，但要把这句话写进 `docs/PACKAGING-EXE.md` 与 README | **本卡默认推荐**：先把诚实的边界写清楚，再谈 D2 |

**W0-D 验收**：`docs/PACKAGING-EXE.md` 里有一句**可断言**的话（"冻结形态下能否起 Ink 外壳 = 是/否"），
且 `packaging/ace.spec` 的 `datas` 与那句话**一致**。

#### ✅ 已定（2026-09-27）：选 **D3**，并落到两处 + 两条断言

| 落点 | 内容 |
|---|---|
| `docs/PACKAGING-EXE.md` | 「冻结后不成立的东西」表新增 **Ink 主外壳（`frontend/`）= ❌ 不进包** 一行；新增一节「Ink 主外壳不进包（打包口径 **D3**）」：三条实测理由 + D1/D2/D3 的取舍表 |
| `packaging/ace.spec` | docstring 的「不再成立」清单里加一条（**用 ASCII 写** —— 该文件第 9 行自己规定"不用非 ASCII 字符"，见下面那条顺带发现） |
| `test_all [10]` | **两条断言**：① `datas` 不含 `frontend/`；② 这个边界**两处都写着**（spec docstring + 文档）。写一处忘一处、或往 `datas` 里加了 `frontend/` 却没改文档 ⇒ 当场红 |

**D2 的关键点（决定之前必须知道，已写进文档）**：把 TS 打成 bundle **只去掉 `npm install`，
去不掉 Node** —— 打包 JavaScript 不会产生 JavaScript 运行时。要真让 exe 用户跑上 Ink，
得引入**单文件运行时**（Node SEA / `pkg` / `bun build --compile`），那是一条**新的跨平台产物链**
（每平台一份 + 校验 + smoke）。所以 D2 不是"顺手补一下"，而是一次**新的分发决策**；
在它被单独决策之前，D3 是唯一诚实的口径。

> **顺带发现（未处理，留给作者）**：`packaging/ace.spec` **没有 BOM**（实测前 3 字节 `23 20 2D`）
> 却**含非 ASCII 字节** —— 它的中文 docstring 正是它第 9 行警告的那件事
> （"无 BOM 的 UTF-8 被按 ANSI 读"，见 `CHANGELOG v3.40.2` / REL-03）。
> 两条路：给它加 BOM，或把那段理由搬进 `PACKAGING-EXE.md` 让 spec 真的只剩 ASCII。
> **本卡不替你选**，所以我的补充写成 ASCII，不加深那个风险。

---

## 3. 与其它卡的关系

| 卡 | 关系 |
|---|---|
| `THREE-LAYERS.md` **RL-01** | **同源**：该卡 §7 原话 —— "给机器的结构与给前端的事件**是同一份数据**"。两张卡必须在同一批改，否则 `ExecutionResult` 的新字段（`outcome`/`class`/`retryable`/`hint`/`fingerprint`）会**漏给外壳** |
| `THREE-LAYERS.md` RL-03 / TH-R5 | RL-03 的三段式回传直接减轻外壳渲染压力；TH-R5 已写明"只做**正交新增**字段，配合 WP-0" |
| `ROADMAP` §6 **ACC** | W0-A 的"新增断言"会**产出新指标**（重复实现数）——按 ACC-02 的指标语义契约报（`Metric`/`Anchor`/`Population`/`Excludes`/`Reads as`）。**本卡按 ACC 的形状设计这条指标**，即使 ACC 卡尚未开工 |
| `BACKLOG.md` **REL-09**（已闭环） | 主前端进 CI 是它的成果（`ci.yml:243`）；W0-B / W0-C 的验收**建立在它之上** —— 没有 CI 里的 vitest，10 个 parity 测试就只是"本机的事" |
| `SAFETY-HARDENING.md` **H-31**（已闭环） | 集成测试不再写开发者真实仓库，是 REL-09 的前置 |

---

## 4. 风险

| # | 风险 | 缓解 |
|---|---|---|
| **WP0-R1** | **动全部 4 个外壳**，回归面最大（= `ROADMAP` R-1） | 分批迁移，每批**保持旧路径可用**；10 个 parity 测试会立刻抓到不一致 |
| **WP0-R2** | **"收敛"做过头的风险**：把"同一份数据各自排版"也合并，等于让协议承担排版 | W0-A 的 **P-03 清单是范围闸门**：先判"收/不收"，再动手；`ace_events.py:41-47` 是"不收"的成文先例 |
| **WP0-R3** | **对拍测试被"改绿"而不是"改对"** | 验收要求**改之前先看着它红**（沿用 `CONFIRM-BOUNDARY` W0 的做法） |
| **WP0-R4** | 打包三选一被拖成"以后再说" | W0-D 是批次 0 的**出口条件**：不落定，批次 1 不许开工（`ROADMAP` §7：批次 1 依赖批次 0 的前端部分） |
| **WP0-R5** | 十个 parity 测试里有 2 个（`text` / `i18n`）不在 `ROADMAP` 的验收清单里，容易漏 | §0.2 ① 已点名；W0-B 验收写 **10 个**而不是 8 个 |
| **WP0-R6** | **"重复计数"本身没有来源**（×4/×3 无文件清单），改完无法证明变好了 | W0-A 先点名、再计数；完成前后各留一次实测数 |

---

## 5. 开工检查单

> 本卡的**批次位置已定**：`ROADMAP` §7 **批次 0**，且与 **`RL-01` 同批**（§7.1 **C1**）。

- [ ] **批次 -1 闸门先过**（`ROADMAP` §7.2）：W0-A 清单 + **W0-D 打包口径落定** + **G6 凭据不落地**（§3.3 ③，须单独立卡）
- [ ] **W0-A 的 P-01~P-03 清单完成**（没有它不许动代码）
- [ ] §0.2 三处与 `ROADMAP` 的差异已确认（尤其"8 个 → **10 个**"与 W0-D 的三选一）
- [ ] **`RL-01` 与本包同批开工**（`C1`）—— 否则 `ExecutionResult` 的新字段会**漏给 4 个外壳一次**
- [ ] 每个工作包一个可独立回滚的提交
- [ ] `ruff` + `py_compile` + `python test_all.py` + `cd frontend && npx tsc --noEmit && npx vitest run` 全绿
- [ ] 完成时登记 `CHANGELOG.md` → push
