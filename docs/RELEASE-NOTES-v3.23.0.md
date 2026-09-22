# ACE v3.23.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3230-2026-09-19)。无破坏性变更。

## 一句话

「全套 UI 与交互」的第二批：**模型吐出来的那段字**。回答不再以源码形态摊在屏幕上，工具做了什么也不再靠你自己往上翻。

## ✨ 回答按 Markdown 渲染

模型本来就在写 Markdown。过去这段字是原样打印的，于是你看到的是满屏 `**`、`|` 和 ```` ``` ````：

```
**注意**：这个函数会 | 参数 | 说明 |
```

现在：

- 标题保留层级（`#` 开头按级上色）· 列表 `• ` 按层缩进 · 引用 `│ ` 前缀 · 分隔线一条横线
- 代码块画边框并标注语言，内部**不做任何行内解析**（代码里的 `**` 就是两个星号，不会被吃掉）
- 表格按**显示列宽**重排：中文算两列，所以列一定对齐，宽度不够按列截断并给省略号
- 行内 `**粗**` / `*斜*` / `` `码` `` / `[文字](链接)`（终端里不假装能点，显示成 `文字 (链接)`）

**认不出的语法原样保留** —— 宁可少渲染也不猜。

## ✨ 边生成边显示，但不错行

模型是一个字一个字吐出来的。等一整段才渲染，你会以为程序卡死；收到半个词就渲染，`**粗` 会被拆成两半、星号直接漏出来。

做法是**按完整行渲染**：一行写完就画出来，还在路上的半行留在缓冲里；表格因为列宽依赖所有行而单独攒着，遇到别的行再一起画。流式渲染的结果与整篇渲染**逐行一致**（测试段 `[49]` 就是这么钉的）。

## ✨ 谁在说话，一眼分得清

| 符号 | 含义 |
|---|---|
| `❯` | 你的输入 |
| `◈` | 模型的回答 |
| `⚙` | 工具调用汇总 |
| `·` / `✗` | 通知 / 错误 |

早先只有你的输入有符号，其余靠颜色区分 —— 重定向到文件、或者色弱终端里，颜色全丢，符号不会。

## ✨ 一轮工具调用的汇总会合并同类

```
⚙ 3 次工具调用 · 1.20s · file_read ×2 ✓ · file_write ✓
```

同一个工具连续调三次（比如读三个文件），过去会写三遍 `file_read ✓` —— 三份重复信息把"这轮其实只做了一件事"讲了三遍。现在合并成 `file_read ×2 ✓`，把位置留给真正不同的动作。**只合并连续的**：`读·写·读` 合成一段会把顺序讲错。

## ✨ 思考过程有边框，也有折叠上限

开了 `/thinking`（或 F4）之后，内部推理过去是一行行 `· 文本` 刷过去。现在是：

```
┌ 思考 (12 行)
│ 先确认这个字段在哪儿被写入…
│ …
│ … 其余 6 行已折叠（/thinking 控制显示）
└─
```

最多显示 6 行 —— 内部推理不该占满屏幕。

## ✨ `/diff`：先看动了哪些文件，再看某处的逐行

```
❯ /diff
◈ 改动记录（3 处，最新在前）：
  [1] file_write  ace/ui/ace_markdown.py  +142 -3  (4 块)
  [2] file_write  ace/ai_code.py  +38 -12  (3 块)
  [3] str_replace  ace/ui/ace_diff.py  +12 -1  (1 块)
  /diff <序号> 看逐行 · /review 把最新一处写成补丁去编辑器里改

❯ /diff 2
```

一次改 5 个文件时，几百行 diff 全铺出来，连"改了哪些文件"都读不出来。所以分两级：第一级回答**动了什么**，第二级回答**怎么动的**。记录会保留最近 20 处（`/review` 仍然只看最新一处）。

## ✨ `Ctrl+O` 终于能按了

`/keys` 表里从 v3.22.0 就写着「Ctrl+O 展开上一次被折叠的输出 / diff」，但这个键一直没绑上 —— 文档承诺了、代码里没有，等于骗人。现在按下就展开最近一次被折叠的工具输出或 diff。

