# ACE v3.21.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3210-2026-09-19)。无破坏性变更。

## 一句话

五条能力线的最后一条：改完的东西能**在编辑器里审**、图能**发给模型看**、键位按你的习惯改、花了多少钱心里有数。

## ✨ `/review`：改动交给编辑器审，再读回来

模型改完一个文件，你往往只想动其中一两行。`/review` 把这个过程做成一条命令：

1. 上一处改动写成一份 **unified diff** 补丁
2. 在 `$ACE_EDITOR` / `$VISUAL` / `$EDITOR` 里打开
3. 你改完保存退出 → 它**读回补丁并应用**到源文件

两个刻意的决定：

- **回填走的是同一道执行层闸门**（`file_write` 工具路径：快照、权限、审计都在），不是绕过工具直接写盘。
- 应用器是自己实现的**最小 unified diff**（`core/ace_patch.py`）：不依赖 `patch(1)`（Windows 上没有），也不依赖 `git apply`（要求仓库）。上下文逐字匹配，**对不上就整体不应用**并指出第几行不匹配 —— 半个补丁落盘比不落盘更糟。

没有编辑器时它明说"补丁在哪儿、你自己应用"，不假装打开了；补丁留在 `.ace_review/*.diff` 随时可复查。

## ✨ 图片输入（`@image <路径>`）

```bash
@image ~/Desktop/报错截图.png
看一下这个报错
```

- png / jpg / jpeg / webp / gif，单张 ≤4MB，最多 3 张；底栏显示 `图1` 直到发出去
- 按接口格式组装（OpenAI 用 `data:` URL，Anthropic 用 `base64` source）
- **注意：图片会原样发给模型提供商**（base64 进请求体）—— 这不是本地预览，敏感截图先自己确认。挂上时会提示这一点
- 超限 / 格式不对 / 读不出来都如实报原因，**不静默跳过**："以为发出去了其实没发"是这类功能最容易出的错

没有图片时消息 content 仍然是**字符串**（与旧行为逐字节一致）—— 各家对纯字符串的处理最稳。

## ✨ vim 模式与自定义键位

```json
"vim_mode": true,
"keybindings": {"c-e": "/expand", "f5": "/todo"}
```

- `/vim [on|off]` 热切换；打开后给输入行接 `EditingMode.VI`（Esc 回正常模式，i/a 进插入）
- 自定义键位走的是与 F1–F4 **同一条通道**（退出输入行 → 执行斜杠命令），不另开一套执行面
- 保留键（`enter` / `esc` / `Ctrl+C` 等）不许覆盖；非法键名与"值不是斜杠命令"的项会丢弃，`/vim` 列出实际生效的键位

## ✨ 成本估算（每会话）

`/status` 里多一行：

```
成本: $0.0037（估算） · 输入 ≈12000 / 输出 ≈800 tokens
```

**它是估算，不是账单**，两个不确定来源都写在明面上：token 数按字符估（中文按字），价格表是**本地快照**（厂商随时会改），用配置 `pricing` 覆盖：

```json
"pricing": {"deepseek-v4-flash": {"in": 0.28, "out": 0.42}}
```

键按**子串**匹配、最长优先（写 `deepseek` 就能命中 `deepseek-v4-flash`）。查不到价格时显示"价格未知"，**绝不编一个数字**。

`--json` 模式下，`session_end` 事件带上 `cost_estimate_usd` 与输入/输出 token —— 脚本可以直接记账。

## 🐛 过程中被断言抓出的一处

写补丁时多补了一个换行，导致末尾空行被解析器当成"上下文空行"，回填时报"文件已结束"。现在解析前先丢掉末尾空行，写入端也不再重复补换行。

## 🛡️ 守卫

`[47]`（可 `--only 47`）：补丁应用器的五类边界、图片块的两套格式与四类拒绝、成本的价格匹配与格式分档、键位解析的白名单/黑名单，以及**真文件 + 真 CLI**：`@image` 挂图后对话里真的组装出 image 块并在发送后清空；`/review` 用脚本冒充编辑器改补丁 → 源文件真的被回填且留下快照与审计；编辑器不改动时如实说"什么都没做"。

## 📋 兼容性

