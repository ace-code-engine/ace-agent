# ACE v3.31.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3310-2026-09-19)。无破坏性变更。

## 一句话

上一版加了持久规则（`/rules`），这一版把它**接到发生的那一刻**：你刚说"允许"，就顺手问一句要不要记下来。

## ✨ 授权时顺手记成规则

选「2) 本会话允许」之后多问一句（**回车 = 不记**）：

```
  2) 本会话允许
  要不要记成持久规则（下次开新会话也生效）？建议模式: docs/
  回车=不记 · y=按建议记 · y <模式> <作用域> · ! <模式> = 记成拒绝:
```

- `y` → 按建议记下（默认作用域 `local`，只在本机生效、不进 git）
- `y ace/ project` → 自定义模式与作用域（`project` 随仓库走，团队共享）
- `! rm:*` → 顺手把某个前缀**锁死**（记成拒绝）

落地后立刻生效（重载并同步到执行裁决），并回显规则说明与写入的文件路径。

## ✨ 建议模式默认给最小范围

| 这次调用 | 建议的模式 |
|---|---|
| `pytest -q --tb=short` | `pytest:*` |
| 写 `ace/ui/ace_prompt.py` | `ace/ui/` |
| 认不出的工具 | 留空（你自己定） |

规则是长期的，**默认给太宽等于把整个工具放开** —— 所以宁愿建议得保守一点，让你自己改宽。

## ⚙️ 三条"不打扰"的边界

- 选了「仅本次」**不会**来劝你存规则（你刚说了"就这一次"）
- **外发工具不提供**"顺手允许"（要授权目的地得用配置 `egress_allowlist`）
- 非交互终端不问；写法认不出或作用域写错会**如实报错**，不会静默不记

## 🐛 自查修掉的一个真错

`parse_persist_answer` 一开始借用了通用的规则解析器，于是"缺工具名"把**合法回答**（`y docs/ project`）判死了 —— 工具名本来就该由调用方补上。探针里当场看到它返回 `None`，改成直接构造规则。

## 📋 兼容性

- 无破坏性变更；新增 3 个 i18n 键（中英日各 514 键对齐）；新增测试段 `[57]`（15 项断言）
- 仍未做：折叠组的进行中实时说明、通知区、全屏历史视图第二层、会话选择器的进阶筛选键

---

# ACE v3.31.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3310-2026-09-19). No breaking changes.

## In one line

The previous release added persistent rules (`/rules`); this one hooks them into **the moment they are decided**: right after you say "allow", you get one question about saving it.

## ✨ Save it as a rule while you are already saying yes

After choosing "2) allow this session" (**Enter = do not save**):

```
  Save this as a persistent rule (applies to future sessions too)? Suggested pattern: docs/
  Enter = do not save · y = save the suggestion · y <pattern> <scope> · ! <pattern> = save as deny:
```

`y` saves the suggestion (scope `local` by default: this machine only, not in git); `y ace/ project` customises pattern and scope; `! rm:*` locks a prefix down as a deny. The rule takes effect immediately (reloaded and pushed to the enforcement path) and the output names both the rule and the file it was written to.

## ✨ The suggested pattern is deliberately narrow

`pytest -q --tb=short` → `pytest:*`; writing `ace/ui/ace_prompt.py` → `ace/ui/`; an unrecognised tool → empty (yours to fill in). A rule is long-lived, so suggesting it too wide would open the whole tool by default.

## ⚙️ Three "do not nag" boundaries

- choosing "allow once" does **not** trigger the offer (you just said "this once")
- **outbound tools are never offered** (authorise the destination via `egress_allowlist`)
- non-interactive terminals are not asked; unrecognised input or a bad scope is reported honestly, never silently dropped

## 🐛 One real bug found in self-review

`parse_persist_answer` reused the generic rule parser, so "missing tool" killed **valid answers** (`y docs/ project`) — the tool name is supposed to be supplied by the caller. The probe showed it returning `None`; it now builds the rule directly.

## 📋 Compatibility

- No breaking changes; 3 new i18n keys (514 per locale, aligned); new test section `[57]` (15 assertions)
- Still open: live progress inside collapsed groups, the notification area, the second layer of the history view, and advanced keys in the session picker
