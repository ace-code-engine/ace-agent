# ACE v3.33.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3330-2026-09-19)。无破坏性变更。

## 一句话

按社区那份《Claude Code 用户体验深潜》整理出的交互规格开工第一批：**等待时的状态不再靠文字**，以及**通知与窗口标题**两条一直在缺的通道。

## ✨ 等待指示器：扫光速度就是语义

| 阶段 | 形态 | 速度 |
|---|---|---|
| 等首字节（网络） | `· ˙ • ˙` | 快闪 0.08s |
| 模型推理 | `◐ ◓ ◑ ◒` | 慢转 0.24s |
| 正式回答 | `◈ ◇ ◆ ◇` | 中速 0.12s |
| 工具参数流入 | `▖ ▘ ▝ ▗` | 0.10s |
| 工具执行 | `▁ ▃ ▅ ▇ ▅ ▃` | 脉冲 0.16s |

不用读文字就能分辨"在等网络"还是"模型在长思考"。

**卡住了会被颜色说出来**：静默超过 3 秒后，颜色从主题绿**平滑过渡到告警红**，强度随时间递增。
低色深终端在过半处**离散跳变**到告警色（降级后"不太对"的语义仍然成立）。

**动效必须有替代**：开了"减少动效"就固定首帧并补一行文字标记 —— 屏幕不动时也能看出异常。
**工具在跑时不做卡住判定**：一条长命令跑 60 秒是正常的，把它染红只会教你忽略颜色。

## ✨ 通知区：同时只显示一条

以前的通知就是 `print` 一行，谁都能盖掉谁。现在入队管理：

- 按优先级插队（需要你做决定 > 出错 > 进度 > 提示）—— 低优先级的提示顶不掉刚打出来的错误
- 同一条文本重复出现只刷新时间（不刷屏）；按优先级给 TTL 自动让位
- **需要你做决定的那种永不自动消失**（授权请求不会自己溜走）

## ✨ 窗口标题与系统通知

- 标题常驻 `ACE · 模型 · 状态`，需要你确认时变成 **等你确认** —— 切到别的窗口也知道要回来
- 一轮跑完 **超过 30 秒** 才发系统通知（坐在终端前的人不需要被打断）
- 支持三种通知约定（OSC 9 / 777 / 99，终端认哪个都行），标题走 OSC 2
- **没有 TTY 一个字节都不发**：管道/CI 里塞转义序列只会污染给机器读的输出；`ACE_NO_NOTIFY=1` 也能关

## 📋 兼容性

- 无破坏性变更；新增 3 个 i18n 键（中英日各 517 键对齐）；新增测试段 `[59]`（26 项断言）
- 顺带修掉：CI 的 compileall 清单漏了新的根级 `setup_env.py`（结构守卫当场报出来）

## 📋 下一批（按规格缺口排序，我会接着做）

1. **流式增量渲染 + 稳定前缀缓存**：正文边到边上屏，Markdown 只重解析"不稳定尾块"
2. **权限对话框 200ms 防误触宽限期**：弹出瞬间的飞行按键不算介入
3. 工具状态点四态 + 并行同帧同步 / 内联 diff 交互化 / 错误自愈与降级提示合并
4. Ctrl+F 增量搜索 + 鼠标命中测试 / 和弦键位（按上下文作用域）

---

# ACE v3.33.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3330-2026-09-19). No breaking changes.

## In one line

First batch of work from a community deep-dive on Claude Code's UX: waiting states that no longer need words, plus the notification and window-title channels that were missing.

## ✨ Spinner: the sweep speed *is* the meaning

Five phases, each with its own glyph set and speed — waiting for the first byte flashes fast, reasoning turns slowly, answering rotates at medium speed, tool arguments advance through the corners, tool execution pulses. You can tell "waiting on the network" from "the model is thinking" without reading a word.

**Being stuck is said with colour**: after 3 seconds of silence the colour interpolates from theme green to warning red, increasing with idle time. Low-colour terminals jump discretely to the warning colour past the halfway point, so the meaning survives the downgrade.

**Motion needs a substitute**: with reduced motion the first frame is frozen and a text marker is appended — a still screen still tells you something is wrong. **A running tool is never judged stuck**: a long command is normal, and painting it red only teaches you to ignore colour.

## ✨ Notification area: one at a time

Notifications are queued rather than printed: priority ordering (needs-you > error > progress > hint) so a low-priority hint cannot overwrite a fresh error, de-duplication by text, and TTL expiry per priority — while **anything that needs your decision never expires on its own**.

## ✨ Window title and desktop notifications

The title carries `ACE · model · state` and switches to **waiting for you** when a permission request appears, so you can tell from another window that you are needed. A finished turn only notifies if it took over 30 seconds. Three notification conventions are supported (OSC 9 / 777 / 99) plus OSC 2 for the title — and **without a TTY nothing is emitted at all**, because stray escape sequences would pollute machine-readable output (`ACE_NO_NOTIFY=1` also disables it).

## 📋 Compatibility

- No breaking changes; 3 new i18n keys (517 per locale, aligned); new test section `[59]` (26 assertions)
- Also fixed: the CI compileall list was missing the new root-level `setup_env.py` (the structure guard caught it)

## 📋 Next batch

1. **Streaming incremental rendering with a stable-prefix cache** — text on screen as it arrives, Markdown re-parsing only the unstable tail
2. **200ms anti-misfire grace period on permission dialogs** — in-flight keystrokes do not count as consent
3. Four-state tool dots with same-frame synchronisation / interactive inline diffs / merged self-healing error notices
4. Ctrl+F incremental search with mouse hit-testing / chorded keybindings scoped by context
