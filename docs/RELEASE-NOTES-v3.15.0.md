# ACE v3.15.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3150-2026-09-19)。无破坏性变更，升级不需要改配置。

## 一句话

Agent 每次动手都看得见了：**改了哪几行**（上色 diff）、命令**退出码是多少**、这一问**总共跑了几次工具**。

## 为什么

跑错一条命令，当场就知道；**改错一行，往往几天后才发现**。而此前 `file_write` 只回一个"写了多少字符"，`str_replace` 明明返回了 diff，终端却从来没显示过它——模型看得到，人看不到。这一版把「改了什么」摆到屏幕上。

## ✨ 写入类工具的卡片带 diff

```
  % str_replace ✓ [SUCCESS] · 0.00s · +1 -0
    已替换 1 处（匹配方式: exact）
    --- a/demo_notes.md
    +++ b/demo_notes.md
    @@ -2,4 +2,5 @@
      - 第一条
      - 第二条
    +- 第三条（新加的）
```

- `+` 行绿、`-` 行红、`@@` 区块头青，文件头按 dim —— 文件头不是"删了这行加了那行"，染成红绿会让每次 diff 都显得先删后加一整行
- 标题挂 `+N -M` 统计，一眼看出改动规模
- 折叠过的 diff 同样能用 `/expand` 展开

**三条边界**（都写在代码 docstring 里，不是事后补的说明）：

1. **新文件不给 diff**：全是 `+` 行没有信息量，还会把一次性写入的几百行灌进模型上下文
2. **凭据文件不读旧内容**：`.env` / `*.pem` / `id_rsa` 与"快照不留副本"复用同一份名单（SEC-04）——否则旧内容会进终端卡片，也会顺着工具结果进模型上下文
3. **超大文件不算 diff**：旧文件或新内容超过 200 KB 就跳过（读 10 MB 只为渲染 8 行，不值）

## ✨ 退出码 + 本轮工具时间线

- 命令类工具卡片标题带 `· exit N`：**"命令跑完了"和"命令成功"是两件事**，把退出码摆出来由人判断；非 0 时标题不再用成功的绿色
- 一轮里调用 ≥2 次工具时收尾给一行：`2 次工具调用 · 1.83s · file_write ✓ · str_replace ✓`（非 0 退出码就地标出）。只调一次工具时不打这行——那张卡片本身就是全部信息

## 🐛 顺带修掉的两处

- **同一份 diff 不再打印两遍**：`str_replace` 的 `content` 里本来就带着 diff，卡片现在只留一行摘要 + 单独渲染的 diff 段
- **mock 演示不再把 JSON 灌进回答**：模型"观察结果"优先取人说得出的一句（时间/摘要，截断 160 字符），此前整份 `data` JSON 会被原样写进回答，看着像 bug。同时把 mock 改成**第一轮判定剧本**——此前每轮靠关键词重新嗅探，而第二轮之后 prompt 已是工具结果回喂、没有用户原话（拦截剧本是靠结果里恰好带着 `id_rsa` 才蒙对的）

## 🛡️ 守卫

- `[10]`：覆盖写入返回 diff 且是合法 unified diff、新文件不给 diff、内容没变不给 diff、**`.env` 即便写入成功也不给 diff**、超大文件不给 diff
- `[9]`（走真实 `converse` 的集成断言）：卡片带 `+N -M`、`+` 行真的上绿、`-` 行真的上红、文件头不上红绿、正文不重复整份 diff、多工具时间线恰好一行、单工具没有时间线、`/expand` 能展开折叠的 diff
- `[34]`：`looks_like_diff` 正反例（`+ 列表` 不算 diff）、**文件头不计入增删**、`color_name` 五态、`colorize_diff` 按列截断与超限说明

其中 `.env` 那条断言**当场抓出了第一版的漏判**：`sensitive_target` 的名单里没有 `.env`，于是改用与快照相同的 SEC-04 名单。

## 📋 兼容性

