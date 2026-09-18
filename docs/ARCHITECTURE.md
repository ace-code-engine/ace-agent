# 架构（Architecture）

> 本文档承接原 README「项目结构」权威清单与架构分层（docs/design/README-RESTRUCTURE.md，v3.7）；完整目录树**以本文档为准**（CONTRIBUTING/维护者索引指向这里）。
> README 只展示架构级短树，深读从这里进入。

## 1. 分层职责

| 层 | 组件 | 职责 |
|---|---|---|
| 用户层 | `ai_code.py` | 登录页、聊天 REPL、斜杠命令、提供商切换（纯终端，编辑器无关） |
| 交互循环 | `agent_runner.py` | 模型 ↔ 执行层多轮闭环；格式错误 / 守门 / 诱饵自动回喂修正，最多 20 轮 |
| 模型网关 | `gateway_v2/` | L1 意图 → L2 技能 → L4 守门（8 规则）→ L5 飞轮（SFT 数据） |
| 执行层 | `execution_layer.py` | 单轮 `_stage_*` 状态机（14 阶段，RoundCtx 本轮上下文）；协议解析、权限裁决、安全闸门、快照与守门串联 |
| 工具集 | `tools/` | registry 单点声明（name/schema/权限组/handler）+ 按域拆分的执行器 |
| 支撑模块 | `work.py` `guardian.py` `Archive.py` `Nuwa.py` | 诱饵/AST 行为检测、物理快照回滚（HMAC）、SimHash 记忆、POC 报告 |

## 2. Gateway 与执行层的关系（真话）

**Gateway 不是独立的安全流水线，不独自持有执行权。** 它是执行层在每轮内调用的策略/辅助层：

- `L1 意图识别 + L2 技能推荐`：仅在新输入时计算一次并缓存（`_stage_route`）；
- `L4 守门`：模型产出经过文本守门与成功结果守门（`_stage_final_reply` / `_stage_output_guard`，违规回滚本轮快照）；
- `L5 飞轮`：守门违规落盘为 SFT 数据（`flywheel_path`）。

README 架构图以虚线（旁路）连接 Gateway 与交互循环，即表达此意——每轮裁决的强制边界仍在 `execution_layer.py`。

## 3. 完整目录树（权威）

