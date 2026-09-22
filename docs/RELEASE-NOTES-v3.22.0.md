# ACE v3.22.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3220-2026-09-19)。无破坏性变更。

## 一句话

「全套 UI 与交互」的第一批：把**输入行**该有的东西补齐 —— 粘一大段不再刷屏、跑命令不用先跟模型说一遍、写一半能存起来、一次能交代几件事、键位看得见。

## ✨ `! <命令>`：直接跑，但不绕过闸门

```
! git status
! python -m pytest -q
```

- 与 Claude Code 的 `!` 同一个用法，**但闸门是我们的**：它走 `terminal_exec` 那条路 —— 逐次确认、沙箱、审计一个不少。所以"直接执行"不等于"绕过审查"
- 输出会贴进对话上下文，下一轮模型看得到
- 提示符随模式变色：`!` 开头是黄色的 `! `、多行输入是青色的 `… `、其余是品红的 `▊ ` —— "这条到底发给模型还是本机跑"不该靠猜
- 空 `!` 给用法；命令失败会报状态与原因，而且**不进上下文**（失败输出不该当事实喂给模型）

## ✨ 大段粘贴自动折叠

粘 300 行日志进输入行，过去光标没了、上一条对话被顶出屏幕。现在：

```
[粘贴 #1 +30 行]
```

- 超过 6 行或 800 字符的粘贴折叠成占位符，**提交时自动展开**成原文
- 展开时找不到编号就**原样留着**，不静默丢掉占位符
- 回显也截断：提交后最多回显 12 行，并**说明实际发出多少行/字符** —— 静默截断比不截断更糟，你以为发出去的只有这些

## ✨ 暂存与排队

| 操作 | 作用 |
|---|---|
| `Ctrl+S` / `/stash <文本>` | 把当前输入存起来（一句话写一半想问别的） |
| `/stash pop` | 取回最近一条（填进输入行，不自动发送） |
| `/queue <文本>` | 排到当前这轮之后自动执行 |
| `/queue clear` | 清空队列 |

底栏会显示 `暂存1` / `队列1` —— 有东西存着或排着，你自己得看得见。

这和 `goal`（任务级目标）、`todo`（步骤级清单）不重复：暂存是"手边的草稿"，排队是"下一件事"。

## ✨ 快捷键表（`/keys` 或单独一个 `?` 加回车）

一张表列全：Enter / Alt+Enter（换行）/ ↑↓ / Ctrl+R / F1–F4 / Ctrl+O（展开）/ Ctrl+S（暂存）/ Ctrl+L（清屏）/ Esc / Ctrl+C / `!` / `?`，外加上你在配置 `keybindings` 里加的自定义键位。

真实终端里"按 `?` 弹菜单"不可靠（`?` 就是个普通字符），所以做成**回车时判定**：单独一个 `?` 加回车 = 弹表。

## 📋 兼容性

- 无破坏性变更：不用 `!`、不粘大段、不用 `/stash` `/queue` 时，行为与之前一致
- 新增 40 个 i18n 键，中英日三语齐全；`docs/COMMANDS.md` 新增「输入行（模式与快捷键）」一节

---

# ACE v3.22.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3220-2026-09-19). No breaking changes.

## In one line

The first batch of the full UI/interaction pass covers the **input line**: a big paste no longer floods the screen, running a command does not require asking the model first, half-written thoughts can be parked, several asks can be queued, and every shortcut is documented.

## ✨ `! <command>`: run it directly, but not around the gate

```
! git status
! python -m pytest -q
```

- Same usage as Claude Code's `!`, **but the gate is ours**: it goes through the `terminal_exec` path — per-call confirmation, sandbox, audit all still apply. "Direct" does not mean "unreviewed".
- The output is pasted into the conversation context, so the next turn can see it.
- The prompt changes colour with the mode: yellow `! ` for bash, cyan `… ` for multiline, magenta `▊ ` otherwise — whether a line goes to the model or to your shell should not be a guess.
- A bare `!` prints usage; a failing command reports status and reason and is **not** added to context (failed output should not be fed to the model as fact).

## ✨ Large pastes fold automatically

Pasting 300 lines of logs used to eat the cursor and push the previous message off-screen. Now:

```
[粘贴 #1 +30 行]
```

- Pastes over 6 lines or 800 characters fold into a placeholder and are **expanded automatically on submit**
- If a placeholder's id cannot be resolved it stays as-is — nothing is silently dropped
- Echo is truncated too: at most 12 lines are echoed, with a note saying how many lines/characters were actually sent — silent truncation is worse than none, because you think that was all.

## ✨ Stash and queue

| Action | Effect |
|---|---|
| `Ctrl+S` / `/stash <text>` | park the current input |
| `/stash pop` | bring the latest one back (fills the prompt, never auto-sends) |
| `/queue <text>` | queue a prompt to run right after this turn |
| `/queue clear` | empty the queue |

The footer shows `stash1` / `queue1` — if something is parked or queued, you should be able to see it.

This does not overlap with `goal` (task-level objective) or `todo` (step-level checklist): a stash is the draft in your hand, a queue is the next thing.

## ✨ Shortcut table (`/keys`, or a lone `?` plus Enter)

One table lists everything: Enter / Alt+Enter (newline) / ↑↓ / Ctrl+R / F1–F4 / Ctrl+O (expand) / Ctrl+S (stash) / Ctrl+L (clear screen) / Esc / Ctrl+C / `!` / `?`, plus any custom bindings from your `keybindings` config.

"Press `?` to open a menu" is unreliable in real terminals (`?` is just a character), so it is decided **on Enter**: a lone `?` opens the table.

## 📋 Compatibility

- No breaking changes: without `!`, without large pastes and without `/stash` `/queue`, behaviour is unchanged
- 40 new i18n keys, complete in Chinese, English and Japanese; `docs/COMMANDS.md` gains an "input line (modes and shortcuts)" section
