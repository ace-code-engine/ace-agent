# 交接提示词：R-03 双前端模型客户端合并

> 用途：把下面「可直接粘贴的提示词」整段复制到另一个对话（或另一个 agent 会话）里执行。
> 这一份是**自包含**的：接手的人不需要读我们的聊天记录，也不需要问任何问题。
> 已经在跑的子代理用的是同一份口径（分支 `r03-client-merge`，worktree `../ace-r03`）。

---

## 一、背景（给接手的人）

项目：ACE —— 本地 AI 编程代理，纯 Python，安全核心零依赖。
问题：**两套模型客户端并存**，是行为漂移的源头：

| 前端 | 类 | 形态 |
| --- | --- | --- |
| `ai_code.py`（交互 CLI） | `ModelClient` | 流式 + `requests` + 重试 + 工具调用 |
| `agent_runner.py`（headless） | `ModelProvider` | `urllib` 一次性 + 另一套错误文案 |

`core/ace_model.py` 里已经收拢了一部分纯逻辑（`trim_history` / `error_hint` / 消息组装），
**HTTP 层还没合**。这就是 R-03 剩下的部分（安全半边早在 v3.9 就做完了）。

## 二、验收标准（缺一不可）

1. **两个 CLI 行为不变**：`python ai_code.py --mock …` 与 `python agent_runner.py --mock …`
   的流式输出、错误文案、提供商切换都不回归；
2. `python test_all.py` → **0 失败**（当前 2029/2029；只允许因为**新增**断言而变多）；
3. `ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` → 零命中；
4. **仓库里只剩一处构造 `/chat/completions` 请求的代码**（在报告里贴 grep 结果证明）；
5. `execution_layer.py` 的 14 阶段管线、权限/审批三轴、`ERROR_STATUSES` 语义**不许改**；
6. 不升版本号、不重录演示图、不动 `CHANGELOG.md` 与 README 徽章；
   新增文件要登记进 `docs/ARCHITECTURE.md` 的目录树（守卫 `[38]` 会查，且**只查已 git add 的文件**）。

## 三、可直接粘贴的提示词

```
你在 ACE 项目（本地 AI 编程代理，Python）里完成 R-03：把两套模型客户端合并成一套。

仓库路径：C:\Users\69215\Desktop\AI_Project\ace
（如果你想隔离作业，先建 worktree：git -C <仓库> worktree add ../ace-r03 -b r03-client-merge，
 然后在 worktree 里干活，别动主工作树。）

问题：ai_code.py 的 ModelClient（流式 + requests + 重试 + 工具调用）与 agent_runner.py 的
ModelProvider（urllib 一次性）并存，是行为漂移源。core/ace_model.py 已收拢纯逻辑，HTTP 层未合。

要求（缺一不可）：
1. 两个前端行为不变：python ai_code.py --mock … 与 python agent_runner.py --mock … 的流式输出、
   错误文案、提供商切换都不回归；
2. python test_all.py → 0 失败（当前 2029/2029，只允许因为新增断言而变多）；
3. ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811 → 零命中；
4. 仓库里只剩一处构造 /chat/completions 请求的代码（报告里贴 grep 证明）；
5. execution_layer.py 的 14 阶段管线、权限/审批三轴、ERROR_STATUSES 语义不许改；
6. 不升版本号、不重录演示图、不动 CHANGELOG 与 README 徽章；新增文件登记进
   docs/ARCHITECTURE.md 目录树（守卫 [38] 只查已 git add 的文件，所以先 git add 再跑测试）。

做法建议（可以推翻，但要在报告里说明为什么）：
- 先读 core/ace_model.py、ai_code.py 的 ModelClient、agent_runner.py 的 ModelProvider，
  以及覆盖它们的测试段；
- 选一处作为唯一实现（扩展 core/ace_model.py 或新增 core/ace_client.py），它必须支持：
  (a) 流式增量回调、(b) 一次性非流式、(c) 工具调用载荷、(d) 现有重试/ace_http 策略、
  (e) 两种协议（OpenAI 兼容 / Anthropic 兼容）的 URL 与请求头；
- 一次迁一个前端，每步都跑测试；调用方契约不同就留薄适配层（例如 agent_runner 只打一行）；
- 加断言把"只剩一处请求构造"钉住（源码级守卫，参照 test_all.py 里 [38] 的写法）。

环境（必须用这几个解释器，裸 python 是坏的商店占位）：
- 无依赖真 Python：C:\Users\69215\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe
- 带依赖（prompt_toolkit + textual + rich）与 ruff：C:\aider_env\Scripts\python.exe / C:\aider_env\Scripts\ruff.exe
两个都跑全量（它们跳过的段不同；无依赖那个对齐 CI）。

已知坑（省你时间）：
- 跑 python 前设 $env:PYTHONIOENCODING="utf-8"，否则中文输出在 Windows 控制台会炸；
- PowerShell 里 heredoc 与带嵌套引号的 python -c 不可用：把脚本写成临时 .py 再跑；
- test_all.py 支持 --only N / --skip / --upto / --list（段号 [1]…[66]）；
- 别用 PowerShell 字符串操作改 CRLF 或含中文的文件：用 Python 显式 encoding + newline="";
- *.cmd 必须保持纯 ASCII（cmd.exe 会错位解析多字节批处理）；
- 提交用 git commit -F <消息文件>，不要 git add -A。

交付报告（简洁）：
- 改了什么（文件 + 为什么）、新模块的公开 API、两个前端怎么共用它；
- 跑过的命令与结果（两个解释器的通过数、ruff、证明只有一处请求构造的 grep）；
- 你**故意没做**的事与残余风险；
- 分支上的提交哈希（不要 push）。
遇到解决不了的阻塞就停下报告，不要假装成功。
```

## 四、为什么值得做（给决策的人）

- **漂移成本**：两套实现意味着"改了一边忘了另一边"，而模型的错误文案、重试策略、超时
  正是用户最容易察觉的地方；
- **测试面**：现在只覆盖 mock 路径；合并之后真实端点的 smoke 才有意义（一处改，两处都受益）；
- **风险点是"改行为"**：所以验收标准第 1 条要求"两个前端行为不变"，并且必须真机（或
  至少 mock + 真实端点 smoke）验证 —— 这也是它一直在待办里没做的原因。
