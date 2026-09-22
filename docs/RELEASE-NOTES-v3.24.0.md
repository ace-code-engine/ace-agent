# ACE v3.24.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3240-2026-09-19)。无破坏性变更。

## 一句话

「全套 UI 与交互」的第三批：**对话框**。所有提问现在长一个样 —— 单选/多选、分组、进度条、页签、按键提示；顺带把两件一直没说清的事说清了：会话级授权到底放行了什么，以及取消配置向导是不是真的什么都没改。

## ✨ 所有提问长一个样

此前"弹个框问一句"散在三处（权限档位一个选择器、`/config` 一串 `input()`、联网开关又一套），同一个软件里问同一件事有两三种长相，每次都得重新学。现在是一份数据 + 一个渲染器：

```
┌ 权限: 会话级规则 ────────────────────────────────────────────────────────────────────┐
│ 已授予 ████░░░░░░░░░░░░░░░░░░░░ 3/15 20%                                             │
│ 勾选 = 本次会话不再逐次确认；取消勾选立刻收回                                        │
│ — 外发                                                                               │
│   [ ] api_post  本次会话免确认  按设计拒绝会话级授权（不可选）                       │
│ — 逐次确认                                                                           │
│   [ ] terminal_exec  本次会话免确认  按设计拒绝会话级授权（不可选）                  │
│ — 写类                                                                               │
│ ▶ [x] file_write  本次会话免确认                                                     │
│   [ ] str_replace  本次会话免确认                                                    │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ Space 勾选 · Enter 确认 · Esc 取消 · 已选 1                                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- 框线**宽度严格对齐**：中文按两列算，进度条、页签、脚注都算进去（歪掉的框比没有框更难看，所以这条是拿显示列宽当断言钉住的）
- 多选复用同一个模糊搜索浮层：输入即过滤、`Space` 勾选、`Enter` 确认、`Esc` 取消，脚注显示已选条数
- 进度条在总数未知时显示 `—`，**不编百分比**
- 被设计成不可选的条目**照样列出来并标明原因** —— 让它消失，你会以为"这功能漏了"

## ✨ `/permission rules`：会话级授权终于看得见、撤得掉

问"要不要临时授权"时回答 `a`，会给出**会话级授权**（本次会话不再问）。可此前没有任何地方能看见你放行过什么，也撤不掉 —— 授权只进不出，只能靠 `/clear` 或重启收拾。

现在：

```
❯ /permission rules
```

- 勾选 = 本次会话不再逐次确认；**取消勾选 = 立刻收回**
- 候选只列**当前档位下仍要请示**的工具（已经免费放行的不列，那是噪音）
- 三类结果分开报，绝不混成一句"已更新"：
  - 真的进了会话级规则
  - **按设计拒绝**会话级授权的（`terminal_exec`、外发工具）→ 明说"只能单次"，你不会以为整场免问
  - 收回的
- 非交互会话（脚本/管道）只列出规则，什么都不改

## ✨ 配置向导：能后退、输错当场重问，取消就是真的没改

`/config` 现在是一个真正的状态机：

- 每一步**输错当场重问**（旧行为是"编号无效就跳过"，跳过之后你会以为设置生效了）
- 按 `b` **退回上一步**；模型那一步的可选值跟着上一步选的提供商走
- **答案先攒着，跑完才落库**。旧实现是边问边改内存里的配置，中途 Ctrl+C 说"配置未保存"，可 base_url/model 早被改过一轮了 —— 说话与事实不一致，而且那份配置还可能被顺手写盘。现在取消 = 逐字段未变（有断言盯着）

## 📋 兼容性

- 无破坏性变更：选择器取值的语义没变（缺 `prompt_toolkit` 时照旧降级，不阻塞）
- 新增 31 个 i18n 键（`rules_*` / `wizard_*`），中英日齐全
- `docs/COMMANDS.md` 补 `/permission rules`；新增测试段 `[50]`（55 项断言）

---

# ACE v3.24.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3240-2026-09-19). No breaking changes.

## In one line

The third batch of the full UI/interaction pass covers **dialogs**: every question the app asks now looks the same — single/multi select, groups, progress, tabs, key hints — and two things that were never clear are now clear: what session-level permissions you actually granted, and whether cancelling the config wizard really changed nothing.

## ✨ Every question looks the same

Asking one question used to be three different implementations (a selector for permission levels, a chain of `input()` for `/config`, another one for the network toggle). One model and one renderer now cover all of them:

- box lines are **exactly width-aligned** (CJK counts as two columns; progress bar, tabs and footer all measured) — a crooked box is worse than no box, so this is pinned by assertions
- multi-select rides the same fuzzy-search overlay: type to filter, `Space` to check, `Enter` to confirm, `Esc` to cancel, with the checked count in the footer
- the progress bar shows `—` when the total is unknown; it never invents a percentage
- items that are disabled by design are **still listed, with the reason** — hiding them makes you think the feature is missing

## ✨ `/permission rules`: session grants are finally visible and revocable

Answering `a` to a permission prompt grants a **session-level** allowance (no more prompts this session). Until now nothing showed what you had granted and nothing could take it back — grants only went in, and cleaning up meant `/clear` or a restart.

```
❯ /permission rules
```

- checking a tool stops the prompts for this session; **unchecking revokes it immediately**
- the list only offers tools that **still ask** at the current level (already-allowed tools would be noise)
- three outcomes are reported separately, never merged into "updated":
  - actually added to the session rules
  - **refused by design** (`terminal_exec`, outbound tools) — it says "per-call only", so you do not believe the whole session is exempt
  - revoked
- in a non-interactive session it lists the rules and changes nothing

## ✨ Config wizard: step back, re-ask on bad input, and cancel really cancels

`/config` is a real state machine now:

- invalid input is **re-asked on the spot** (it used to print "invalid, skipping", which reads like it applied)
- `b` goes back one step; the model step's choices follow the provider chosen above
- **answers are collected first and applied at the end.** The old flow mutated the in-memory config as it went, so Ctrl+C printed "not saved" while base_url/model had already changed — and that config could still be written to disk. Cancelling now leaves every field untouched (asserted).

## 📋 Compatibility

- No breaking changes: selector semantics are unchanged (and it still degrades when `prompt_toolkit` is missing)
- 31 new i18n keys (`rules_*` / `wizard_*`), complete in Chinese, English and Japanese
- `docs/COMMANDS.md` gains `/permission rules`; new test section `[50]` (55 assertions)
