# 命令参考（Command Reference）

> 本文档由 README「命令参考」一节拆分而来（docs/README-RESTRUCTURE.md，v3.7），内容与当时 README 保持一致。
> README 入口见「常用命令」（只列最常用的）；完整清单在这里。

**首页**：↑/↓ 选择 · 数字直选 · Enter 确认 · Esc/q 退出。聊天内 `exit` 回首页，首页 `7`/`Esc`/`q` 才真正退出。

**斜杠命令**（聊天里输入 `/` 实时弹菜单，需 `prompt_toolkit`，未装自动降级）：

| 分类 | 命令 |
|---|---|
| 会话 | `/help` `/clear` `/status` `/stats` `/exit` |
| 安全 | `/permission [level]` `/snapshots` `/undo` `/rollback <id>` |
| 模型 | `/provider [名称\|编号] [key]` `/model <名称>` `/config` `/mock` |
| 工具 | `/open <路径>` `/edit <路径>` `/search <关键词>` `/memory` `/report` |

```bash
/provider                   # 列出 9 家厂商 · 10 入口（当前标 ✓）
/provider zhipu             # 一键切智谱（自动换到 glm-4.7-flash）
/provider 3 sk-你的key      # 编号 + 密钥一把梭
```

**@ 快捷方式**（输入 `@` 弹菜单）：

| 命令 | 作用 | 示例 |
|---|---|---|
| `@lang` | 切换回复语言 + 界面语言（zh/en/ja） | `@lang en` |
| `@skill` | 切换技能，描述与推荐工具注入提示词 | `@skill coding` |
| `@file` | 把文件内容加入上下文（≤4000 字符自动截断） | `@file README.md` |
| `@folder` | 把文件夹列表加入上下文（≤30 项） | `@folder tools` |
| `@refs` / `@clear` | 查看 / 清空当前引用（最多保留 3 项） | `@refs` |

可选技能：`coding`（默认推荐 `code_execute` `file_write` `terminal_exec`）· `writing` · `analysis` · `fiction` · `general`。

**在对话里打开文件**——默认只给可点击链接，不抢焦点、不弹窗：

```
（自己动手）  ❯ /open 报告.docx        # 系统默认程序打开
              ❯ /edit main.py          # 优先 VS Code
（叫 Agent）  ❯ 帮我打开桌面的报告.docx
              🔗 点击打开文件: C:\Users\...\报告.docx   ← 点一下才展开
```