## 📋 兼容性

- 无破坏性变更：渲染只影响**显示**；送进模型、写进会话日志的仍是模型原文
- 新增 7 个 i18n 键，中英日三语齐全；`docs/COMMANDS.md` 新增 `/diff`
- 新增测试段 `[49]`（47 项断言）

---

# ACE v3.23.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3230-2026-09-19). No breaking changes.

## In one line

The second batch of the full UI/interaction pass covers **the text the model produces**: replies are no longer dumped as Markdown source, and what the tools did is no longer something you have to scroll back for.

## ✨ Replies render as Markdown

The model already writes Markdown; that text used to be printed verbatim, so you saw walls of `**`, `|` and ```` ``` ````. Now:

- headings keep their level (and get colour by level) · lists get `• ` with nesting · quotes get a `│ ` prefix · rules become a line
- code fences are drawn with a border and a language label, and **nothing inside them is parsed inline** (a `**` in code stays two asterisks)
- tables are re-laid out by **display width**: CJK counts as two columns, so columns always line up; when the terminal is too narrow each column is truncated with an ellipsis
- inline `**bold**` / `*italic*` / `` `code` `` / `[text](link)` (shown as `text (link)` — the terminal does not pretend to be clickable)

**Anything unrecognised is passed through unchanged** — we would rather render less than guess.

## ✨ Streamed output, line by line

The model emits one character at a time. Waiting for a whole block makes it look hung; rendering half a word splits `**bold` and leaks the asterisks. So rendering happens **per completed line**: a finished line is drawn immediately, the in-flight half stays buffered, and tables (whose column widths need every row) are held until something else arrives. Streamed rendering matches whole-document rendering **line for line** — that is what test section `[49]` pins down.

## ✨ You can tell who is speaking

| Glyph | Meaning |
|---|---|
| `❯` | your input |
| `◈` | the model's reply |
| `⚙` | tool-call summary |
| `·` / `✗` | notice / error |

Previously only your input had a glyph and everything else was colour-coded — colour is the first thing lost when output is redirected to a file or read on a colour-blind terminal. Glyphs are not.

## ✨ Tool summaries merge consecutive repeats

```
⚙ 3 tool calls · 1.20s · file_read ×2 ✓ · file_write ✓
```

Three consecutive reads used to print `file_read ✓` three times — the same fact stated three ways, crowding out what actually differed. They now collapse into `file_read ×2 ✓`. **Only consecutive runs merge**: collapsing `read · write · read` would misreport the order.

## ✨ Thinking gets a frame and a cap

With `/thinking` (or F4) on, internal reasoning used to stream past as `· text` lines. Now it is framed, capped at 6 lines, and says how many more were folded — internal reasoning should not fill the screen.

## ✨ `/diff`: which files changed first, then the lines

```
❯ /diff
◈ Change log (3 entries, newest first):
  [1] file_write  ace/ui/ace_markdown.py  +142 -3  (4 hunks)
  [2] file_write  ace/ai_code.py  +38 -12  (3 hunks)
  [3] str_replace  ace/ui/ace_diff.py  +12 -1  (1 hunk)
  /diff <n> for the full diff · /review turns the newest entry into a patch you edit

❯ /diff 2
```

When one turn touches five files, hundreds of diff lines tell you nothing about *which* files moved. Level one answers **what changed**, level two answers **how**. The last 20 entries are kept (`/review` still uses only the newest).

## ✨ `Ctrl+O` finally works

The `/keys` table has listed "Ctrl+O — expand the last folded output / diff" since v3.22.0, but the key was never bound: the docs promised it and the code did not. Pressing it now expands the most recent folded tool output or diff.

## 📋 Compatibility

- No breaking changes: rendering affects **display** only; the model and the session log still receive the raw text
- 7 new i18n keys, complete in Chinese, English and Japanese; `docs/COMMANDS.md` gains `/diff`
- New test section `[49]` (47 assertions)
