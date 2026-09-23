# vendor/ —— 离线依赖的落点

ACE 的**核心是零依赖**的（只用标准库）。只有"交互体验"那一层需要 `prompt_toolkit`：
浮层补全菜单、输入历史、底部状态栏、全屏会话。没有它也能用 —— `setup_env.py` 会退回
内置输入行（`ui/ace_prompt.py`，标准库实现，菜单/历史/行编辑一样不少），只是不画浮层。

## 怎么用

在线（默认）：

```bash
python setup_env.py --ensure     # 建 .ace_env 并 pip install prompt_toolkit
ace --install-ui                 # 同上（启动器里的等价入口）
```

离线（内网 / 无 pip 源）：把 wheel 放进这个目录，再跑同一条命令 —— `setup_env.py` 会
**优先用本地 wheel**（`pip install --no-index vendor/*.whl`），装不上才退回在线：

```bash
pip download prompt_toolkit -d vendor/        # 在能联网的机器上准备好
python setup_env.py --ensure                  # 目标机器上离线安装
```

## 多套环境

- `ACE_PYTHON`：显式指定某个解释器（优先级最高）
- `ACE_ENV_DIR`：把本地环境建到别处（默认 `<项目>/.ace_env`），多套环境可以并存
- 启动器每一步都会**真的跑一次 `import prompt_toolkit`** 来验证，不靠猜

`vendor/*.whl` 不进 git（`.gitignore` 已排除），只保留这份说明。
