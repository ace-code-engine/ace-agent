# 01 · 安全实验室

**目标**：亲手撞一遍执行层的三道闸门——权限裁决、逐次确认、写前快照——确认"安全不在提示词里"这句话是真的。

**前置**：仓库根目录，Python ≥ 3.10。**不需要 API Key**（`--mock` 用的是脚本化的离线假模型）。

```bash
cd <仓库根目录>
python ai_code.py --mock
```

进去以后照着做。每一步的输入都是**对模型说的话**或**斜杠命令**：

| # | 做什么 | 应该看到什么 | 看到它说明什么 |
|---|---|---|---|
| 1 | 说：`把 examples/01_security_lab/workspace/note.txt 的内容改成 hello` | `403`，附"当前只读，可用 request_permission 申请"之类的指令 | 起步权限是 `readonly`（`agent_runner` / `execution_layer` / `ai_code` 三个入口的默认值都是它）；模型在"看得见的工具"里决策，写工具根本没被放行 |
| 2 | 输入 `/permission write` | 提示权限已切到 write | 提权是**人的动作**，不是模型能自己做的；模型只能 `request_permission` 求你 |
| 3 | 重说第 1 步那句话 | 工具调用成功，文件内容真的变了 | 权限档一放开，同一条请求就走通了——拦截点确实是执行层 |
| 4 | 输入 `/snapshots` | 列出一个快照（seq / 时间 / 涉及文件） | 写操作前**自动**建快照，不需要谁记得去备份 |
| 5 | 输入 `/undo` | 回滚成功，`note.txt` 回到原文 | 回滚是物理恢复，不是"让模型再改一遍" |

### 再加一步：命令执行必须过人

| # | 做什么 | 应该看到什么 | 看到它说明什么 |
|---|---|---|---|
| 6 | 说：`用 terminal_exec 跑一下 echo hi` | 弹确认（本次 / 本会话），**即使已经在 write 档** | `terminal_exec` 在注册表里是 `confirm=True`：它的危险命令黑名单可被引号、长选项、变量展开绕开，所以唯一有效防线是"人看一眼"——它拒绝会话级放行，每次都问 |
| 7 | 说：`读一下 ~/.ssh/id_rsa` 或项目外的任意路径 | `403` 路径越界 | 读工具与 `terminal_view cat` 同一口径；绝对路径不因为"说得出口"就合法 |

### 为什么改不坏快照目录

`.guardian/`（快照与签名密钥所在）在工具层被当作**敏感目标**：即便权限拉到 `write`，`file_write` /
`file_delete` / `str_replace` / `terminal_view` 碰它一律 403。否则模型改一行
`.guardian/snapshots/<id>/meta.json` 就能让回滚验证失败——那就成了"能删自己监控的监控"。
这条有回归断言盯着（`test_all.py` 的敏感目标用例）。

### 想再往前一步

```bash
# 真实内核边界（不是进程内策略）：
ace --install-executor            # Windows：装官方预编译执行器（无需本机 Go）
python ai_code.py --sandbox job   # Windows Job Object：进程树/内存上限 + 受限令牌
python ai_code.py --sandbox docker # 一次性容器：network none + cap-drop ALL
```

拿不到边界时**返回 503，绝不静默回退到宿主执行**——这条语义在 job / docker 两档都一样。
边际与诚实说明见 [`docs/SECURITY-MODEL.md`](../../docs/SECURITY-MODEL.md)。
