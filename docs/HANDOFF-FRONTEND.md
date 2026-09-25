# 交接：TypeScript + Ink 前端（`frontend/`）

> 用途：把下面「可直接粘贴的提示词」整段复制到另一个对话（或另一个 agent 会话）里执行。
> 这一份是**自包含**的：接手的人不需要读任何聊天记录，也不需要问任何问题。
> 格式沿用 [`HANDOFF-R-03.md`](HANDOFF-R-03.md)。

---

## 一、背景（给接手的人）

项目 ACE 原本只有一套表现层：`ui/`（Python 手写 ANSI）+ `tui/`（可选 Textual）。
新增了第三套：**`frontend/`（TypeScript + Ink）**，作为**主路径**，与 Python 那套**并存**
（Python 侧退居回退）。

为什么是独立进程：引擎是 Python，前端是 Node。两者间**必须有条管道**。
真正的理由只有一个 —— **审批对话框是双向的**：引擎需要一个答案时会**阻塞**等回传
（`execution_layer.py` 从不读 stdin、不持有回调，它只维护 `pending_permission` 并返回状态码）。
单向的事件流做不了这件事。

协议形体照 `docs/ADR-002-executor-boundary.md` 里已论证过的 Go 执行器那套：
`v=1` / `req`·`resp`·`event` / `id` 相关 / `seq` 单调（丢帧检测）/ `initialize` 握手。

**启动方式**：`ace` → 新的 Ink 前端；`ACE_LEGACY_UI=1 ace` → 老的 Python REPL。

## 二、当前状态（接手前必须知道）

### 2.1 什么都没提交

工作树里全部是**未提交改动**：

```
 M ace.cmd  ai_code.py  core/ace_events.py  docs/ARCHITECTURE.md
 M locales/{zh,en,ja}.json  test_all.py
?? core/ace_serve.py  frontend/
```

**`frontend/` 还没进版本库** —— 所以 `test_all.py --only 38`（权威树校验）目前仍绿，
它用 `git ls-files` 读已跟踪文件。**`git add` 之后那条会开始看 `frontend/`**，
届时需要确认树里已登记的 `frontend/` 条目足够（现在是一行，未展开子项 ——
因为展开后 `[38]` 会要求把每个直接子项都登记上，而 `package-lock.json` 之类会漂）。

### 2.2 环境陷阱（踩过，浪费过时间）

- **裸 `python` 是失效的 Microsoft Store 执行别名存根**：不报错、无输出、退出码 49。
  可用的是 `C:\aider_env\Scripts\python.exe`（`ace.cmd` 硬编码优先探测它）。
