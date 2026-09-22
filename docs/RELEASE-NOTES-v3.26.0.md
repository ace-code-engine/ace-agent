# ACE v3.26.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3260-2026-09-19)。无破坏性变更。

## 一句话

「全套 UI 与交互」的第五批（收尾）：**键位与编辑器集成** —— 键位写错会告诉你为什么、vi 的操作符与文本对象终于能用、输出风格一份预设同时管提示词与界面、终端能力探不出来就问人。

## ✨ 键位：写错会有人告诉你

配置里的 `keybindings` 现在会被完整判定，被拒的每一条都给理由：

- **保命键**（Enter / Esc / Ctrl+C …）不许覆盖 —— 改掉它们等于把"发不出去、退不出来"写进配置
- **已接真功能的键**（Ctrl+S / Ctrl+O / Ctrl+L / F1–F4）不许覆盖 —— 覆盖不是"改键位"，是"两件事各做一半"
- 键名写法不对、值不是斜杠命令、条数超限，都会在 `/keys` 表下方列出来

此前这些情况都是**静默忽略**：按下没反应，你只会以为这软件坏了。

## ✨ vim 子集：操作符与文本对象

```
dw  d2w  de  d$  cw  dd  cc  yy  x  D  C  p     操作符与计数
h l w b e 0 $ gg G                              motion
iw aw i" a" i( a( ip                            文本对象
```

- **全屏会话的输入行**已经接上这套键位（普通 REPL 的 vi 模式本来就由 `prompt_toolkit` 提供，不重复造）
- 做不成就说做不成：`di"` 停在引号外时**不动文本**，只留一句说明 —— 悄悄删错东西比没生效坏得多
- 明确不做：撤销栈、寄存器、宏、`.` 重复、可视模式、`/` 搜索（输入一行提示词时收益极低）

## ✨ 输出风格预设：一份预设，两个面

```
❯ /style concise
```

| 预设 | 提示词 | 界面 |
|---|---|---|
| `default` | 不加额外指令 | 各开关自己决定 |
| `concise` | 少铺垫、去客套、代码优先 | 不显示推理过程，diff 只留 40 行，卡片只留摘要 |
| `explanatory` | 动手前说一句为什么，讲清取舍与坑 | 展开推理与完整卡片 |
| `strict` | 只报验证过的事实 | 不显示推理过程 |

为什么合成一件事：想"回答短一点"的人同时也在意"别刷屏"。分开两个旋钮的话，改了提示词却仍被推理过程刷屏，只会觉得"这设置没用"。**用户显式按 F4 开过思考，就以用户为准**。

## ✨ 终端能力自检

```
❯ /term
  终端能力（结论: partial）:
  ✓ 颜色                        yes
  ✓ 真彩（24bit）               yes
  ? Unicode 符号                unknown
```

能自动判的自动判：`COLORTERM` 才算真彩（`TERM` 里的 256color 不算）、`NO_COLOR` 优先级最高、管道里一律 no、Windows 旧 conhost 一律 unknown（本项目在这里踩过方框字的坑）。

探不出来的三项用 `/term check` **问人**：颜色对不对、方块字有没有、滚轮管不管用。答案覆盖探测结果并写进配置 —— 猜错的代价是花屏，而花屏比"功能少一点"糟得多。

## 📋 兼容性

- 无破坏性变更：不写 `keybindings`、不用 `/style` `/term` 时行为与之前一致
- 新增 36 个 i18n 键（中英日各 452 键对齐）；新增测试段 `[52]`（62 项断言）
- 顺带修掉：`/keys` 之前在补全菜单里重复出现一条

---

# ACE v3.26.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3260-2026-09-19). No breaking changes.

## In one line

The fifth and final batch of the full UI/interaction pass covers **keys and editor integration**: a rejected keybinding now tells you why, vi operators and text objects work, one output-style preset drives both the prompt and the UI, and terminal capabilities that cannot be probed are asked about instead of guessed.

## ✨ Keybindings: a rejected key says why

- **Safety keys** (Enter / Esc / Ctrl+C …) cannot be overridden — remapping them writes "cannot send, cannot quit" into your config
- **Keys that already have a real function** (Ctrl+S / Ctrl+O / Ctrl+L / F1–F4) cannot be overridden — that is not remapping, it is half-breaking two things
- Bad key syntax, a value that is not a slash command, and too many entries are all listed under the `/keys` table

Previously all of these were **silently ignored**: pressing the key did nothing and you concluded the app was broken.

## ✨ vim subset: operators and text objects

`dw d2w de d$ cw dd cc yy x D C p` · `h l w b e 0 $ gg G` · `iw aw i" a" i( a( ip`

- wired into the **full-screen input line** (the plain REPL's vi mode comes from `prompt_toolkit`; this does not duplicate it)
- when it cannot do the thing, it says so: `di"` with the cursor outside the quotes **leaves the text alone** — silently deleting the wrong thing is worse than doing nothing
- deliberately out of scope: undo stack, registers, macros, `.` repeat, visual mode, `/` search

## ✨ Output style presets: one preset, two faces

`/style concise | explanatory | strict | default`. A preset changes both the instruction appended to the system prompt and how much the UI shows (thinking, diff length, card collapsing, summary-only). If you explicitly toggled thinking with F4, your choice wins.

## ✨ Terminal capability self-check

`/term` prints the table; `/term check` asks about the three things autodetection cannot answer (colours right? glyphs clean? mouse working?) and stores the answers in the config. Guessing wrong costs a garbled screen, which is far worse than having one feature fewer.

## 📋 Compatibility

- No breaking changes; 36 new i18n keys (452 per locale, aligned); new test section `[52]` (62 assertions)
- Fixed along the way: `/keys` appeared twice in the completion menu
