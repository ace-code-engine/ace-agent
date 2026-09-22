# ACE v3.25.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3250-2026-09-19)。无破坏性变更。

## 一句话

「全套 UI 与交互」的第四批：**布局与状态行**。多了一个全屏会话（会话自己带滚动区，不再拿终端回滚缓冲当历史）、底栏变成可配置的数据、等待时能看出"在动"还是"卡住"，目标/待办/正在跑的工具合成一棵树。

## ✨ 全屏会话：`--fullscreen` 或 `/fullscreen`

普通 REPL 是流水账 —— 模型一轮跑几十条工具之后，想回看刚才那张卡片只能翻终端回滚缓冲，状态行也挤在一行里。全屏（备用屏幕）把它分成固定四块：

```
 ACE · mock · readonly · C:\项目                                     ← 头部
                                                                     ← 会话滚动区
 ▶ 目标 [R2/20] 把 UI 补齐                                           （自己的视口）
 │  ├─ ✓ #1 画状态行
 │  └─ ▶ #2 接任务树
 轮2 工具7 · 上下文 ████░░░ 42%                                       ← 状态行
 Enter 发送 · PageUp/↑ 回看 · Ctrl+O 展开 · F5 退出全屏 · Ctrl+C 取消
 ❯ 帮我看看这段                                                ← 输入行
```

- `PageUp` / `↑` **回看**（提示行显示 `↑12-24/96`），`End` 或 `↓` 回到底部，`PageDown` 翻页
- `F5` 退出全屏回到普通 REPL；`Ctrl+O` 展开最近一次被折叠的输出；`F1`–`F4` 与普通 REPL 同义
- 退出全屏后终端画面原样恢复（备用屏幕的语义）
- 终端太小（小于 8 行）或没装 `prompt_toolkit`：**直接回退普通 REPL**，不硬撑出一个更难用的界面

**一处刻意的取舍**：全屏里不弹嵌套浮层选择框（`prompt_toolkit` 的 Application 不能安全嵌套），选择类命令退化成"打印列表/取默认"，要弹框按 F5 退出全屏即可。

## ✨ 底栏变成数据：`/statusline`

```
❯ /statusline
  底栏分段（当前顺序）: model · permission · sandbox · net · goal · turns · todos · queue · stash · images · context · cost
  可用分段: model, permission, sandbox, net, goal, turns, todos, queue, stash, images, context, cost
  /statusline model,context,-turns 改顺序；-名字 = 去掉该段（窄终端会自动按优先级丢装饰）

❯ /statusline context,model,-turns
  底栏已改为: context → model → permission → …
```

- 每一项带**优先级**：终端窄了先丢装饰（轮数、工具数），**先保住上下文占用与目标进度** —— 被截掉的恰恰常是"出事前唯一能救你"的信息
- 丢完还有一次**回填**：20 列时得到"模型 + 上下文"，而不是只剩"模型"
- 写错分段名会如实报错，**不当成设置成功**（那是最坏的一种成功）

## ✨ 等待时看得出"在动"还是"卡住"

```
◈ 思考中.. 12s
◈ 正在调用工具. 61s（61s 没有新进展 · Ctrl+C 可中断）
```

- 停滞判据是「**多久没有新动作**」而不是「等了多久」：换阶段（思考 → 调工具）会刷新计时，正常的 60 秒多轮任务不会被误报成卡死
- 等待行按终端列数截断 —— 顶破终端会让 `\r` 重绘错位

## ✨ `/tasks`：目标 / 待办 / 正在跑的工具，一棵树

```
❯ /tasks
▶ 目标 [R2/20] 把 UI 补齐
├─ ✓ #1 画状态行
├─ ▶ #2 接任务树
└─ ▶ file_write  (running)
```

三者都空时如实说没有（不打印一棵空树）。状态符号与 `todo` 清单同一套口径（✓/▶/·/✗）。

## ✨ 其它

- `/status` 多一条**上下文度量条**（`████░░░░ 42%`），口径与底栏同一份估算
- 首屏标题在真终端里播一次浮现动画（管道/CI 里直接跳过；`ACE_NO_ANIM=1` 或配置 `animate: false` 可关）
- 顺带修掉：一串空格的输入此前会被当成问题发给模型（只挡了空串），现在识别为空输入直接跳过

## 📋 兼容性

- 无破坏性变更：不进全屏、不配 `statusline` 时行为与之前一致（底栏还是同一份数据，只是现在会按宽度取舍）
- 新增 25 个 i18n 键，中英日齐全；`docs/COMMANDS.md` 补三个命令；新增测试段 `[51]`（62 项断言）

---

# ACE v3.25.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3250-2026-09-19). No breaking changes.

## In one line

The fourth batch of the full UI/interaction pass covers **layout and the status line**: a full-screen session whose transcript has its own viewport (your terminal scrollback is no longer the history), a status line that is data instead of a hard-coded string, waiting that shows whether it is moving or stuck, and one tree for goal + checklist + the running tool.

## ✨ Full-screen session: `--fullscreen` or `/fullscreen`

The plain REPL is a stream: after a turn with dozens of tool calls, looking back at a card means digging through your terminal scrollback. Full screen (alternate screen) splits it into four fixed regions:

- header · **transcript with its own viewport** · status line · input line
- `PageUp` / `↑` scrolls back (the hint line shows `↑12-24/96`), `End` or `↓` returns to the bottom, `PageDown` pages
- `F5` leaves full screen back to the plain REPL; `Ctrl+O` expands the last folded output; `F1`–`F4` mean the same as in the plain REPL
- exiting restores the previous terminal contents (that is what the alternate screen is for)
- too small a terminal (under 8 rows) or no `prompt_toolkit`: it **falls back to the plain REPL** rather than forcing a worse interface

**One deliberate trade-off**: no nested overlay pickers inside full screen (prompt_toolkit Applications cannot be nested safely), so picker commands degrade to printing the list / taking the default; press F5 to leave full screen and use them.

## ✨ The status line becomes data: `/statusline`

- every segment carries a **priority**: a narrow terminal drops decoration (turn/tool counts) first and **keeps the context meter and goal progress** — those are exactly the things you need before trouble
- after dropping, there is a **refill pass**: at 20 columns you get "model + context" rather than just "model"
- `/statusline model,context,-turns` reorders or removes segments and writes the config; a misspelled name is reported, never silently treated as success

## ✨ Waiting shows "moving" versus "stuck"

```
◈ 思考中.. 12s
◈ 正在调用工具. 61s (61s without progress · Ctrl+C to interrupt)
```

The stall test is "how long since the **last new action**", not "how long have we waited": switching stage (thinking → calling a tool) refreshes the timer, so a normal 60-second multi-round task is not misreported as hung.

## ✨ `/tasks`: goal, checklist and the running tool as one tree

```
❯ /tasks
▶ Goal [R2/20] finish the UI
├─ ✓ #1 draw the status line
├─ ▶ #2 wire the task tree
└─ ▶ file_write  (running)
```

When all three are empty it says so instead of printing an empty tree.

## ✨ Also

- `/status` gained a **context meter** (`████░░░░ 42%`), same estimate as the status line
- the banner animates once on a real terminal (skipped in pipes/CI; `ACE_NO_ANIM=1` or config `animate: false` turns it off)
- fixed along the way: an all-whitespace input used to be sent to the model as a question (only the empty string was filtered); it is now recognised as empty and skipped

## 📋 Compatibility

- No breaking changes: without full screen and without a `statusline` config, behaviour is unchanged
- 25 new i18n keys, complete in Chinese, English and Japanese; `docs/COMMANDS.md` gains three commands; new test section `[51]` (62 assertions)
