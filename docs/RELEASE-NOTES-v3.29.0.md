# ACE v3.29.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3290-2026-09-19)。无破坏性变更。

## 一句话

把 **Esc** 这件"退一层"的键补成分层语义（顺手给了个历史选择器），再把状态行的抖动治掉。

## ✨ Esc：一个键，按上下文决定退哪一层

| 当前情境 | Esc 做什么 |
|---|---|
| 菜单开着 | 关菜单（**输入保留**） |
| 有输入 | 清空输入 |
| 空输入 + 双击（0.8 秒内两下） | 打开**历史选择器** |
| 历史为空 | 什么都不做（不装样子） |

```
❯ （空输入，连按两下 Esc）
  ▶ 帮我看看这段代码为什么报错
    把刚才那张卡片展开一下
    再跑一遍测试
  回车填入 · Esc 关闭
```

- 回车是**填入输入行**，不是直接发送 —— 历史那句话是当时的上下文，不该被原样再发一次
- 挑错了按 Esc 关掉，回车发出的是空输入（不会误发历史）

## ✨ 状态行防抖（0.3 秒窗口）

模型连着切几个工具名时，状态行原本会以每秒十几次的速度抖，看着像坏了。现在的规则是：**第一次变化立即生效**，之后同一窗口内的变化等窗口过去 —— 被挡下的文案不会丢，窗口一过就换上去。

## ✨ Ctrl+T：任务树

`Ctrl+T` = `/tasks`：目标 + 逐项待办 + 此刻在跑的工具，一棵树看清"我在哪一层"。两条输入路径（浮层菜单 / 内置输入行）同义。

## 📋 兼容性

- 无破坏性变更；新增测试段 `[55]`（13 项断言）
- 仍未做：折叠组的进行中实时说明、持久授权规则（可编辑前缀规则 + 保存作用域选择）、通知区

---

# ACE v3.29.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3290-2026-09-19). No breaking changes.

## In one line

**Esc** now has complete layered semantics (and a history picker), and the status line no longer flickers.

## ✨ Esc: one key, four layers

| Situation | What Esc does |
|---|---|
| a menu is open | close the menu (keep what you typed) |
| you typed something | clear the input |
| empty input, pressed twice within 0.8s | open the **history picker** |
| no history | nothing at all (no pretending) |

Enter **fills** the input line rather than sending it — that old line was written in a different context and should not be resent as-is. Esc closes the picker; a following Enter sends the empty input, not the history entry.

## ✨ Status line anti-flicker (0.3s window)

When the model switches tools rapidly, the status line used to jitter many times a second and looked broken. The first change applies immediately; further changes within the window wait for it to pass. A suppressed label is kept as pending, not dropped.

## ✨ Ctrl+T: task tree

`Ctrl+T` runs `/tasks` — goal, checklist and the running tool as one tree. Same on both input paths.

## 📋 Compatibility

- No breaking changes; new test section `[55]` (13 assertions)
- Still open: live progress inside collapsed groups, persistent permission rules (editable prefix rules + save scope), the notification area
