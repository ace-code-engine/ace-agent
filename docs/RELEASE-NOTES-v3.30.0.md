# ACE v3.30.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3300-2026-09-19)。无破坏性变更。

## 一句话

授权这件事从"本次会话"变成**写文件、跨会话生效**：`/rules` 能按命令前缀或路径记下"别再问我"，也能反过来**锁死**某个目录。

## ✨ `/rules`：持久授权规则

```
❯ /rules add file_write docs/ project        ← 允许免问（路径在 docs/ 下）
❯ /rules add terminal_exec '!rm:*' local     ← 前缀 ! = 直接拒绝
❯ /rules                                     ← 列出：序号 / 动作 / 说明 / 作用域 / 来源文件
  [1] allow  file_write: 允许免问（路径在 'docs/' 下）  project
       C:\项目\.ace\permissions.json
  [2] deny   terminal_exec: 直接拒绝（命令以 'rm' 开头）  local
       C:\项目\.ace\permissions.local.json
❯ /rules remove 2
```

三档作用域写在不同文件：

| 作用域 | 文件 | 用途 |
|---|---|---|
| `local` | `.ace/permissions.local.json` | 只有你本机生效（**不进 git**），优先级最高 |
| `project` | `.ace/permissions.json` | 随仓库走，团队共享 |
| `user` | `~/.ace/permissions.json` | 家目录全局，对所有项目生效 |

模式的写法按工具类别：**命令类**写前缀（`pytest:*` 命中 `pytest -q`；不写 `:*` 就是完全相同）、**文件类**写路径前缀、**留空**表示该工具任意用法。

## 🔒 三条安全纪律（都有测试盯着）

1. **deny 永远赢**：同一目标既有 allow 又有 deny 时按 deny 处理 —— 放宽要你明确决定，收紧不需要
2. **外发工具的 allow 一律拒绝**：`api_post` 这类"把数据发出去"的工具只能 deny，要免问请用配置 `egress_allowlist` 指定**目的地**（按工具名放行等于把出口整个打开）
3. **规则不提权**：readonly 下写/执行工具照样要授权 —— 规则的意思是"这个前缀别再问我"，不是"给我提权"；要放开请显式 `/permission write`

另外：空前缀（任意用法）的 allow 不会顺带跳过"动项目外文件"那道闸门。

## ✨ 命中规则时的表现

- 命中 **deny** → 直接拒绝，并把规则出处一起说明（用户和模型都能看到是哪条规则、在哪个文件）
- 命中 **allow** → 视为这次调用已经被你确认过，不再逐次问

## 🐛 顺带修掉的

规则一开始只挂在 `ExecutionLayer` 上，而裁决发生在**执行器**的第 ⑦ 段管线 —— 于是"规则读到了、匹配也算得对，但没人用它"。现在两处都挂。（自查时先用裸 `executor.execute()` 验证，得到一个假的"成功"，才发现找错了入口。）

还修了一次**键名冲突**：新命令的 `rules_title` 等键与 `/permission rules` 对话框重名，把后者的文案顶掉了；现在新键统一 `prules_*` 前缀。

## 📋 兼容性

- 无破坏性变更；新增 15 个 i18n 键（中英日各 511 键对齐）；新增测试段 `[56]`（28 项断言）
- 仍未做：折叠组的进行中实时说明、通知区、全屏历史视图第二层、授权对话框里"顺手存成规则"的入口

---

# ACE v3.30.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3300-2026-09-19). No breaking changes.

## In one line

Permissions move from "this session only" to **rules written to files**: `/rules` records "stop asking me" for a command prefix or a path, and can also **lock down** a directory.

## ✨ `/rules`: persistent permission rules

```
❯ /rules add file_write docs/ project        ← allow without asking (paths under docs/)
❯ /rules add terminal_exec '!rm:*' local     ← a leading ! means deny
❯ /rules                                     ← list: index / action / description / scope / file
❯ /rules remove 2
```

Three scopes, three files: `local` (`.ace/permissions.local.json`, **not in git**, highest priority), `project` (`.ace/permissions.json`, shared with the repo), `user` (`~/.ace/permissions.json`, all projects).

Pattern semantics follow the tool kind: **commands** are prefixes (`pytest:*` matches `pytest -q`; without `:*` it must match exactly), **files** are path prefixes, and an **empty** pattern means any use of that tool.

## 🔒 Three safety rules (each with assertions)

1. **deny always wins** — when both match, the deny applies: loosening requires an explicit decision, tightening does not
2. **outbound tools can only be denied** — for `api_post`-style tools, authorise the *destination* via `egress_allowlist`; allowing by tool name would open the whole exit
3. **rules do not escalate** — under `readonly`, write/exec tools still ask; a rule means "stop asking for this prefix", not "raise my level"

Also: an empty-pattern allow does not skip the "file outside the project" gate.

## 🐛 Also fixed

Rules were only attached to `ExecutionLayer`, while the decision happens in the **executor's** stage ⑦ — so "the rule was loaded and matched correctly, but nobody used it". Both places now carry them. (The first verification used a bare `executor.execute()` and produced a false "success", which is how the wrong entry point was found.)

A key-name collision was fixed too: the new command's `rules_title`-style keys clashed with the `/permission rules` dialog and overwrote its text; new keys are now prefixed `prules_`.

## 📋 Compatibility

- No breaking changes; 15 new i18n keys (511 per locale, aligned); new test section `[56]` (28 assertions)
- Still open: live progress inside collapsed groups, the notification area, the second layer of the history view, and a "save this as a rule" shortcut inside the permission dialog
