# 03 · 多轮真实任务

**目标**：把"聊天"变成"能自己往下推的任务"——持久目标自动续跑、子代理拆活、结论沉淀进知识库。

**前置**：需要真实模型（这一步必须烧 key）。

```bash
python ai_code.py                  # 首页 → 2 配置向导（选提供商 → 输 API Key → 选模型）→ 1 进聊天
# 已有 key 的话也可以直接切：
#   /provider            → 列出 9 家厂商 · 10 入口
#   /provider deepseek sk-xxxx
```

想先把配置写成文件（键名以 [`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md) 为准）：

```bash
cp examples/03_multi_turn_agent/config.example.json ~/.ai_code.json   # 然后改成你自己的值
python ai_code.py --save-config        # 也可以把当前命令行参数直接落盘
```

> `config.example.json` 里的 `egress_allowlist` 是**出站目的地白名单**：不配 = 闸门关闭（只有 SSRF 检查）；
> 配上之后 `api_get` / `api_post` / `browser_open` / `search` / `notify_send(email)` 都归它管，
> 并且**逐跳复检**（清单内的域名 302 到清单外会被掐断）。签名密钥与快照上限同理，写进配置即生效。

## 剧本：让一个长任务自己跑完

| # | 做什么 | 应该看到什么 | 说明 |
|---|---|---|---|
| 1 | 说：`给 examples/01_security_lab/workspace/note.txt 写一个 30 行的说明文档，分三节` | 模型调用 `file_write` → 被 403 拦（默认只读） | 先用 `/permission write` 提权；这一步在演示"权限是人的决定" |
| 2 | 说：`这个任务比较长，先建个目标：把 note.txt 扩写成 30 行说明文档并保持三节结构` | 模型调用 `goal_create`，出现目标 id | 持久目标存盘（`.ace_goals.json`），**不是**上下文里的约定 |
| 3 | 什么都不做，看着它 | 每轮自动继续推进，直到完成/暂停/阻塞/预算耗尽 | 这是 `goal` 与"让模型记着"的区别：状态在执行层，不在对话里 |
| 4 | 输入 `/goal` | 目标状态、轮次、revision | 重启 ACE 后 `/goal resume` 还能接着跑 |
| 5 | 说：`这块调研比较独立，交给子代理：查一下 Python 里写 CSV 的三种方式并对比` | 调用 `subagent`（`spawn` 新上下文 / `fork` 继承当前会话） | 子代理有自己的工具循环（最多 8 轮），**跟随主会话的沙箱档位**——主会话开 job/docker，子代理不会偷跑在宿主上 |
| 6 | 说：`把刚才的结论存进知识库，文件名 notes/csv.md` | 调用 `kb_add` | 知识库落在项目 `.ace_kb/`（或 `--kb <目录>` 指定的外挂目录），跨会话持久 |
| 7 | 新开一次会话，说：`从知识库里找一下 CSV 的结论` | 调用 `kb_search` 命中上一步写的文件 | 这才是"记忆"：不是模型记得，是它能查回来 |
| 8 | 输入 `/audit` | 全链路事件日志（权限裁决 / 守卫 / 快照 / 工具往返） | 出问题时有据可查，而不是"感觉它刚才好像做了点什么" |

## 收尾建议

```bash
/undo            # 最近一次写操作回滚（写前自动快照）
/snapshots       # 看有哪些快照可回
/permission readonly   # 干完活降回只读
```

想把这些动作跑在真实边界里（而不是进程内策略层）：

```bash
ace --install-executor             # 装官方预编译 Go 执行器（Windows，无需本机 Go）
python ai_code.py --sandbox job    # Windows Job Object
python ai_code.py --sandbox docker # 一次性容器
```

机制与残留风险见 [`docs/SECURITY-MODEL.md`](../../docs/SECURITY-MODEL.md)；
工具与权限的权威清单见 [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) 与 `tools/registry.py`。
