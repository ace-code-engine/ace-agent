# WP-6 · agent 预设 / 自定义模式（G-11）—— 立项卡

> 状态：**卡已立**（`ROADMAP` §4 WP-6 的要求："**必须单独立卡 + 单独评审**"）。
> 上级：`docs/ROADMAP.md` §4 WP-6 · §7.1 **C4**（DL-03 已落地，依赖满足）· §7.1 **C1**（`WP-0` 已完成）。
> **风险：高** —— 这是**直接改权限层**的一项（全局最高的安全风险在 `WP-9`，本项次之）。

## 一、要做什么

把 `CONFIRM_TOOLS` 从**全局常量**变成 **per-agent 权限规则**：`agents/*.md` 的 frontmatter（照 kilocode）

```markdown
---
name: reviewer
description: 只读审查
permission: {read: allow, edit: ask, webfetch: ask, bash: deny}
---
你是审查者……
```

- 预设**只改"要不要问人"这一维**，**不改**用户/项目的**持久规则**（`core/ace_rules.py`）、
  不改 `sensitive.py` 的越界判定、不改沙箱档 —— 那些是**更上位**的约束。
- 切换预设**必须广播到所有外壳**（REPL / TUI / Ink），与 `WP-0` 的口径同源（C1 已满足）。

## 二、**S-1 硬约束（不得削弱）**

预设**只能比全局更严或相等，绝不允许更松**：

| 全局 | 预设可写 | 预设**不可**写 |
|---|---|---|
| `bash: ask` | `deny` / `ask` | **`allow`** |
| `read: allow` | `allow` / `ask` / `deny` | —（read 本就最松，往下只能更严） |
| 任一 `deny` | `deny` | **`ask` / `allow`**（不许把 deny 放宽） |

- **断言**："预设不得放宽到比全局更松" —— 每一条 frontmatter 的权限值都要过 `assert_no_relaxation` 同族的判定
  （与 DL-04 的 `RELAXING_ACTIONS` / `RelaxationForbidden` **同一条纪律 + 同一个判定处**，不新开第二套）。
- **放宽只能是人的动作**：预设文件本身**不是**放宽入口；要放宽得改全局配置或持久规则（都是人写的）。

## 三、落地要点

1. `agents/*.md` 的扫描器（frontmatter：`name` / `description` / `permission`）；
   **无效字段只 warning 不阻塞启动**（与 WP-7 skill 同一姿态）。
2. `permission` 的**四维**（`read` / `edit` / `webfetch` / `bash`）→ 映射到既有 `CONFIRM_TOOLS` / 权限档，
   **不新增第二套权限模型**。
3. 预设切换 → 事件广播到四壳（复用 WP-0 的既有通道）。
4. **不静默**：预设里认不出的字段/值 → 如实 warning（HL-03②），不静默忽略。

## 四、验收

- **S-1 断言**：任何"预设比全局更松"的构造 → **红**（不是 warning）。
- **无效字段只 warning**：坏 frontmatter 不阻塞启动。
- **四壳广播**：切换预设后四壳口径一致（parity 断言，与 WP-0 同源）。
- `CONFIRM_TOOLS` 的**全局语义不变**（没有预设时行为与本卡之前逐字一致）。

## 五、边界（不做什么）

- 不动 `core/ace_rules.py` 的持久规则、不动 `sensitive.py`、不动沙箱档。
- 不做"预设市场"/远程拉取（只读本地 `agents/*.md`）。
- 不改 `WP-9` 的沙箱后端语义（那是另一项，且优先级更高）。
