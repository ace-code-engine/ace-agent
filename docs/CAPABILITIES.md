# 核心能力（Capabilities）

> 从 README 迁出。工具清单与权限档位以 `tools/registry.py` 的 `TOOL_SPECS` 为唯一真相源，本文只做概览。

## 执行安全

| 能力 | 一句话钩子 |
|---|---|
| 三级权限 + 按权限裁剪工具表 | `readonly` / `write` / `full`。工具清单随档位裁剪，单点声明在 `tools/registry.py`，模型只在"看得见用得了"的工具里决策。 |
| 三层沙箱 | `off`（策略层）/ `job`（Windows Job Object：进程树、内存上限、受限令牌）/ `docker`（一次性容器：`network none` + `cap-drop ALL`）。**Linux 上 Go 执行器还会自动叠加 Landlock 写隔离 + seccomp 网络默认拒绝**（工作区内可写、区外只读、不能出网）。拿不到边界就 503，绝不静默回退。 |
| 写入前快照 | 每次写操作自动物理快照，`/undo` 一键回滚。HMAC 签名防伪造，快照目录 Agent 自身不可写。 |
| 外发闸门 | 数据去往**模型指定的目的地**时，目的地不在白名单内就逐次问人；配置 `egress_allowlist` 即一次性授权。 |
| 安全事件分级 | 403 里"执行层主动防御"与"模型参数写错"分开计数：前者本会话累计到阈值就明确告警 —— 那通常意味着有东西在借被读取的文件或网页注入指令。 |
| 行为检测闸门 | 首次 `code_execute` 注入语义诱饵验证模型清醒 + AST 6 规则（无限递归 / 硬编码密钥 / SQL 注入等）。 |
| Go 执行器 | 危险工具委派独立 Go 进程（NDJSON），整树回收（Windows Job Object / Linux·macOS 进程组 SIGKILL）+ 第二道策略复检；Linux 上还叠加 **Landlock 写隔离 + seccomp 网络默认拒绝**。官方产物 `ace --install-executor` —— 5 平台（win / linux / macos × amd64 / arm64）。 |

## Agent 能力

| 能力 | 一句话钩子 |
|---|---|
| 持久目标（goal） | `goal_create` 后**自动逐轮续跑**直到完成 / 暂停 / 阻塞 / 预算耗尽。blocked 须给机器 code，重启后 `/goal resume` 才续。 |
| 子代理 | `subagent` spawn（全新上下文）/ fork（继承父会话），各自带工具循环，结果回传父代理整合。 |
| 免 key 联网搜索 | `search` 双引擎兜底（Bing RSS → DuckDuckGo）+ `search_read` 一步抓 top 正文。出站全走 SSRF 校验 + 白名单。 |

## 可选与实验性

- **可选** —— 自定义知识库（`kb_search` / `kb_add` / `kb_list`）、会话事件日志与重启恢复（`/audit`）、Plan Mode、审批疲劳缓解、浏览器自动化、文档解析全家桶（Word / Excel / PPT / PDF / OCR）、SimHash 记忆、`AGENTS.md` 项目指令、上下文压缩、网络退避、i18n（zh / en / ja）。
- **实验性** —— 聊天内置滚动引擎。引擎已实现，真机接线待做，见 `docs/history/UI-CHAT-SCROLL.md`。
