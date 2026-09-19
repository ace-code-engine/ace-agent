# ACE v3.20.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3200-2026-09-19)。无破坏性变更。

## 一句话

会话能列、能续、能分叉、能退回；任务能拆成逐项清单 —— 而且**你和模型看的是同一份**。

## ✨ 会话管理

| 命令 | 作用 |
|---|---|
| `/sessions [编号]` | 列最近会话（时间 / 轮数 / 首句 / **是否被压过**）；交互终端里可选中续聊 |
| `/resume <编号\|文件名>` | 续聊一个已有会话：历史按它重建，**之后的事件也写进那份日志**（是续聊，不是复制） |
| `/fork [编号]` | 以某会话为起点开**一段新会话**（新文件 + 带最近 10 轮消息） |
| `/rewind [轮次]` | 把**对话**退回到第 n 轮之后（默认退掉最后一轮） |

两个刻意的决定：

- **`/rewind` 只动对话，不动文件。** 文件回退是 `/rollback`（快照）的事，输出里每次都写明这一点 —— "rewind 一下文件也回来了"是危险的误会。
- **`/fork` 不共享历史。** 两条线各自往后走；要做合并那是版本控制的问题，不是聊天界面该假装能做的事。

另外，列表里会标出"压缩过 N 次"：被压过就说明这段会话其实已经忘掉一部分了，这件事该看得见。

## ✨ 逐项待办清单

```
/ todo add 跑全量测试
/ todo add 写更新介绍
/ todo start 1
/ todo done 1
```

- 模型侧对应工具 `todo_write`（`action` = add / start / done / remove / clear）；**多步任务请先列清单再动手**
- 清单非空时**底栏显示 `待办 1/3`**，全部完成时变绿
- 状态只有三档（未开始 / 进行中 / 完成）—— 没有"取消"：不做就删掉，留着只会让进度数字失真
- 清单存进会话事件日志，`/resume` 或重启后按日志重放，**换会话不会丢**

`todo_write` 挂在**只读权限组**：它只动会话状态、不碰文件。归到写组会让 readonly 会话下"列个清单"都要授权一次 —— 那不是安全，是噪音。

## 🛡️ 守卫

`[46]`（可 `--only 46`）：待办状态机与事件重放、会话摘要与四种 rewind 边界，以及**真文件 + 真 CLI** 的端到端 —— `/resume` 后新消息真的写进被续聊的那份日志、`/rewind` 之后磁盘上的文件一字未动、`/fork` 真的开新文件并把历史复制过去、待办能从日志重放出来。

## 🐛 过程中被断言抓出的三处

- 「第 n 轮结束」最初写成"第一条 assistant 之后就停"，但一轮里可能有多条 assistant（工具往返），结果第 2 轮只回出 3 条消息 —— 改成以"下一条 user 出现"为界
- 换会话后待办存储没重建（它持有旧日志对象），`todo/*` 事件被写进上一个会话的文件 → 重放新日志得到空清单
- 新工具 `todo_write` 忘了登记三处：三个运行时提示词、卡片符号表、外部内容来源表 —— 三处守卫各自报了出来

## 📋 兼容性

- 无破坏性变更：不加参数时行为与之前一致；新增 31 个 i18n 键，中英日三语齐全
- 新增工具 `todo_write`（只读组），需要时模型会自己用；你不用它也不会影响任何既有流程

---

# ACE v3.20.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3200-2026-09-19). No breaking changes.

## In one line

Sessions can be listed, continued, forked and rewound; tasks can be broken into an itemised checklist — and **you and the model look at the same list**.

## ✨ Session management

| Command | Effect |
|---|---|
| `/sessions [index]` | List recent sessions (time / turns / first line / **whether it was compacted**); pick one interactively to continue |
| `/resume <index\|filename>` | Continue an existing session: history is rebuilt from it and **subsequent events are appended to that same log** (continuing, not copying) |
| `/fork [index]` | Start a **new session** seeded from another one (new file + the last 10 turns) |
| `/rewind [turn]` | Rewind the **conversation** to after turn N (default: drop the last turn) |

Two deliberate decisions:

- **`/rewind` touches the conversation only, never files.** Restoring files is `/rollback` (snapshots), and every run says so — "rewind must have brought the files back too" is a dangerous misunderstanding.
- **`/fork` does not share history.** The two lines diverge; merging them is version control's problem, not something a chat UI should pretend to solve.

The listing also marks "compacted N×": if it was compacted, that session has already forgotten part of itself, and that deserves to be visible.

## ✨ Itemised todo list

```
/ todo add 跑全量测试
/ todo add 写更新介绍
/ todo start 1
/ todo done 1
```

- The model side is the `todo_write` tool (`action` = add / start / done / remove / clear); **list the steps before starting multi-step work**
- While non-empty, the footer shows `todo 1/3` and turns green once everything is done
- Three states only (pending / in progress / done) — there is no "cancelled": delete what you will not do, otherwise the progress number lies
- The list lives in the session event log and is replayed on `/resume` or restart, so **switching sessions does not lose it**

`todo_write` sits in the **read-only permission group**: it only touches session state, never files. Putting it in the write group would make "write a checklist" require authorisation in a readonly session — that is not safety, that is noise.

## 🛡️ Guards

`[46]` (runnable as `--only 46`): the todo state machine and event replay, session summaries and four rewind boundaries, plus **real files and a real CLI** end to end — new messages after `/resume` genuinely land in the continued log, `/rewind` leaves every file on disk byte-identical, `/fork` really opens a new file and copies the history across, and todos replay from the log.

## 🐛 Three things the assertions caught

- "End of turn N" was first implemented as "stop after the first assistant message", but a turn can contain several assistant messages (tool rounds) — turn 2 came back with only 3 messages. Now the boundary is "the next user message".
- The todo store was not rebuilt after switching sessions (it held the old log object), so `todo/*` events landed in the previous session's file and replaying the new log returned an empty list.
- The new `todo_write` tool was missing from three registries: the three runtime prompts, the card glyph tables, and the external-content source table. Three separate guards said so.

## 📋 Compatibility

- No breaking changes: without the new commands, behaviour is unchanged; 31 new i18n keys, complete in Chinese, English and Japanese
- One new tool (`todo_write`, read-only group); the model uses it when useful and ignoring it breaks nothing
