# ACE v3.27.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3270-2026-09-19)。无破坏性变更。

## 一句话

交互体验专项：**补全菜单不再依赖第三方库**、**打全的命令一次回车就跑**、**一次探索不再刷几十张卡片**。

## 菜单：没装依赖也有，装了更好

以前补全菜单只活在 `prompt_toolkit` 里 —— 依赖没装（或装在另一个解释器上），你看到的就是一个光秃秃的输入行：没有菜单、没有历史、没有提示。现在菜单是一份**模型**（候选从哪来、怎么排、回车干什么），两条渲染路径共用：

- 装了依赖：prompt_toolkit 的浮层菜单（原来的体验）
- 没装：标准库实现的输入行，菜单/历史/行编辑/快捷键一样不少，只是不画浮层

依赖缺失时的提示也改了：直接给你一条能复制的命令，并说明内置菜单已经可用。

## 回车：打全了就跑，没打全才补

- 候选**会改变**你输入的内容 → 先补全（不发送）
- 候选和你打的**一致**（`/help` 已经打全）→ **直接发送**

旧行为是"斜杠命令第一次回车只弹列表、第二次才发"，于是打全一条命令也要按两次回车 —— 这正是"僵硬"的来源。

## 菜单里现在有参数提示

`/permission` 后面要填什么，不用去翻 `/help`：

```
❯ /permission
  ▶ readonly   只读（默认，最安全）
    write      可写（改动前快照）
    full       完全（含沙箱边界外的动作）
    rules      编辑会话级授权规则
```

`/sandbox d` 这样的模糊输入也能命中 `docker`；参数选好之后菜单自动让位，回车直接发送。

## 一次探索，一句话

连续的读文件/检索/列目录**成功时不再各打一张卡片**，收尾汇总成一行：

```
⚙ 4 次工具调用 · 1.20s · 读取 3 项 · 检索 1 次
```

失败的读**照旧打出来**（出错的读必须看得见），写/执行类操作永远单独显示 —— 折叠只吃掉"读到了"这种没有信息量的行。

## 等待时看得出"在动"，也看得出"卡了"

- 状态行前 2.4 秒说准确状态（"思考中"），之后轮换动词（分析中/推演中/核对中…）
- 3 秒没有新进展给一个安静标记，45 秒明说"可 Ctrl+C 中断"
- 工具阶段带上工具名：`正在调用 file_read`（比"正在调用工具"信息量大得多）
- `reduce_motion` 配置或 `ACE_REDUCE_MOTION=1`：不轮换、不逐帧刷新（录屏/终端复用/无障碍）

## 顺带修掉的两个真错

1. `Esc` 后面紧跟回车时，"转义序列前瞻"会把**回车吃掉** —— 于是"Esc 关菜单、再回车"被当成输入结束
2. 在历史最新一条按 `↓` 会把历史灌进输入框

## 📋 兼容性

- 无破坏性变更；新增 27 个 i18n 键（中英日各 489 键对齐）；新增测试段 `[53]`（40 项断言，含真 CLI 管道端到端）
- 这一版**没做**：权限对话框的编号直选与"拒绝时附反馈"、折叠组的进行中实时说明、通知区、全屏历史视图（`Ctrl+E`）—— 都在待办里，下批继续

---

# ACE v3.27.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3270-2026-09-19). No breaking changes.

## In one line

An interaction-focused release: the completion menu **no longer depends on a third-party library**, a fully typed command **runs on one Enter**, and one exploration **no longer prints dozens of cards**.

## The menu: works without the dependency, better with it

The completion menu used to exist only inside `prompt_toolkit` — without it (or with it installed for a different interpreter) you got a bare prompt: no menu, no history, no hints. The menu is now a **model** (where candidates come from, how they rank, what Enter does) shared by two renderers:

- with the dependency: the prompt_toolkit overlay (as before)
- without it: a standard-library input line with the same menu, history, line editing and hotkeys — it just does not paint an overlay

The missing-dependency message now gives you one copy-pasteable command and says the built-in menu is already available.

## Enter: run it if it is complete, complete it if it is not

- the highlighted candidate **would change** your input → complete it (do not send)
- the candidate **equals** what you typed (`/help`) → **send it**

The old behaviour was "first Enter only previews the list, second Enter sends", so a fully typed command still needed two presses — exactly the rigidity you noticed.

## Argument hints are in the menu

`/permission` now shows `readonly / write / full / rules` with descriptions; fuzzy input works (`/sandbox d` → `docker`), and once an argument is chosen the menu gets out of the way so Enter sends.

## One exploration, one line

Consecutive reads/searches/listing calls **no longer print one card each** when they succeed; the turn ends with:

```
⚙ 4 tool calls · 1.20s · read 3 · searched 1×
```

Failed reads are **still printed** (a failed read must be visible), and write/exec calls are always shown on their own — folding only swallows "I read a file", which carries no information.

## Waiting: you can tell it is moving, and you can tell it is stuck

- the status line states the exact state for the first 2.4s, then rotates verbs
- 3 seconds without progress adds a quiet marker; 45 seconds says "Ctrl+C to interrupt"
- the tool phase names the tool: `Calling file_read` instead of `Calling tool`
- `reduce_motion` (config) or `ACE_REDUCE_MOTION=1`: no rotation, no per-frame redraw

## Two real bugs fixed along the way

1. `Esc` followed by Enter had the escape-sequence lookahead **eat the Enter**, so "close the menu, then send" looked like end-of-input
2. `↓` at the newest history entry yanked history into the input line

## 📋 Compatibility

- No breaking changes; 27 new i18n keys (489 per locale, aligned); new test section `[53]` (40 assertions, including a real piped CLI round-trip)
- Not in this release (listed honestly): permission dialogs with numbered options and deny-with-feedback, live "reading X" progress inside collapsed groups, the notification area, and the full-screen history view (`Ctrl+E`)
