# ACE v3.12.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3120-2026-09-19)。这一版没有行为破坏性变更，升级无需改配置。

## 一句话

把终端里那句"（用 /expand 看完整）"从空话变成真命令，顺手补上跨会话输入历史与状态行计时。

## ✨ 新命令 `/expand`：折叠提示终于有对应实现

工具输出超过 8 行时，卡片会折叠并在末行写：

```
… 已折叠 40 行 (用 /expand 看完整)
```

这句话从早先版本就在卡片上了，但**仓库里从来没有 `/expand` 这条命令**——提示挂在最需要出口的位置，却点不开。这一版补上实现：

- `/expand` 重印上一次被折叠的完整输出，标题带工具名与行数，一眼知道展开的是哪次调用
- 单次最多保留前 **4000 字符**；超过时标题会写明"原始输出超过 4000 字符，以下为截断后的内容"——不假装这就是全部
- 没有折叠过就如实回答"没有可展开的输出"，并说明触发条件（不会打印一个空框）

## ✨ 输入历史跨会话 + 状态行带上已用秒数

- **↑/↓ 与 Ctrl+R 现在翻得到昨天的输入**。此前走的是 prompt_toolkit 默认的内存历史，进程一退就没了，同一个会话里连着改同一份文件都得重新打一遍。历史落在 `~/.ace_history`
  - 历史文件里可能留下你粘贴过的密钥，所以给了显式开关：`ACE_NO_HISTORY=1` 退回只留在进程内
- **状态行从「`◈ 思考中...`」变成「`◈ 思考中... 12s`」**。只转圈不说过了多久，用户没法区分"模型在想"和"已经卡死"——现在能看出来

## 🛡️ 守卫

- `[9]` +12 条：`/expand` 有折叠时**真的印全**（40 行首末行都在、行数不多不少）、无折叠时如实回答、4000 截断如实标注、两张命令表都登记；`spinner_line` 的拼接；源码级断言 `PromptSession` 收了 `history=`、`ACE_NO_HISTORY` 真的接在 `InMemoryHistory` 上
- `[9]` 新增一条**通用不变量**：用 `inspect.signature` 逐个核对"命令表里的 parts 标志"与"处理函数的真实签名"。它第一次运行就抓住了 `/expand` 自己的不符（表里声明"不收 parts"，函数却要求 `parts`）——这类错此前只在用户敲下那条命令时才炸
- `[11]` +3 条：三语（zh/en/ja）键集完全一致（当前各 196 键）、同名键的 `{占位符}` 三语一致（防某语言下 `.format()` 直接 KeyError）、没有空译文。这三类问题此前都只在"切到那个语言"时才暴露

## 📋 同步与升级

- `docs/COMMANDS.md` 命令表加 `/expand`，并补上折叠阈值、4000 字符上限与历史开关的说明；中英 README 同步
- 无破坏性变更：配置文件、启动参数、权限/沙箱/审批三维度语义均未改动。已有的 `config.json` 直接可用

---

# ACE v3.12.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3120-2026-09-19). No breaking changes; no config edits needed.

## In one line

The fold hint in the terminal stopped being an empty promise, plus cross-session input history and an elapsed timer on the spinner.

## ✨ New command `/expand`

When tool output exceeds 8 lines, the card folds it and ends with:

```
… 已折叠 40 行 (用 /expand 看完整)
```

That line has been on the card for several versions — but **no `/expand` command ever existed**. The hint sat exactly where you needed an exit and there was nothing behind it. Now:

- `/expand` reprints the last folded output in full, with a header naming the tool and the line count
- Up to the first **4000 characters** are retained per call; when the original was longer, the header says so ("original output exceeded 4000 characters, the following is truncated") instead of pretending it is complete
- With nothing folded it answers honestly ("nothing to expand") and states the trigger condition — no empty box

## ✨ Cross-session history and elapsed seconds

- **↑/↓ and Ctrl+R now reach yesterday's input.** Previously this used prompt_toolkit's default in-memory history, so it vanished with the process — retyping the same file path every session. History now lives in `~/.ace_history`
  - The file can retain keys you once pasted, so there is an explicit opt-out: `ACE_NO_HISTORY=1` keeps history in-process only
- **The status line went from `◈ 思考中...` to `◈ 思考中... 12s`.** A spinner with no elapsed time leaves you unable to tell "the model is thinking" from "it hung"

## 🛡️ Guards

- `[9]` +12: `/expand` really prints everything when something was folded (first and last of 40 lines present, count exact), answers honestly when not, marks the 4000-character cut, and is registered in both command tables; spinner composition; source-level assertions that `PromptSession` receives `history=` and that `ACE_NO_HISTORY` is really wired to `InMemoryHistory`
- `[9]` gains a **generic invariant**: every entry in the command table is checked with `inspect.signature` against its handler's real signature. It caught `/expand`'s own mismatch on the first run (table said "takes no parts", the function required `parts`) — that class of bug used to surface only when a user typed the command
- `[11]` +3: identical key sets across zh/en/ja (196 keys each), identical `{placeholders}` per key (a mismatch means a `.format()` KeyError in that language), and no empty translations. All three were previously invisible until you switched language

## 📋 Compatibility

- `docs/COMMANDS.md` documents `/expand` along with the fold threshold, the 4000-character cap and the history switch; both READMEs updated
- No breaking changes: config format, CLI flags, and the permission/sandbox/approval axes are untouched. An existing `config.json` keeps working