- 无破坏性变更：配置、启动参数、权限/沙箱/审批语义、命令用法都没变
- 工具结果新增 `diff` / `summary` 两个字段（`file_write`）；`content` 内容不变，模型侧看到的格式不受影响
- 演示新增第四张图 `demo/demo_diff.svg`，`--check` 四张一起校验

---

# ACE v3.15.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3150-2026-09-19). No breaking changes; no config edits needed.

## In one line

Every action the agent takes is now visible: **which lines changed** (colourised diff), the command's **exit code**, and **how many tools ran** for this request.

## Why

Run the wrong command and you know immediately; **change the wrong line and you may not find out for days**. Yet `file_write` reported only a byte count, and `str_replace` has been returning a diff all along — the terminal simply never showed it. The model could see it; the human could not.

## ✨ Diffs on write-tool cards

```
  % str_replace ✓ [SUCCESS] · 0.00s · +1 -0
    已替换 1 处（匹配方式: exact）
    --- a/demo_notes.md
    +++ b/demo_notes.md
    @@ -2,4 +2,5 @@
    +- 第三条（新加的）
```

- `+` green, `-` red, `@@` hunk headers cyan, file headers dim — a file header is not "a line removed and a line added", and colouring it red/green makes every diff look like it rewrote a line
- The title carries a `+N -M` stat so the size of the change is visible at a glance
- A folded diff can still be expanded with `/expand`

**Three boundaries** (documented in the code, not bolted on afterwards):

1. **No diff for new files** — all `+` lines, no information, and it would pour hundreds of lines into the model context
2. **Credential files are never re-read** — `.env` / `*.pem` / `id_rsa` share the same SEC-04 list the snapshot uses to refuse copies; otherwise the old contents would land in the terminal card *and* travel back into the model context through the tool result
3. **Huge files are skipped** — either side over 200 KB and there is no diff (reading 10 MB to render 8 lines is a bad trade)

## ✨ Exit codes and a per-request tool timeline

- Command tools now show `· exit N` in the card title: **"the command finished" and "the command succeeded" are different things**, so the number is shown and the human decides; a non-zero exit no longer uses the success green
- When a request calls two or more tools, it ends with `2 tool calls · 1.83s · file_write ✓ · str_replace ✓` (non-zero exits marked inline). A single tool call prints nothing — that card is already the whole story

## 🐛 Two fixes along the way

- **The same diff is no longer printed twice**: `str_replace`'s `content` already contained it; the card now shows a one-line summary plus a separately rendered diff block
- **The mock demo no longer dumps JSON into the answer**: the mock's "observation" prefers a human sentence (time/summary, capped at 160 chars). The mock also now decides its script on the **first** round — previously it re-sniffed keywords every round, but from round two on the prompt is a tool result with no user words in it (the blocked script only worked because the result happened to contain `id_rsa`)

## 🛡️ Guards

- `[10]`: overwrite returns a valid unified diff, new files get none, unchanged content gets none, **`.env` gets none even when the write succeeds**, oversized files get none
- `[9]` (integration assertions driving a real `converse`): the `+N -M` stat, `+` lines actually green, `-` lines actually red, headers not red/green, no duplicated diff body, exactly one timeline line for multiple tools, no timeline for one tool, `/expand` expanding a folded diff
- `[34]`: `looks_like_diff` positives and negatives (`+ list` is not a diff), **file headers excluded from add/remove counts**, `color_name`'s five cases, `colorize_diff` column truncation and cap notice

The `.env` assertion **caught a real miss in the first implementation**: `sensitive_target` does not list `.env`, so the check was switched to the SEC-04 snapshot list.

## 📋 Compatibility

- No breaking changes: config, CLI flags, permission/sandbox/approval semantics and command usage are untouched
- `file_write` results gain `diff` and `summary` fields; `content` is unchanged, so the format the model sees is unaffected
- A fourth demo image (`demo/demo_diff.svg`) joins the `--check` set
