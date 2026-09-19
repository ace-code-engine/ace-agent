# ACE v3.13.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3130-2026-09-19)。无破坏性变更，升级不需要改配置。

## 一句话

把"上下文还能撑多久"从"压缩之后才知道"变成常驻可见的一个数——并且明确告诉你它是估算。

## ✨ 底栏多了一段上下文占比

底栏此前显示 `模型 | 权限 | 沙箱 | 联网 | 目标 | 轮数/工具数`，就是没有"还剩多少上下文"。用户唯一的信号是压缩真的发生后的那句提示，而那时历史已经被折叠过了。现在底栏末尾多一段：

```
上下文38%
```

颜色即语义：

| 颜色 | 含义 |
|---|---|
| 灰 | 有余量 |
| 黄 | 已用掉压缩触发点的 80% |
| 红 | 已达触发点，下一轮就会压缩 |

窗口未知时这一项**不显示**——不拿 0 当分母造一个假百分比。

## ✨ `/status` 有明细，逼近阈值会提前提醒

```
  上下文: 约 12480 tokens / 窗口 32768（38%，压缩触发点约 23040；估算值，不是服务端读数）
```

- 数字口径与真正的压缩决策**共用同一个策略构造点**，不会出现"底栏说 38% 而实际已经压缩了"。一个自相矛盾的数，用户看两次就不再相信了
- 底层沿用既有的 `cli/ace_context.estimate_tokens`：**中文按字计**（中文一个字通常就是一个 token，按 4 字符折算会把中文历史低估到实际的四分之一）
- 逼近触发点时，在请求发出**之前**提醒一次，并告诉你还有别的选择：继续当前话题，或者 `/clear` 开一段新的。同一档只提醒一次（按触发点的 10% 一档），跨档才再提醒——每轮刷一行警告，用户很快就会学会无视它
- 用 `--no-compact` 关掉压缩后，`/status` 会追加一句"超出窗口直接硬截断"，免得以为还有压缩兜底

**它是估算，我们把它当估算说。** 文案里一律带"约"，并写明"不是服务端读数"——不同厂商对同一条消息的计费口径本来就不一致，把它写成精确值才是误导。

## 🛡️ 守卫

`[9]` +17 条：三档边界（按 4096 窗口的真实阈值算）、窗口未知 → `unknown` 且底栏空串、`over` 的 tokens 确实 ≥ 触发点、`pct` 与 `trigger_pct` 两个分母不混用、**"显示口径 = 决策口径"的同源不变量**、底栏真的含占比且颜色随状态变、`/status` 真的打出 tokens 与窗口、提醒的节流（首次提醒 → 同档沉默 → 跨档再提醒 → 回安全区沉默 → `/clear` 后水位归零）。

`[11]` 的键集一致性断言自动覆盖新增的 5 个 i18n 键（断言里的键数是从文件读的，所以从 196 变 201 不用改断言）。

## 📋 兼容性

- 无破坏性变更：配置文件、启动参数、权限/沙箱/审批三维度语义、命令用法都没变
- 对外新增的 5 个 i18n 键中英日三语齐全；`docs/COMMANDS.md` 补了底栏图例与 `/status` 的上下文行

---

# ACE v3.13.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3130-2026-09-19). No breaking changes; no config edits needed.

## In one line

How much context is left went from "you find out when compaction happens" to a number that is always on screen — explicitly labelled as an estimate.

## ✨ A context figure in the footer

The footer showed `model | permission | sandbox | network | goal | rounds/tools` — everything except how much context was left. The only signal was the notice printed *after* compaction, by which point history had already been folded. Now the footer ends with:

```
ctx 38%
```

Colour is the semantics:

| Colour | Meaning |
|---|---|
| grey | room to spare |
| yellow | 80% of the compaction trigger consumed |
| red | trigger reached — the next round compacts |

When the window is unknown the item is **not shown** — no fake percentage computed against a zero denominator.

## ✨ `/status` detail and a warning before the trigger

```
  Context: ~12480 tokens / window 32768 (38%, compaction triggers near 23040; an estimate, not a server reading)
```

- The displayed figure and the actual compaction decision **share one policy constructor**, so the footer cannot say 38% while the history has in fact already been compacted. A number that contradicts reality stops being trusted after about two sightings
- It reuses the existing `cli/ace_context.estimate_tokens`: **CJK counts per character** (one Chinese character is usually one token; dividing by four would undercount Chinese history to a quarter of its real size)
- As the trigger approaches, a warning fires **before** the request goes out and names the alternatives: stay on the topic, or `/clear` for a fresh one. It is throttled per 10% band, so crossing a band re-arms it — a warning printed every round is a warning nobody reads
- With `--no-compact`, `/status` adds a line noting that history is hard-truncated past the window, so it does not look like compaction is still there as a safety net

**It is an estimate, and it says so.** The wording carries "~" and "an estimate, not a server reading" — providers do not agree on how they count the same message, so presenting it as exact would be the actual misleading move.

## 🛡️ Guards

`[9]` +17: band boundaries against the real thresholds for a 4096 window, unknown window → `unknown` with an empty footer segment, `over` tokens genuinely ≥ trigger, `pct` and `trigger_pct` denominators never mixed, a **"display policy = decision policy" invariant**, the footer really carrying the figure with the colour tracking state, `/status` really printing tokens and window, and the warning throttle (first warn → same band silent → next band re-arms → back in the safe zone silent → `/clear` resets the watermark).

`[11]`'s key-parity assertion covers the 5 new i18n keys automatically, since the key count is read from the files rather than hard-coded.

## 📋 Compatibility

- No breaking changes: config format, CLI flags, the permission/sandbox/approval axes and command usage are untouched
- The 5 new i18n keys ship in all three languages; `docs/COMMANDS.md` documents the footer legend and the `/status` context line
