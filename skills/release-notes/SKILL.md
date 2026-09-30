---
name: release-notes
description: 从 git 历史写一份**给人读**的发布说明（分类、影响面、升级注意），不堆 commit 原文。要发版、写 CHANGELOG、给用户解释这次改了什么时使用。
version: 1.0.0
license: MIT
allowed-tools: [terminal_exec, file_read, file_write, git_log, git_diff]
when_to_use: 用户说"写发布说明 / 更新 CHANGELOG / 这次版本改了什么"时
metadata:
  author: ace
  tags: [release, changelog, docs]
---

# 发布说明（release-notes）

发布说明的读者是**用户**，不是提交者。所以这件事的核心不是"把 commit 抄下来"，而是
**分类 + 翻译 + 标出影响面**：用户要能回答"我要不要升级、升级后我要不要改东西"。

## 步骤

1. **定范围**：先问清（或从上下文确定）版本区间 —— `git log <上一个 tag>..HEAD`。
   没有 tag 时用 `git log --oneline -n 50` 并让用户确认起点。
2. **取原始材料**：`git log`（带 `--no-merges`）+ `git diff --stat`。
   分类判据见 `references/style.md`（**先读它**，别自己发明分类）。
3. **分类**：按 `新功能 / 改进 / 修复 / 破坏性变更 / 内部` 归位。归不进去的放"内部"，
   宁可少写一条，也不要把内部重构写成"新功能"。
4. **写**：按 `assets/release-notes-template.md`。每条一行、以**用户视角**说清影响；
   破坏性变更必须带"升级要做什么"。
5. **自查**（写完后逐条过）：
   - 每条都能在 diff 里找到出处吗？
   - 有没有把"计划做的"写成"已经做的"？
   - 破坏性变更是否漏了迁移步骤？

## 硬规则

- **不发明事实**：commit 里没写、diff 里看不到的，不写进发布说明（包括"性能提升 30%"这种）。
- **不美化**：修复了 bug 就说修了哪个症状，不写"体验全面升级"。
- **破坏性变更单独一节且置顶**：漏掉一条的代价是用户升级后崩在生产上。
- 产物写进 `CHANGELOG.md`（已存在则**追加到顶部**，不要重排历史段落）。
