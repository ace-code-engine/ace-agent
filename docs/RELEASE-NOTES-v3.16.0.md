# ACE v3.16.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3160-2026-09-19)。无破坏性变更，升级不需要改配置。

## 一句话

一句话写不完的时候能换行了，上次那句话能按关键词找回来了，25 条命令也分了组。

## ✨ 多行输入

| 按键 | 作用 |
|---|---|
| `Enter` | 发送 |
| `Alt+Enter` / `Ctrl+J` | 在光标处换行（**推荐**，各终端一致） |
| `Shift+Enter` | 换行（需要终端支持扩展键协议：Windows Terminal / Kitty 支持；旧 conhost 会把它当成 `Enter`） |

续行用 `… ` 对齐，一眼看出还在同一句里。此前只有单行输入——想贴一段代码，或者写清"改哪个文件、改成什么、注意什么"，只能挤成一行。

## ✨ `/history`：按关键词找历史

```bash
/history            # 最近 20 条（倒序）
/history dsk        # 子序列匹配：命中「帮我把 deepseek 的 key 换成新的」
```

- 复用选择器那套**子序列评分**（`dsk` → `deepseek`、`glm4` → `glm-4.6`），命中字符高亮
- 交互终端里给选择器，**挑中后填进下一次输入行**——不自动发送。历史里那句话是当时的上下文，直接发出去大概率不是这次想说的
- 历史为空时如实说没有，并点出它写在 `~/.ace_history`、`ACE_NO_HISTORY=1` 时只留在进程内

和 `Ctrl+R` 的分工：`Ctrl+R` 逐条往回翻（脑子里得有确切字样），`/history` 按关键词找（只记得"那次问的是 deepseek 相关的事"）。

## ✨ 命令分组：`/` 菜单与 `/help`

25 条命令分成 **会话 / 安全 / 模型 / 工具** 四组：

- 补全菜单按组排序，说明前标组名（`会话 · 清空会话历史`）
- `/help` 用与首屏同一套分节样式（`── 会话 ─────…`）

平铺 25 条时，"我要找的那条"得靠眼睛扫完整张表。

## 🛡️ 守卫

- 分组**覆盖全部命令且不重不漏**（新增命令不会掉出菜单，忘了分组也会落到「其他」）
- `menu_entries()` 是纯函数：顺序与说明前缀都可断言，且**不依赖 prompt_toolkit** —— 它是可选依赖，缺了整段断言会被跳过，于是"菜单长什么样"在最需要它的环境里反而没人验
- 历史读取要正确处理 `FileHistory` 写的 `+` 前缀行与时间戳注释行；`dsk` 必须命中 `deepseek` 那条；无命中时如实回答
- 多行键位与续行提示、`/history` 选中后填进输入行（不自动发送）都有断言盯着

## 📋 兼容性

- 无破坏性变更：`Enter` 仍然是发送，既有的 ↑/↓ 与 `Ctrl+R` 行为不变
- 新增 14 个 i18n 键，中英日三语齐全；`docs/COMMANDS.md` 补上输入行一节

---

# ACE v3.16.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3160-2026-09-19). No breaking changes; no config edits needed.

## In one line

You can now write more than one line, find that sentence you typed last week by keyword, and see 25 commands grouped instead of flat.

## ✨ Multiline input

| Key | Effect |
|---|---|
| `Enter` | send |
| `Alt+Enter` / `Ctrl+J` | insert a newline (**recommended**, consistent across terminals) |
| `Shift+Enter` | newline (needs the extended keyboard protocol: Windows Terminal / Kitty do; old conhost sends it as plain `Enter`) |

Continuation lines are aligned with `… ` so it is obvious you are still in the same message. Until now the input was single-line only: pasting a snippet, or spelling out "which file, what change, what to watch out for", had to be squeezed into one line.

## ✨ `/history`: find a past input by keyword

```bash
/history            # last 20, newest first
/history dsk        # subsequence match: hits "帮我把 deepseek 的 key 换成新的"
```

- Reuses the picker's **subsequence scoring** (`dsk` → `deepseek`, `glm4` → `glm-4.6`) with matched characters highlighted
- In an interactive terminal it opens the selector, and the picked entry **fills the next prompt** — it is never auto-sent, because that sentence belonged to its own context
- With no history it says so honestly, and points out that history lives in `~/.ace_history` (and stays in-process under `ACE_NO_HISTORY=1`)

Division of labour with `Ctrl+R`: `Ctrl+R` walks backwards one entry at a time (you need to know the wording), `/history` searches by keyword (you only remember it was about deepseek).

## ✨ Grouped commands: the `/` menu and `/help`

The 25 commands are grouped into **Session / Security / Model / Tools**:

- the completion menu is sorted by group and prefixes each description with the group name (`Session · Clear conversation history`)
- `/help` uses the same section style as the landing screen (`── Session ─────…`)

Flat-listed, finding one command means scanning the entire table.

## 🛡️ Guards

- Groups **cover every command exactly once** (a new command cannot fall out of the menu; if you forget to group it, it lands in "More")
- `menu_entries()` is a pure function, so ordering and description prefixes are assertable **without prompt_toolkit** — it is an optional dependency, and skipping the whole block would mean nobody verifies what the menu looks like in the environments that need it most
- History reading handles the `+` prefix lines and timestamp comments that `FileHistory` writes; `dsk` must hit the `deepseek` entry; a miss is reported honestly
- Multiline keybindings, the continuation marker, and "picking a history entry fills the prompt (never auto-sends)" all have assertions

## 📋 Compatibility

- No breaking changes: `Enter` still sends, and the existing ↑/↓ and `Ctrl+R` behaviour is untouched
- 14 new i18n keys, complete in Chinese, English and Japanese; `docs/COMMANDS.md` gains an input-line section