- 无破坏性变更：不配 `vim_mode`/`keybindings`/`pricing`、不打 `@image`、不用 `/review` 时，行为与之前一致
- 新增 25 个 i18n 键，中英日三语齐全

---

# ACE v3.21.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3210-2026-09-19). No breaking changes.

## In one line

The last of the five capability lines: review a change **in your editor**, send an **image** to the model, rebind keys to your habits, and see what the session cost.

## ✨ `/review`: hand the change to your editor, read it back

After the model edits a file you usually want to touch only a line or two. `/review` makes that a single command:

1. the last change is written out as a **unified diff** patch
2. it opens in `$ACE_EDITOR` / `$VISUAL` / `$EDITOR`
3. you edit, save and quit → it **reads the patch back and applies it** to the source file

Two deliberate decisions:

- **The write-back goes through the same execution-layer gate** (the `file_write` tool path: snapshot, permission, audit), not straight to disk.
- The applier is our own **minimal unified diff** (`core/ace_patch.py`): it depends neither on `patch(1)` (absent on Windows) nor `git apply` (requires a repo). Context lines must match exactly; a mismatch means **nothing is applied** and the offending line is named — half a patch on disk is worse than none.

With no editor configured it says where the patch is and that you can apply it yourself, rather than pretending to have opened something; patches stay in `.ace_review/*.diff` for review.

## ✨ Image input (`@image <path>`)

```bash
@image ~/Desktop/error-screenshot.png
take a look at this error
```

- png / jpg / jpeg / webp / gif, ≤4MB each, up to 3; the footer shows `img1` until the turn is sent
- Blocks are built per wire format (OpenAI `data:` URL, Anthropic `base64` source)
- **Note: the image is sent to the model provider as-is** (base64 in the request body) — this is not a local preview, so check sensitive screenshots first. The command says so when you attach one.
- Oversized, unsupported or unreadable files are reported honestly and **never silently skipped** ("I thought it was sent" is the classic failure of this feature)

Without images the message content stays a **string** (byte-identical to the old behaviour) — providers handle plain strings most reliably.

## ✨ vi mode and custom keybindings

```json
"vim_mode": true,
"keybindings": {"c-e": "/expand", "f5": "/todo"}
```

- `/vim [on|off]` toggles it live; with it on the prompt uses `EditingMode.VI` (Esc for normal mode, i/a to insert)
- Custom keys go through the **same channel as F1–F4** (leave the prompt, run the slash command) — no second execution surface
- Reserved keys (`enter` / `esc` / `Ctrl+C` …) cannot be rebound; invalid key names and values that are not slash commands are dropped, and `/vim` lists what is actually in effect

## ✨ Cost estimate (per session)

`/status` gains a line:

```
Cost: $0.0037 (estimate) · in ≈12000 / out ≈800 tokens
```

**It is an estimate, not a bill**, and both sources of uncertainty are stated: tokens are estimated from characters (CJK counted per character), and the price table is a **local snapshot** (vendors change prices). Override it in config:

```json
"pricing": {"deepseek-v4-flash": {"in": 0.28, "out": 0.42}}
```

Keys match by **substring**, longest first (writing `deepseek` covers `deepseek-v4-flash`). When no price matches, it says "price unknown" — it **never invents a number**.

In `--json` mode the `session_end` event carries `cost_estimate_usd` plus input/output tokens, so scripts can do their own accounting.

## 🐛 One bug the assertions caught

The patch writer added an extra trailing newline, so the trailing blank line was parsed as a "context blank line" and applying reported "file ended". The parser now drops trailing blank lines, and the writer no longer adds a second newline.

## 🛡️ Guards

`[47]` (runnable as `--only 47`): five boundary cases for the patch applier, both wire formats and four rejection paths for images, price matching and formatting tiers for cost, and the whitelist/blacklist of keybinding parsing — plus **real files and a real CLI**: attaching an image really composes an image block into the message and clears the pending list once sent; `/review` with a script posing as the editor really writes the source file back and leaves a snapshot and audit trail; when the editor changes nothing it says so.

## 📋 Compatibility

- No breaking changes: without `vim_mode`/`keybindings`/`pricing`, without `@image` and without `/review`, behaviour is unchanged
- 25 new i18n keys, complete in Chinese, English and Japanese