- 跑测试要带 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`，否则中文输出变乱码。

### 2.3 既有失败基线（**不是**你弄坏的）

改动前先认清基线，否则会把"本来就这样"误判成自己弄坏的：

**Python 全量 2113 项里有 5 条既有失败**（本机环境相关）：

- 菜单渲染：带分组、选中标记与按键提示（段 `[53]`）
- `[65]` 强度：符号一眼可辨（○ ◐ ● ◉）
- `[65]` 主页：渲染出选中标记与分区标题
- `[66]` 补全：渲染的是窗口（含选中项）
- `[66]` 浮层真按键：连按 8 次 ↓ 选中项始终可见

**`demo/record_demo.py --check` 有 1 处既有失败**：`demo_landing.svg` 第 69 行 ——
录制的是 `▶ 继续上次`，本机渲染成 `> 继续上次`（`core/ace_io.py` 的代码页字形降级）。
另外三张一致。

判定方法（**别靠推测**）：

```bash
git stash push <改过的文件>
<跑那批测试或 demo --check>
git stash pop
```

两边跑出**字面相同**的失败 → 既有。注意**全量测试跑动期间不要 stash** ——
它会 spawn `ai_code.py` 子进程，中途换文件会污染那一轮结果。

## 三、已完成的部分

前端一套独立测试（vitest），**当前 247/247 全绿**；Python 全量 **2140/2145**
（即 2145 减去上述 5 条既有失败，**本批 0 新增**）。

已实现：`/` 补全菜单 · diff 上色 · 选择器 · 主页 · 任务树 · 键位/vim ·
**首屏横幅**（logo + 身份 + 环境）· **显示宽度**（`render/text.ts`，对齐 `ui/ace_text.py`）·
**跨会话引用 `@session`**。

### 3.0 引擎侧同时做的事（与前端配套，别漏看）

- **命令表 50 → 59**：新增 `/compact` `/context` `/plan` `/btw` `/rename`
  `/recap` `/export` `/cd` `/agents`。三张表（`COMMANDS` / `COMMAND_HANDLERS` /
  `COMMAND_GROUPS`）必须同步 —— 有自检会报"只在 COMMANDS 不在 HANDLERS"和"未分组"。
- **协议新增方法**：`home.request` `tasks.request` `config.request` `sessions.request`
  `choice.answer`（见 `core/ace_serve.py` 与 `ai_code._run_serve` 的注册处）。
- **配色口径改了**：`frontend/src/theme/tokens.ts` 现在返回 **chalk 色名**（`yellow` /
  `cyanBright`…），**不是十六进制**。第一版转成了 xterm 默认 16 色 hex，后果是黄色变
  橄榄绿、提示符一片绿、而且所有颜色不再跟随用户的终端主题。改回去之前先读那段注释。

### 3.1 协议（`core/ace_serve.py`）

双向 NDJSON 服务端 + `ServeUIHost`。

**关键设计决定（别改回去）**：审批、选模型、确认、文本输入这四类"问人"的接口，
是**通过 `attach_ui(host)` 一处接上的**，不是散在各调用点加 `if serve` 分支。
CLI 里十几处调用点因此一行未改。把协议前端实现成 host 的形状，与组件化全屏界面
（`tui/app.py`）完全一致。

拿不到答案时**一律保守**：授权 fail-close 拒绝、选择返回 None（= 取消）、
确认返回 False（= 否）。没人回答时，「不做」永远比「替他做」安全。

### 3.2 跨语言一致性靠测试钉住，不靠人记得同步

前端有一批测试**直接读 Python 源码做比对**，因为那些数据两边必须逐字一致：

| 测试 | 比什么 |
|---|---|
| `theme.test.ts` | 17 个语义 token 的**名与值** ↔ `ui/ace_theme.py` |
| `protocol.test.ts` | 事件类型集合 ↔ `core/ace_events.EVENT_TYPES`；审批三态 ↔ `agent_runner.GRANT_*` |
| `spinner.test.ts` | 字形序列与帧间隔 ↔ `ui/ace_spinner.py`（**速度本身是语义**） |
| `diff.test.ts` | diff 判据与统计 ↔ `ui/ace_diff.py` |
| `tasktree.test.ts` | **逐行**渲染结果 ↔ `ui/ace_layout.render_task_tree` |
| `match.test.ts` | **调真 Python** 算 18 组评分逐一比对 |
| `vim.test.ts` | **差分测试**：71 条用例同时喂给 Python 与 TS |
| `launcher.test.ts` | `ace.cmd` 的调用形态 + CRLF/纯 ASCII 两条硬约束 |

**所以：改 Python 侧会让这些用例红 —— 那是设计如此，不是脆弱。** 跟着改前端。

改 `ace.cmd` 时注意两条硬约束（它的头部注释里写着）：**必须纯 ASCII**（cmd.exe 按字节
偏移定位，多字节字符会让它从行中间重读）、**必须 CRLF**。用字节级脚本改，别用编辑器。

### 3.3 已修的真实缺陷（别改回去）

1. **事件在订阅前丢失** —— 引擎的 `session_start` 在进程启动时发，比界面挂载早；
   事件流没有重放。`AceClient` 有事件缓冲，首个订阅者到来时按序补发。
2. **关闭时硬杀进程** —— 收到 shutdown 的 resp 就 `kill()` 会把 `atexit` 的收尾砍掉
   （`session_end`、**MCP 子进程回收**、会话日志 flush）。现在是"关 stdin 等它自己退，
   超时才强杀"。
3. **粘贴后立刻回车会丢内容** —— 按键闭包捕获的是异步 state。`Input` 用 ref 做真值来源。
4. **非 TTY 下抛 React 堆栈** —— 现在是清楚的提示 + 退出码 2。
5. **`ace.cmd` 从仓库根调 tsx** —— tsx 从**当前目录**找 `tsconfig.json`，找不到就退回
   经典 JSX 转换，第一次 `render()` 就 `React is not defined`。现在 `pushd frontend` 再调。
6. **主页条目的 `fmt` 没发** —— 条目文案里有 `{when}`/`{turns}` 这类占位符，漏发参数
   前端只能把花括号原样打出来。**不报任何异常**，只是文案读起来是断的。
   （协议里已补 `fmt`，`test_all.py [69]` 有守卫。）
7. **首屏身份说了两遍** —— 横幅与主页各打了一行模型/权限。首屏重复"一眼要确认"的
   信息等于把真正的新东西挤下去。现在身份与环境归横幅，主页只留可操作条目。
8. **主页「继续上次」的时间和首句一直是空的** —— `_sessions_brief` 读的是
   `summarize()` 的 `when` / `first`，而它**从来不产出这两个键**（给的是
   `first_user` / `last_assistant` / `turns` / `root` / `project`）。不报任何错，
   只是那两栏空着。已对齐 `/sessions` 的做法（`label(evs, p.stem)` +
   `format_when(mtime)`）。**这条改了首屏输出，`demo_landing.svg` 因此过期。**
9. **主页条目的占位符原样上屏**（`{when}{turns}`）—— 协议漏发 `fmt`。同类错误
   （不报错、只是文案残缺）在 `[69]` 有守卫。
10. **`/compact` 会把短对话"压"了，而且压完更大** —— 强行把触发线设成 0 时
    **跳过了"值不值得压"那一关**：两三条消息没有可摘要区间，于是走硬截断，
    token 从 30 涨到 52（用一条摘要顶掉两条短消息），内容还白丢。
    现在先问一次 `plan_compaction`，没有可压区间就什么都不动。
11. **`/rename --clear` 清不掉名字** —— `label()` 从后往前找**非空**的 rename，
    跳过了最后那条空的、又捡起更早的旧名字。语义是「最后一条 rename 说了算，
    哪怕它是清空」。

> 以上 8–11 有一个共同点：**都不报错，只是行为不对**。改动时优先怀疑自己新加的逻辑，
> 而不是被测物 —— 这轮里我三次以为是测试写错了，两次确实是测试、两次是代码。

### 3.4 两块"别手抄"的数据

`frontend/src/render/logo.ts` 与 `render/text.ts` 里的 `WIDE_RANGES` **都是生成出来的**，
不是手写：

- **logo** 由脚本从 `ai_code.ACE_LOGO` 提取（手抄过一次，某个块状字符少一格、整块图形歪掉）；
- **W/F 码点区间**由脚本从 Python 的 `unicodedata` 生成。第一版手抄**抄窄了 emoji、
  抄宽了带圈数字** —— `test/text.test.ts` 的码点差分（6.8 万个）当场抓出来。

改这两处请改上游（Python 那侧）再重新生成，别直接编辑生成物。

## 四、未完成 / 未验证（**接手的人从这儿开始**）

1. **`ui/ace_keys.py` 的用户自定义键位没做。** 「用户覆盖 + 冲突警告」那套系统没有移植 ——
   只做了 vim 和一套内置绑定。`/keys` 的说明表也还是 Python 侧的。
2. **六项的视觉效果一次都没被人眼看过。** 开发环境没有 TTY，Ink 起不来。
   测试覆盖的是逻辑、协议、跨语言一致性；**排版、配色、vim 的光标/模式显示
   全部未经视觉验证**。这是接手后的第一件事。
3. `model_delta` 的**发射点没接**（schema 已登记，`initialize` 的 `stream` 开关也已接，
   但引擎侧还没有地方真的发出增量）。
4. `status` 事件同样只登记了 schema，没有发射点。
5. `/lang` 切换后主页/菜单**要重渲染才生效**（发的是 i18n 键，前端自己查字典；
   目前没有在收到语言变更后主动刷新）。
6. Phase 4 未做：前端**没有进 CI**。`.github/workflows/ci.yml` 目前只跑 Python。

## 五、验收标准（缺一不可）

1. `cd frontend && npx tsc --noEmit` → 零错误；
2. `cd frontend && npx vitest run` → 全绿（当前 214 条，只允许因**新增**而变多）；
   **不允许出现 skipped** —— 跳过就是假绿；
3. `python test_all.py` → **2108/2113**（只允许因新增断言而变多；那 5 条是既有失败，
   见 §2.3）；
4. `ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` → 零命中；
5. `python demo/record_demo.py --check` → 与改动前**相同的**结果（那 1 处既有失败不算）；
6. `ace.cmd` 保持纯 ASCII + CRLF（`test_all.py --only 38` 会查）；
7. **不升版本号、不重录演示图、不动 `CHANGELOG.md` 与 README 徽章**；
8. Python 侧的权限/审批三轴、执行层 14 阶段管线、`ERROR_STATUSES` 语义**不许改**。

---

## 六、可直接粘贴的提示词

> 接手 ACE 项目的 TypeScript + Ink 前端（`frontend/`）。先读 `docs/HANDOFF-FRONTEND.md`，
> 它自包含，不需要额外的上下文。
>
> 从「四、未完成 / 未验证」开始：第一件事是**在真终端里跑 `ace` 看一眼实际渲染**
> —— 那六项功能的视觉效果至今没有任何人验证过（开发环境没有 TTY）。
> 然后按 §2.3 认清既有失败基线，再动手。
>
> 注意：工作树里全是未提交改动，`frontend/` 还没进版本库。
> 改动前先跑一遍 §五 的验收清单建立基线。
