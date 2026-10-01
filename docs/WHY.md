# 为什么是 ACE（Why ACE）—— 名称说明 · 对比 · 设计取向

> 从 README 迁出（首页只留一句话钩子，全文在这里）。原 README 的「名称说明 / Why ACE / 设计取向」。

## 名称说明 —— 此 "ACE" 非彼 "ACE"

有多个互不相关的项目、框架与认证都叫 **ACE**。本仓库是 **ACE · AI Code Engine**
（`ace-code-engine/ace-agent`）：一个面向编码代理的**执行层** —— 在每次工具调用执行之前裁决
它能不能执行，并记录发生过什么。

本仓库**不是**以下任何一个，且与其无任何关联：

- **ACE 编辑器**（Ajax.org Cloud9 Editor，以 `ace-builds` 发行）—— 一个浏览器端源代码编辑器；
- **ACE 框架**（Adaptive Communication Environment）—— C++ 网络编程工具包，发行包名为 `libace`；
- **ACE-Step** —— 一个开源的音乐生成模型；
- **ACE: Agentic Context Engineering** —— 一种演化模型上下文的研究方法；
- **Adobe Certified Expert** 与 **American Council on Exercise** 两项认证。

若你是为找代码编辑器、音乐模型、C++ 框架或上下文工程方法而来，那是另一个项目。
本项目可辨识的事实：入口文件是 `ai_code.py`，安装后的命令是 `ace`，裁决逻辑在
`execution_layer.py`，安全核心零第三方依赖。

## 安全不该住在提示词里

大多数 Agent 把安全交给提示词："请不要删除文件"。ACE 不这么做。

模型的**每一次工具调用**都要穿过一个独立的执行层，由它做权限裁决、危险行为检测、写入前物理快照。提示词失效时 —— 被越狱、被注入的网页、被篡改的工具输出 —— 那一层仍然在。

> 如果你的需求只是**聊天式 AI 编程**（对话里生成代码、不改文件、不执行命令），ACE 未必必要。如果你的 Agent 要**真实地改文件、执行代码、访问网络**，并且你不希望这件事依赖模型的自觉 —— 那 ACE 才是目标场景。

## ACE 与「提示词护栏」型 Agent 的差别

| | 典型的提示词护栏 Agent | ACE |
|---|---|---|
| 「我有没有权限」在哪裁决 | 提示词里 | 执行层里，**每次调用**都过（`execution_layer.py`） |
| 提示词被注入 / 被越狱之后 | 看模型怎么决定 | 权限闸门、路径边界、敏感目标拦截照样生效 |
| 执行一条 shell 命令 | 模型直接跑 | `terminal_exec` **每次都问人** —— 它的黑名单可被绕过，所以「人」才是那道边界 |
| 撤销一次坏改动 | 指望 git | 每次写入前都有物理快照，`/undo` 一键回滚 |
| 数据离开这台机器 | 模型调 API 就走 | 外发闸门：目的地未知 ⇒ 确认；`egress_allowlist` ⇒ 一次性授权 |
| 离线、没有 API Key | 通常需要密钥 | `python ai_code.py --mock` 离线跑完整闭环 |
| 隔离 | 提示词级 | 三档：`off`（进程内策略）/ `job`（Windows Job Object）/ `docker`（一次性容器）—— 拿不到边界就返回 **503，绝不静默回退** |

## 设计取向

- **安全属于执行层，不属于提示词。** 权限裁决、危险命令拦截、写入前快照都在 `execution_layer.py` 里，与模型无关。换模型、模型被越狱、提示词被覆盖，这层都还在。
- **默认只读。** 起步权限是 `readonly`，写工具会被 403 拦下。提权是**人的动作**（`/permission write`），不是模型能自己发的。
- **边界要说清能挡什么、挡不住什么。** 全仓没有一句"完全安全"的宣称 —— 见 [安全边界 FAQ](security/SECURITY-FAQ.md)。

## 设计参考

架构决策与以下工作对齐 —— **让模型只负责"理解、选择、输出"，把权限、安全、回滚、记忆全部下沉到执行层**：

- [Agent Harness 工程最佳实践](https://github.com/Delphoa/study-awesome-harness-engineering) —— 工具 / 权限 / 记忆 / 沙箱 / 可观测性
- [DeepSeek Harness 设计解析](https://developer.aliyun.com/article/1756780) —— 对应内部调研 `docs/history/dsh_research.md`
- [20 章中文 AI Agent 架构实战](https://github.com/ryzqi/learn-agent)
