# ACE v3.47.0 —— ACE 打包成 MCP 安全子层：主 agent 的子安全层 + 共用 CubeSandbox 底座

> 面向用户。发布说明索引见 [docs/README.md](../README.md)；完整条目见 [CHANGELOG.md](../../CHANGELOG.md)。

## 一句话

把 ACE **打包成一个完整的 MCP 服务**：任何 MCP host（Claude Code / Cline / Codex / 自研）都能挂上
`ace --mcp`，把它当**子安全层**做安全测试 —— 主 agent 负责想，ACE 负责"这一下能不能动"并给出
**可判定**的安全事实，不可信代码进**两者共用的 CubeSandbox 底座**（KVM MicroVM + eBPF 出网闸门）。
`test_all` 2680 → **2733** 条断言，四闸全绿，`e2e/mcp_probe.py` **46/46**。

## 能摸到的新东西

| 面 | 你现在能做什么 |
|---|---|
| **MCP 安全子层（WP-11）** | 主 agent 调 `ace_security_scan`（路径级 + `deep` 内容级扫描，判据复用敏感名单、**宁可漏不可误报**）、`ace_sandbox_exec`（不可信代码进 CubeSandbox；**沙箱不可达 → 拒绝**，绝不退回本地）。报告第一行自带范围声明 —— **"扫过了"≠"安全了"**（SEC-022） |
| **工作区四层（批次 4 关闭）** | `/workspace` 列表 · `/workspace new <标题> [--worktree <路径>]` 真建 git worktree 并注册进 `allowedRoots`；文件工具**真的受** `allowedRoots` 管（`_confined` 一处接线全覆盖）；`/undo` 覆盖情况逐行如实显示 |
| **agent 预设入口** | `/preset [名字]` 运行中切换预设（此前只能写死在启动配置）；切完**立即生效**，`agent_preset` 事件四外壳全都有（底栏段 + 前端归约）；比全局更松的预设当场拒（S-1） |
| **学习闭环** | `/rules accept <序号>` —— 账本攒出的 deny 提议由你签字固化成规则（此前 `accept_proposal` 没有任何入口）；签完从待办摘掉 |
| **L4 阻塞式上报** | `/escalation [回答]` —— 五级阶梯最上一档"停下来问人"终于**真的有人可问**了；轮末提示 + 只看不答不解除 |

## 修掉的一个真洞（SEC-021）

WP-4 接线时带出来的：`allowedRoots` 的来源 `.ace/workspaces.json` 在**项目目录内 = 模型可写范围** ——
写一份 `worktree_path: C:/` 就给自己发了通行证（免确认越界读）。已按 `.guardian` 同款堵死，
只挡精确这一条路径。教训写进了审计表：**给闸门新增数据源时，必须同时问"这个数据源谁能改"**。

## 没做的（如实）

- **WP-9 Tier 2（CubeSandbox 落地）**：卡 + SEC-020 + 三条验收齐了，缺一台跑 KVM MicroVM 的机器；
  `ace_sandbox_exec` 在本机的实测常态就是 Tier 0 拒绝 —— "拒绝得对不对"已被钉住，**真跑通需要你**
  （部署 CubeSandbox → 配 `ACE_SANDBOX_API` → 主 agent 真调一次，见卡 §8 与 A5）。
- **WP-10 Rust 核心化**：R1 的依据已被复测推翻（1929 ms 实测 55~132 ms），R2 无基准支持，未开工。
- **WP-8 非 URL 出网通道**：刻意不做（脆弱 shell 解析，H-27 的教训）；域名级 allowlist 早已落地接线。
