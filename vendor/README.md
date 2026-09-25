# vendor/ —— 离线依赖的落点

ACE 的**安全核心是零依赖**的（执行层 / 网关 / 记忆 / CLI，只用标准库）。依赖分两类：

- **必需**：`requests` —— 模型调用（`core/ace_client.py`）与联网工具（`tools/web_tools.py`）
  的唯一出网点直接 `import requests`，没有回退；没有它连不上模型。见 `docs/ADR.md` ADR-004。
- **可选**：`prompt_toolkit`（浮层补全菜单、输入历史、底部状态栏、全屏会话）。
  没有它也能用 —— `setup_env.py` 会退回内置输入行（`ui/ace_prompt.py`，标准库实现，
  菜单/历史/行编辑一样不少），只是不画浮层。

## 怎么用

在线（默认）：

```bash
python setup_env.py --ensure     # 建 .ace_env 并装 requests + prompt_toolkit + textual + rich
ace --install-ui                 # 同上（启动器里的等价入口）
```

离线（内网 / 无 pip 源）：把 wheel 放进这个目录，再跑同一条命令 —— `setup_env.py` 会
**优先用本地 wheel**（`pip install --no-index vendor/*.whl`），装不上才退回在线：

```bash
python setup_env.py --vendor     # 在能联网的机器上把【完整依赖集】下到 vendor/
python setup_env.py --ensure     # 目标机器上离线安装
```

> **用 `--vendor`，不要手敲 `pip download prompt_toolkit`。** 离线这一路是**全有或全无**：
> `setup_env.py` 装完本地 wheel 后会真的 `import` 一遍 `REQUIRED` 里的每一个模块，
> 缺一个就整段退回在线安装。而 `REQUIRED` 现在是
> `("requests", "prompt_toolkit", "textual", "rich")` —— 所以离线包必须**连 `requests`
> 及其传递依赖（urllib3 / certifi / idna / charset-normalizer）一起**备齐，
> 只备 `prompt_toolkit` 会在这一步判失败。`--vendor` 会按 `REQUIRED` 下全套。

## 多套环境

- `ACE_PYTHON`：显式指定某个解释器（优先级最高）
- `ACE_ENV_DIR`：把本地环境建到别处（默认 `<项目>/.ace_env`），多套环境可以并存
- 启动器每一步都会**真的跑一次 `import`** 来验证（探测的是整个 `REQUIRED`），不靠猜

`vendor/*.whl` 不进 git（`.gitignore` 已排除），只保留这份说明。