```
ace-agent/
├── ai_code.py                  # 命令行前端：登录页 / REPL / 斜杠补全 / 提供商注册表 / goal 续跑 / 会话恢复
├── agent_runner.py             # 交互循环：模型 ↔ 执行层多轮闭环，错误自动回喂，工具结果确定性裁剪
├── execution_layer.py          # 执行层主入口：单轮 _stage_* 状态机（RoundCtx）；协议解析、权限、安全闸门、Plan Mode、全链路日志
├── ace_execpolicy.py           # 命令三值判定（allow / prompt / forbidden），纯函数、可单测
├── ace_net.py                  # 出站请求闸门：全记录校验 + pin-to-IP + 逐跳复检（SSRF）
├── ace_isolation.py            # 外部内容定界与来源标注（SEC-011）
├── ace_http.py                 # 模型调用的重试与退避（Retry-After + full jitter，纯判定可单测）
├── ace_context.py              # 上下文压缩判定：保住任务锚点，中间段折成摘要
├── ace_executor.py             # Go 执行器客户端（NDJSON 协议，纯 stdlib）
├── ace_sessionlog.py           # 会话事件日志：append-only JSONL，seq 契约，深冻结，replay 重建
├── ace_theme.py                # 语义调色板（dark/light 自动检测）
├── ace_selector.py             # 搜索式选择器（/model /provider 输入即过滤）
├── ace_cards.py                # 工具结果卡片（状态+参数+折叠输出）
├── ace_doctor.py               # 环境自检（python ace_doctor.py）
├── ace_chatscroll.py           # 聊天内置滚动引擎(方案 C:视口只滚会话行)
├── executor/                   # Go 执行器：Job Object 沙箱（官方产物 ace --install-executor；或自编译）

├── tools/                      # 工具执行器包（清单与权限以 tools/registry.py 为准）
│   ├── __init__.py             #   包入口：组合各域 mixin 的 ToolExecutor（__all__ 导出）
│   ├── registry.py             #   工具唯一声明处（name / schema / 权限组 / handler）
│   ├── result.py               #   ExecutionResult 结果类型
│   ├── status.py               #   错误码/状态码唯一目录（Q-10 契约，散落字面量由守卫拒绝）
│   ├── base.py                 #   共享助手 + 敏感目标判定 + execute 分发
│   ├── file_tools.py           #   文件/终端/检索（grep/glob/str_replace）
│   ├── code_tools.py           #   代码执行（AST 白名单 + Go 执行器/docker 边界）
│   ├── web_tools.py            #   网络/搜索/search_read/Playwright 浏览器
│   ├── db_tools.py             #   SQLite 读写
│   ├── notify_tools.py         #   通知（console/file/toast）
│   ├── parse_tools.py          #   文档解析（Word/Excel/PPT/PDF/OCR）
│   ├── goal_tools.py           #   持久目标状态机（revision CAS / blocked 白名单 / 轮次驱动）
│   ├── subagent_tools.py       #   子代理（spawn/fork，独立工具执行循环）
│   ├── skill_tools.py          #   文件式技能库（SKILL.md 目录扫描）
│   ├── kb_tools.py             #   自定义知识库（kb_search/kb_add/kb_list）
│   └── docker_sandbox.py       #   容器执行层（--sandbox docker）
├── gateway_v2/                 # 网关包：intent(L1/L2) · guard(L4) · flywheel(L5)
├── work.py                     # 诱饵工厂 + AST 行为检测（ASTDetector）
├── guardian.py                 # 物理快照回滚：快照 / 完整性预检 / HMAC / 自动清理
├── Archive.py                  # SimHash 记忆引擎
├── Nuwa.py                     # POC 报告（HTML + JSON）
├── universal_document_parser.py# N 合一文档解析 + 懒加载 + 50MB 防线
├── i18n.py + locales/          # 轻量国际化（zh / en / ja JSON 字典）
├── prompts/                    # 系统提示词：v7 完整版 · v8 精简版 · tools 原生调用版
├── test_all.py                 # 全模块端到端测试（纯 stdlib，断言数随平台浮动）
├── benchmarks/                 # 实测基准：bench_core.py 一键复现，results/ 存报告（正确率/延迟/吞吐）
├── e2e/                        # 真实模型端到端冒烟（real_model_smoke.py，OpenAI 兼容端点）
├── demo/                       # README 演示动画 + 录制脚本（跑真实 --mock 会话）
├── assets/logo.svg             # 标识（原创几何构图，无第三方素材）

├── docs/                       # 文档（README 是入口，深读按角色分流）
│   ├── ARCHITECTURE.md         #   本文档：分层职责 + 权威目录树 + ADR 索引
│   ├── SECURITY-MODEL.md       #   安全模型：权限/隔离/路径/网络/沙箱 + 生产部署必读
│   ├── CONFIGURATION.md        #   配置全项：config 键 + 出站白名单/检索/编码/DB 边界
│   ├── COMMANDS.md             #   命令参考：斜杠/@ 全表 + 启动参数
│   ├── TESTING.md              #   测试：全量/CI 矩阵/基准/e2e/ruff
│   ├── DEVELOPMENT.md          #   开发者标准化流程（改代码到推送八步 + 新增工具八步清单）
│   ├── INTERFACES.md           #   接口与类型契约（文本协议/状态码/注册表/权限模型/网络）
│   ├── SECURITY-AUDIT.md       #   安全审计（OWASP + STRIDE；部分条目与现码漂移，以代码为准，见 BACKLOG SEC-*）
│   ├── ADR.md                  #   架构决策记录（内联序列 001-006）
│   ├── ADR-002-executor-boundary.md  #   执行器进程边界 / NDJSON 协议 / Windows 沙箱选型
│   ├── BACKLOG.md              #   待办事项（P0 安全 / P1 快速项 / P2 结构 / REL）
│   ├── BACKLOG-P2.md           #   P2 重构立项卡(R-01~R-05 范围/验收/顺序,供新会话照做)
│   ├── PACKAGING.md            #   打包与分发评估（Q-13 结论:源运行,布局重构后再 wheel）
│   ├── design/                 #   已闭环立项卡（历史设计决策）
│   │   ├── EXECUTOR-RELEASE.md     #   执行器发布通道（预编译二进制 + ace --install-executor）
│   │   ├── README-RESTRUCTURE.md   #   README 瘦身两轮立项（本结构由此演进）
│   │   └── ARCH-TREE-CHECK.md      #   权威树一致性校验（Q-06：R1-R4 规则 / 实测缺口 / S1-S4）
│   └── history/                #   会话纪要 / 调研 / 规范历史
│       ├── SESSION-2026-09-06.md   #   评审会话纪要（风险清单→决策→提交→OPEN）
│       ├── UI-CHAT-SCROLL.md       #   聊天内置滚动立项卡(引擎已实现,接线待真机)
│       ├── codex_research.md       #   Codex 源码调研（45+ 可借鉴设计）
│       ├── dsh_research.md         #   DeepSeek Harness 源码调研（62 项可借鉴设计）
│       └── prompt-engineering/     #   提示词工程规范 v1→v7 + 上下文包（历史归档）

├── README.md                   # 项目名片与上手入口（架构级短树；权威树见本文档）
├── CONTRIBUTING.md             # 贡献指南（环境 / 测试 / 风格 / PR 流程）
├── LICENSE                     # MIT
├── CHANGELOG.md                # 逐版本更新日志（Keep a Changelog 风格）
├── SECURITY.md                 # 安全策略：漏洞报告流程 / 承诺 / 已知边界
├── version.py                  # 版本单源 __version__（徽章 / 横幅 / doctor / CHANGELOG 对齐）
├── requirements.txt            # 可选增强依赖清单（核心零依赖，按需安装）
├── ace.cmd                     # Windows 启动器（PATH 探测 python/py，防商店占位）
├── Dockerfile                  # 整体镜像入口（三档细目在 docker/）
├── docker-compose.yml          # 整体镜像一键起停编排
├── .gitignore                  # 忽略规则：生成物 / 缓存 / 密钥
├── .dockerignore               # 构建上下文忽略
├── docker/                     # lite / standard / full 三档整体镜像 + sandbox 执行镜像 + 模型下载脚本
└── .github/                    # 仓库协作配置
    ├── workflows/              #   ci.yml（测试/ruff/Go/bench/e2e）+ release-executor.yml（预编译产物发布）
    ├── ISSUE_TEMPLATE/         #   bug / feature 议题模板
    └── pull_request_template.md#   PR 模板
```

> 维护纪律：树里出现的每个路径必须真实存在，仓库根级与"已展开目录"的直接子项必须登记（BACKLOG Q-06）。该约束由 `test_all.py` 的 `[38] 文档/仓库结构一致性` 自动校验——删文件、加文件、改树名都会让测试变红。

## 4. 深入文档索引

| 想了解 | 去这里 |
|---|---|
| 为什么这么设计（SimHash / 双层协议 / 零依赖） | `ADR.md`（内联序列 001-006） |
| 执行器进程边界 / NDJSON / Windows 沙箱选型 | `ADR-002-executor-boundary.md` |
| 协议/状态码/注册表/权限模型/网络契约 | `INTERFACES.md` |
| 安全机制与边界 | `SECURITY-MODEL.md` + `SECURITY-AUDIT.md`（审计） |
| 配置项与机制说明 | `CONFIGURATION.md` |
| 提示词规范演进 | `history/prompt-engineering/` |
| 测试与 CI | `TESTING.md` |
| 开发流程与规范 | `DEVELOPMENT.md` + `CONTRIBUTING.md` |
