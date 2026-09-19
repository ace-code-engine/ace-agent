# ACE v3.18.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3180-2026-09-19)。无破坏性变更。

## 一句话

把"你自己的规矩"接进来：**钩子**能在工具执行前拦下它，**自定义命令**不用每次重敲，**插件目录**一个目录装一套扩展。

## ✨ 事件钩子（hooks）

四个事件，任何语言都能写：

| 事件 | 时机 | 能做什么 |
|---|---|---|
| `session_start` | 会话建立 | 记一笔、准备环境 |
| `user_prompt` | 输入进模型**之前** | 补充上下文，或**整轮拦下**（根本不发） |
| `pre_tool` | 工具**执行之前**（权限已放行） | 拦下这次调用，理由回给模型 |
| `post_tool` | 工具执行之后 | 记审计、补充上下文（改不了已发生的事） |
| `session_end` | 会话结束 | 收尾、汇总 |

```bash
# stdin 收到
{"event":"pre_tool","tool":"file_write","params":{"path":"migrations/001.sql"}}

# stdout 回（可空）；退出码 2 = 拦截
{"decision":"block","reason":"migrations/ 下的文件必须人工改"}
```

**默认是 fail-close**：钩子崩了、超时了、输出大到离谱，都**不算**"检查通过"。那正是"我加了检查、检查其实没跑"的最坏情形。要宽松就显式写 `"on_error": "warn"`。

配置：`~/.ai_code.json` 的 `hooks`，或项目内 `.ace/hooks.json`（**追加**生效）；插件也能带钩子。`/hooks` 看装了哪些、上次结果如何。

## ✨ 自定义斜杠命令（`.ace/commands/*.md`）

```markdown
---
description: 跑全量测试并逐条列失败项
argument-hint: [段号]
---
请运行 python test_all.py $ARGUMENTS，失败项逐条列出；不要改动测试文件。
```

文件名就是命令名 → `/review 40`。`$ARGUMENTS` / `$1` 代入参数；没写 frontmatter 也认。

两条刻意的取舍：**不引入 YAML 依赖**（核心零依赖是硬约束，需要的只是"描述 + 参数提示"）；**内置命令优先**，`/help` 这类永远不会被自定义命令顶掉。

自定义命令展开成一段提示词，走正常对话流程 —— 所以模型的权限、审批、审计一样管得住它。

## ✨ 插件目录（`.ace/plugins/<名>/`）

```
.ace/plugins/myplugin/
├── plugin.json          # 可选
├── commands/*.md        # → /myplugin:review（自动加前缀，不会撞名）
└── hooks.json           # → 追加生效
```

坏插件只影响它自己，`/plugins` 会显示原因。

**这一版插件不能带工具**：tools 需要 Python 模块，那等于让插件在进程内跑代码 —— 比"命令 + 钩子"大得多的信任面。要做工具扩展，用 MCP。

## 🛡️ 边界（与 MCP 同一条）

钩子和插件里的钩子都是**你自己配置的本地命令，不在 ACE 的沙箱里**。执行层决定"要不要跑它、它说的话算不算数"，管不了它内部干什么 —— **只装你信得过的**。

两条具体约束：被 `pre_tool` 拦下**不计入安全违规**（那是团队规矩，不是有人在试探边界）；钩子**拿不到文件内容**（参数里超长字段被截断），要读自己读。

## 📋 兼容性

- 无破坏性变更：不配 `hooks`、不放 `.ace/` 目录时行为与之前完全一致
- 新增 17 个 i18n 键，中英日三语齐全；完整协议见新增的 [`docs/EXTENDING.md`](../docs/EXTENDING.md)

---

# ACE v3.18.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3180-2026-09-19). No breaking changes.

## In one line

Your own rules, wired in: **hooks** can stop a tool before it runs, **custom commands** stop you retyping the same paragraph, and a **plugin directory** packages a set of extensions.

## ✨ Event hooks

| Event | When | What it can do |
|---|---|---|
| `session_start` | session opens | log it, prepare the environment |
| `user_prompt` | before the model sees the input | add context, or **block the whole turn** (nothing is sent) |
| `pre_tool` | before a tool runs (permission already granted) | veto this call, with a reason fed back to the model |
| `post_tool` | after a tool ran | audit, add context (cannot change what happened) |
| `session_end` | session closes | wrap up, summarise |

```bash
# stdin
{"event":"pre_tool","tool":"file_write","params":{"path":"migrations/001.sql"}}

# stdout (may be empty); exit code 2 blocks
{"decision":"block","reason":"files under migrations/ are edited by humans only"}
```

**The default is fail-close**: a hook that crashes, times out, or floods stdout does **not** count as "check passed" — that is exactly the "I added a check and the check never ran" failure mode. Write `"on_error": "warn"` explicitly to be lax.

Configure with `hooks` in `~/.ai_code.json` or a project-level `.ace/hooks.json` (**appended**, not overriding); plugins can ship hooks too. `/hooks` shows what is installed and how each last ran.

## ✨ Custom slash commands (`.ace/commands/*.md`)

The filename becomes the command → `/review 40`. `$ARGUMENTS` and `$1` substitute arguments; a file without frontmatter still works.

Two deliberate trade-offs: **no YAML dependency** (a zero-dependency core is a hard constraint, and all we need is "description + argument hint"), and **built-ins win** — `/help` can never be shadowed by a custom command.

Custom commands expand into a prompt and go through the normal conversation path, so permissions, approval and audit still apply.

## ✨ Plugin directory (`.ace/plugins/<name>/`)

```
.ace/plugins/myplugin/
├── plugin.json          # optional
├── commands/*.md        # → /myplugin:review (auto-prefixed, no collisions)
└── hooks.json           # → appended
```

A broken plugin only affects itself; `/plugins` shows why.

**Plugins cannot ship tools in this version**: tools require Python modules, which would mean running plugin code in-process — a far bigger trust surface than "commands + hooks". For tool extensions, use MCP.

## 🛡️ The boundary (same as MCP)

Hooks — including those shipped by plugins — are **local commands you configured and are not inside ACE's sandbox**. The execution layer decides whether to run them and whether their word counts; it cannot control what they do internally. **Only install what you trust.**

Two concrete limits: a `pre_tool` block **does not count as a security violation** (it is a team rule, not someone probing the boundary), and hooks **do not receive file contents** (over-long parameter fields are truncated) — read the file yourself if you need it.

## 📋 Compatibility

- No breaking changes: with no `hooks` configured and no `.ace/` directory, behaviour is identical
- 17 new i18n keys, complete in Chinese, English and Japanese; the full protocol lives in the new [`docs/EXTENDING.md`](../docs/EXTENDING.md)
