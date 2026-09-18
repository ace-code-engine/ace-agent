# 场景示例（Examples）

三个可以直接照做的剧本。每个目录里的 README 都是**剧本**：做什么 → 应该看到什么 → 看到了说明什么。

| 场景 | 你会亲眼看到 | 需要 API Key |
|---|---|---|
| [01_security_lab](01_security_lab/) · 安全实验室 | 默认只读把写操作 403 掉 → 提权 → 写入前自动快照 → 一键回滚；`terminal_exec` 逐次要人点头 | 否（`--mock` 离线） |
| [02_document_parsing](02_document_parsing/) · 文档解析 | Word/Excel/PPT/PDF/图片丢进目录就能读；项目外路径与密钥文件被 403 | 解析不用；让模型总结才要 |
| [03_multi_turn_agent](03_multi_turn_agent/) · 多轮真实任务 | 持久目标自动逐轮续跑、子代理拆活、知识库沉淀跨会话 | 是 |

先确认环境是好的（三条都不烧 key）：

```bash
python test_all.py --strict   # 全量测试。受限环境下会列出跳过项，那不是失败
python ai_code.py --mock      # 离线演示：模型 ↔ 执行层的完整闭环
python ace_doctor.py          # 环境自检：Python / 依赖 / Go 执行器 / Docker / 配置
```

> 这些示例只用到仓库自带能力，不额外拉依赖；文档解析场景按需装增强包（见该目录 README）。
> 剧本里的斜杠命令完整列表见 [`docs/COMMANDS.md`](../docs/COMMANDS.md)，安全机制见
> [`docs/SECURITY-MODEL.md`](../docs/SECURITY-MODEL.md)。
