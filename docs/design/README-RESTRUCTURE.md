# README 瘦身（README-RESTRUCTURE）立项卡

> **目标**：把 README 从"名片 + 用户手册 + 技术白皮书 + 开发日志"四合一（520 行）瘦身为**名片 + 精简上手 + 文档枢纽**（约 200 行），长文按角色搬到 docs/，README 只留"一句话 + 链接"。
> **性质**：方案卡。经审阅确认后**单提交执行**（可整体 revert 回滚）；改动纯文档，不动代码与测试。

---

## 1. 背景与现状测量

README 当前 520 行，四类文档混编（诊断来自评审意见，数字为实测）：

| 角色 | 章节 | 行区间 | 行数 | 处置 |
|---|---|---|---|---|
| 名片 | 标题/徽章/动图/一句定位 | 1-38 | ~38 | 保留 |
| 上手 | 目录 / 快速开始 | 39-110 | ~72 | 精简重排 |
| 名片+取舍 | 设计取向 | 111-122 | 12 | **保留**（短、承载设计哲学） |
| 技术白皮书 | 核心能力 / 架构 / 命令参考 / 安全模型 / 配置 | 123-394 | ~272 | 核心能力/架构压缩；命令参考/安全模型/配置**搬 docs/** |
| 开发日志 | 项目结构 / 开发与测试 / 版本历史 / 设计参考 | 395-520 | ~126 | 项目结构折叠保留；版本历史只留最新两条 |

## 2. 目标 / 非目标

目标：
1. 路人在 ~30 秒内看懂"这是什么、怎么试、为什么值得用"；深入者在 README 找到正确文档入口。
2. 内容不丢：搬走的每个字节都进 docs/，README 用链接指回。
3. 不破坏既有引用面（见 §5 链接修复清单）。

非目标：
- ❌ 合并/改名既有 SECURITY.md（根级，漏洞报告策略）与 docs/SECURITY-AUDIT.md（历史审计）——三者角色不同，README 安全模型独立成 **docs/SECURITY-MODEL.md**。
- ❌ 改动命令、行为、代码、测试；不造新的"完整能力清单"文档（核心能力细节就近并入命令参考/相关 docs，避免第四份列表）。
- ❌ 引入 CI 校验 README 结构（BACKLOG Q-06 另行立项）。

## 3. 目标结构（确认后按此重写 README）

```
徽章区 + 一句定位 + demo 动图（保留）
## 快速开始            ← 前置 + 3 命令(clone/test_all/--mock) + 接真实模型 2 行 + ace.cmd
                        （"其他启动方式"整体折叠进 <details>，条目压缩保留）
## 设计取向            ← 保留 3 条（链接改指 SECURITY-MODEL）
## 核心能力            ← 8 个钩子行（下表）
## 架构概览            ← 简化 Mermaid(用户→网关→执行层→工具) + 每层一句话小表
                        （支撑模块 work/guardian/Archive/Nuwa 移出图，文字一行带过）
## 常用命令            ← ~10 条斜杠/@ + /provider 示例 → 完整命令见 docs/COMMANDS.md
## 安全设计            ← 一句话(安全在执行层) → docs/SECURITY-MODEL.md
## 配置入口            ← 最小 ~/.ai_code.json 示例 → docs/CONFIGURATION.md
## 最近更新            ← v3.7 / v3.6 两条 → CHANGELOG.md
## 开发与测试          ← 精简 5 行命令 + CONTRIBUTING 链接
<details> 项目结构     ← 原文折叠（CONTRIBUTING 以它为权威树，不能删）
## 许可
## 设计参考
```

**核心能力 8 钩子**（一行一个差异卖点；原 20+ 行的其余能力就近进命令参考/相关 docs）：

| 能力 | 一句话钩子 |
|---|---|
| 三级权限 + 工具裁剪 | readonly/write/full，模型只在"看得见用得了"的工具里决策 |
| 三层沙箱 | off(策略层) / job(Windows Job Object) / docker(一次性容器)，job/docker 不做静默回退 |
| 写入前快照 | 每次写操作自动快照，`/undo` 一键回滚，快照目录 Agent 不可写 |
| 持久目标 | `goal_create` 自动逐轮续跑至完成/暂停/阻塞/预算耗尽 |
| 子代理 | spawn/fork 独立上下文会话，结果回传父代理整合 |
| 免 key 联网搜索 | Bing RSS → DuckDuckGo 兜底 + `search_read` 一步抓正文 |
| 行为检测闸门 | code_execute 首次注入语义诱饵 + AST 6 规则 |
| 官方执行器 | Go 执行器随 Release 发预编译二进制，`ace --install-executor` 无需装 Go |

## 4. 文件映射（内容去向）

| 新建 docs/ 文件 | 承接内容（现 README 行区间） |
|---|---|
| `docs/SECURITY-MODEL.md` | 安全模型全文 260-340：权限与授权 / 执行隔离 / 路径边界 / 回滚与网络 / 联网搜索双通道 / 容器隔离 / Job Object / 生产部署必读 |
| `docs/CONFIGURATION.md` | 配置全文 341-394：config 字典 + 配置优先级 + 出站白名单 / 检索边界 / str_replace 编码 / db_query 只读 四个小节 |
| `docs/COMMANDS.md` | 命令参考全文 220-259：首页/斜杠表/@ 快捷/技能/@ 文件链接 全部内容 |

README 删除以上三块后，各留一句 + 指回链接（§3）。

## 5. 引用面修复清单（搬家必须同步）

| 位置 | 现引用 | 改为 |
|---|---|---|
| `docs/history/prompt-engineering/README.md:100` | "仓库根 README.md 安全模型一节" | `docs/SECURITY-MODEL.md` |
| README「设计取向」第 3 条（L117 一带） | 锚点 `#安全模型` | `docs/SECURITY-MODEL.md` |
| `CONTRIBUTING.md:51` | README「项目结构」为权威树 | **无需改**（项目结构折叠保留在 README） |
| `docs/PACKAGING.md` / `DEVELOPMENT.md` 提及 README | 泛化引用 | 无需改 |
| docs/EXECUTOR-RELEASE.md 行号引用 | 历史记录 | 不改（记录的是当时事实） |

## 6. 执行步骤（单提交）

1. 建 `docs/SECURITY-MODEL.md`、`docs/CONFIGURATION.md`、`docs/COMMANDS.md`（原样搬迁 + 头部一句"本文档由 README 拆分而来"）。
2. 重写 README 为 §3 结构（保留徽章/动图/设计取向/项目结构原文；压缩快速开始/核心能力/架构；删除安全模型/配置/命令参考正文并换链接）。
3. 修 §5 两处外部链接。
4. 自查 + 提交。

## 7. 验收清单

> 状态记录：✅ 已验证（2026-09-06，提交 85b978f）。

- [x] 文件 520 → 299 行（其中 ~80 行为折叠的完整目录树，视觉上隐藏；不含树约 219 行可见正文）；目录与 12 个标题锚点一一自洽，Python 复核无悬空锚点。
- [x] 三块搬走的内容整段搬入 `docs/SECURITY-MODEL.md` / `docs/CONFIGURATION.md` / `docs/COMMANDS.md`，仅头部加来源说明；提交 diff 对读无漏字。
- [x] 新文档互相不重名；根级 SECURITY.md 与 SECURITY-AUDIT.md 未动（三者角色分离）。
- [x] 引用面修复完成：`docs/history/prompt-engineering/README.md:100` 改指 `../SECURITY-MODEL.md`（当时位于 `docs/prompt-engineering/`）；本地链接脚本扫描 5 个文件 0 死链；grep 无残留旧锚点引用。
- [x] 徽章/版本号三处一致（v3.7.0）；未改任何代码，test_all 无需重跑。
- [x] 单提交快照 `85b978f`（可整体 revert）。

## 8. 风险 / 回滚

| 风险 | 缓解 |
|---|---|
| 长文搬家漏字 | 按行区间整段搬迁 + 提交前 diff 比对原文 |
| 外部死链 | §5 修复清单逐一执行 + grep 复查 |
| README 是 CHANGELOG/ADRs 的"总览"引用目标 | 本项目卡只动 README 与新建 docs；被引用的角色（总览/项目结构）仍在 README |

## 9. 不在本卡范围

- 根级 SECURITY.md / SECURITY-AUDIT.md 内容整合（三份安全文档角色已清晰，各自保留）。
- 命令参考内容的增删改（只搬不编）。
- CI 结构校验、README 数字动态化（BACKLOG Q-04/Q-06）。
