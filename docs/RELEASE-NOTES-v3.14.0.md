# ACE v3.14.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3140-2026-09-19)。无破坏性变更，升级不需要改配置。

## 一句话

这次动的是**每天第一眼看到的那块屏幕**：首屏从一列信息变成面板 + 分组菜单，并且新增 `--preview`，不用开交互终端也能看见界面长什么样（README 首图就是它画的）。

## 为什么会有这一版

上一版之后收到的反馈是"体验还是和以前一样"。这话是对的：`/expand`、底栏占比、逼近阈值的提醒都只在细节层面，而**首屏和聊天界面一行没动**。所以这一版先改最显眼的地方。

## ✨ 首屏：三块结构

```
 ╭─ 当前会话 ────────────────────────── v3.14.0 ─╮
 │ 模型    deepseek-v4-flash · api.deepseek.com  │
 │ 边界    权限 write · 沙箱 off · 联网 开 · 审批 on_request │
 │ 目录    ~\Desktop\AI_Project\ace              │
 │ 历史    已恢复 09-17 23:07 的会话 · 2 条消息   │
 ╰───────────────────────────────────────────────╯

 ╭─ 最近会话 ────────────────────────────────────╮
 │ 09-17 23:07  1 轮  帮我看看 tools/registry.py… │
 ╰───────────────────────────────────────────────╯

 ── 会话 ─────────────────────────────────────────
  ❯ 1. 进入聊天            开始与 Agent 对话
 ── 模型 ─────────────────────────────────────────
    2. 配置向导            提供商 → API Key → 模型
    ...
```

- **「当前会话」面板**把四件事摆在一处：模型、**边界四轴**（权限 · 沙箱 · 联网 · 审批）、即将被编辑的目录、以及"恢复了哪一次会话"。此前这些散在六行文字里，用户得自己拼出"我现在处于什么状态"
- **「最近会话」面板**列出最近 3 次（时间 / 轮数 / 首句）。启动时本来就会自动续聊最近一次会话，但**以前界面上没有任何地方说明恢复的是哪一次** —— 现在写出来了
- **菜单分组**（会话 / 模型 / 其他）并加了分组标题；编号和动作一个都没改，`1`–`7` 还是原来的意思

## ✨ `ace --preview`：界面能被看见

```bash
ace --preview                 # 按当前终端列数画一遍首屏就退出
ace --preview --preview-width 88   # 指定列宽（演示录制用的就是 88）
```

终端界面以前"只能自己跑一次才知道长什么样"，评审、对比、回归都无从下手。现在它只画界面、不读按键、不进对话，所以可以被**录成图**（`demo/demo_landing.svg`，中英 README 首图）、被断言、被 diff。

## 🐛 排版：颜色不再把边框挤歪

`ui/ace_text` 现在忽略 ANSI 颜色码来算宽度。颜色码在终端里占 0 列，此前却会被当成十几个字符 —— 也就是"给一行上个色，面板边框就错位"。顺带修了一个会漂的显示：底栏在 mock 模式下不再显示配置文件里的模型名（那是谎报"正在用某个模型"）。

新增的 `ui/ace_panel.py` 是纯函数排版层（框 / 左右分栏 / 分组标题 / 菜单行），硬保证是**每一行的显示宽度严格等于面板宽度**（中文按两列算），窄终端下整屏也不溢出。

## 🛡️ 守卫

`[9]`：面板齐全、模型/目录/历史三项都在、**每行等于面板宽**、整屏不超宽、菜单编号 1..7 一个不少、三个分组标题都在、60 列窄终端下仍不溢出；`--preview` 三样输出俱全；`list_sessions` 读出条数与首句、目录不存在返回空、**半截日志不抛异常**（首屏不该因为一个坏文件崩掉）。

`[34]`：ANSI 宽度口径（忽略色码、只去 SGR、截断补复位码、补齐按可见宽度）+ `ace_panel` 的框宽/分栏对齐/菜单**显示列**对齐/时间格式三态。

三张演示图（首屏 / 完整会话 / 被拦下）都纳入 `demo/record_demo.py --check`，CI 会校验 —— 界面一变，图必须跟着重录。

## 📋 兼容性

- 无破坏性变更：配置、启动参数、权限/沙箱/审批语义、命令用法、快捷键都没变
- 首屏菜单编号与动作映射保持不变（`1` 进聊天 … `7` 退出）
- 新增 23 个 i18n 键，中英日三语齐全

---

# ACE v3.14.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3140-2026-09-19). No breaking changes; no config edits needed.

## In one line

This one changes **the screen you see first**: the landing page became panels plus a grouped menu, and a new `--preview` flag renders it without an interactive terminal — the new README hero image is drawn by that flag.

## Why this release exists

The feedback after the previous version was "the experience is still the same". That was accurate: `/expand`, the context figure in the footer, and the pre-compaction warning all live in the details, while **the landing page and the chat layout had not moved at all**. So this release starts with the most visible thing.

## ✨ The landing page: three blocks

- **Session panel** — the model, the **four boundary axes** (permission · sandbox · network · approval), the directory about to be edited, and *which past session was resumed*. These used to be six unstructured lines the user had to assemble a mental model from
- **Recent sessions** — the last three, with time, turn count and opening line. The previous session is auto-resumed at startup (since v3.9), but nothing on screen ever said *which* one — now it does
- **Grouped menu** — Session / Model / More, with section headers and an aligned description column. The numbering and actions are untouched: `1`–`7` still mean exactly what they meant before

## ✨ `ace --preview`

```bash
ace --preview                      # draw the landing at the current terminal width and exit
ace --preview --preview-width 88   # fixed width (what the demo recording uses)
```

A terminal UI used to be verifiable only by launching it once and looking. Now it draws the screen without reading keys or entering a conversation, which makes it **recordable** (`demo/demo_landing.svg`, now the README hero image in both languages), assertable, and diffable.

## 🐛 Layout: colour no longer pushes the border out

`ui/ace_text` now ignores ANSI colour codes when measuring width. A colour code occupies zero columns in a terminal but used to count as a dozen characters — i.e. "colour one line and the panel border shifts". Along the way: the status bar no longer claims the configured model name while running in mock mode.

The new `ui/ace_panel.py` is a pure layout layer (boxes, side-by-side, section headers, menu rows) with a hard guarantee: **every line's display width equals the panel width** (CJK counted as two columns), and nothing overflows on a narrow terminal.

## 🛡️ Guards

`[9]`: panels present, model/directory/history rows present, **每 line equals the panel width**, nothing wider than the screen, menu numbered 1..7 with no gaps, three section headers, no overflow at 60 columns; `--preview` emits all three parts; `list_sessions` reads counts and opening lines, returns empty for a missing directory, and **does not raise on a truncated log** (the landing page must not die because one file is broken).

`[34]`: the ANSI width contract (ignore colour codes, strip only SGR, append a reset on truncation, pad by visible width) plus `ace_panel`'s box widths, column alignment, menu alignment by **display column**, and `format_when`'s three cases.

All three demo images (landing / full session / blocked) are covered by `demo/record_demo.py --check` in CI — change the UI and the images must be re-recorded.

## 📋 Compatibility

- No breaking changes: config, CLI flags, permission/sandbox/approval semantics, command usage and keybindings are all unchanged
- Landing menu numbering and action mapping are unchanged (`1` chat … `7` quit)
- 23 new i18n keys, complete in Chinese, English and Japanese
