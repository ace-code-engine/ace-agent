# ACE v1.0.0 —— 公测（Public Beta）

> **发布日期**：2026-10-01 · **版本**：1.0.0 · **成熟度**：公测 · **许可**：MIT
> 完整条目见 [CHANGELOG.md](../../CHANGELOG.md)；文档索引见 [docs/README.md](../README.md)。

## 一、本版定位

ACE（AI Code Engine）是面向编码代理的**执行层**：每一次工具调用在执行之前都经过同一个裁决点
—— 权限闸门、路径与敏感目标边界、写前快照、可审计记录。提示词失效时（越狱、注入内容、
被篡改的工具输出），这道边界仍然成立，因为它并不写在提示词里。

版本号自本版起重新起算为 `1.0.0`。此前的 `3.3`–`3.47` 为内部能力路线图迭代版本，其收尾内容
（工作区四层、agent 预设、学习闭环、L4 上报、MCP 安全子层）均包含在本公测版中，历史条目保留在
更新日志里以便追溯。

## 二、三条交付形态

三种产物并列发布，按使用场景选择其一即可：

| 形态 | 产物 | 装了什么 | 适用场景 |
|---|---|---|---|
| **① 直接用 ACE 当 agent** | `ace-1.0.0-windows-amd64.msi`<br>`ace-1.0.0-windows-amd64.zip` | 完整终端 agent：四外壳、51 工具、写前快照、`/undo` | 需要一个能自行工作的编码代理 |
| **② 把 ACE 当你的 agent 的 MCP 服务** | `ace-mcp-server-1.0.0.zip` | 非侵入式 MCP 服务；host agent 获得唯一的裁决与审计点 | 已在用 Cline / Claude Desktop / Cursor 等 MCP host，只希望增加边界 |
| **③ MCP 服务 + 沙箱底座（一体包）** | `ace-sandbox-bundle-1.0.0.zip` | 形态 ② 加虚拟化底座的引导，使不可信代码运行在硬件隔离的 microVM 中 | 同时需要裁决边界与执行边界 |

已安装 ACE 的环境不需要形态 ② / ③，直接让 host 指向 `ace.exe --mcp`。附带产物：
`ace-executor-<平台>` 为各平台预编译执行器（Windows / Linux / macOS，amd64 与 arm64）。

## 三、主要能力

- **唯一裁决点**：工具由 `tools/registry.py` 声明一次，权限 / 审批 / 审计 / 快照同一条路径；
  MCP server 与 `SKILL.md` 技能走同一口。
- **可逆性**：任何写入之前建立物理快照（信任锚在工作区之外、链式 MAC），`/undo` 与 `/rollback <id>`
  是回滚的唯一入口。
- **MCP 安全子层**：`ace_security_scan`（路径级；`deep: true` 追加内容级，且只读文件名已命中凭据的
  文件）、`ace_sandbox_exec`（不可信代码进沙箱；沙箱不可达一律拒绝，不退回本机）。
- **沙箱底座**：接入 CubeSandbox（RustVMM + KVM microVM）。底座与裁决层**不要求同机**：一台 Linux
  底座可服务多台 agent 主机。
- **工程纪律**：验收断言随每次推送运行（本版 2735 条）；工作流、打包与发布链路均自验。

## 四、已知限制（如实）

- **沙箱底座需要 Linux + KVM**。Windows 与 macOS 不能承载；包内 `preflight` 会先给出判定。
  本版未在具备 KVM 的机器上完成真机冒烟 —— 底座不可达时 `ace_sandbox_exec` 的行为（拒绝）已有断言钉住，
  但"沙箱内部真的隔离"这一点尚待真机验证。
- **MCP 真 host 冒烟已完成读路径**（Cline 经 MCP 调 `file_read`，会话台账留下 `mcp:external agent`
  归属记录）；**写路径**（提权或授权令覆盖）尚未在真 host 上走完。
- **安全扫描为路径级**，内容级仅覆盖文件名已命中凭据的文件；扫描完成不等于结论安全（SEC-022）。
- 接口在 1.0 正式版之前仍可能调整。

## 五、验证方式

```bash
python ai_code.py --mock                            # 离线自验，不需要密钥与网络
python demo/record_demo.py --check                  # 演示图可复现性
python e2e/mcp_probe.py                             # MCP 服务端：真进程 + 真执行层
python packaging/mcp/verify-mcp.py                  # 形态 ②：包内自检
python packaging/allinone/sandbox/verify-sandbox.py # 形态 ③：底座可达性与真执行
```

完整回归：`python test_all.py`（本版 2735 条）。
