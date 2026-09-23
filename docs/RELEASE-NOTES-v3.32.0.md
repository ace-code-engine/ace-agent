# ACE v3.32.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3320-2026-09-19)。无破坏性变更。

## 一句话

以前"菜单好不好用"取决于你运气 —— 跑到的那个 Python 装了 `prompt_toolkit` 才有浮层菜单。
这一版把这件事**确定性化**：自动找出能用的环境，找不到就地建一个，离线也能装。

## ✨ 一键准备环境

```bash
ace --setup            # 或 ace --install-ui
```

它会按顺序检查（每一步都**真的跑一次 `import prompt_toolkit`**，不是猜）：

1. `ACE_PYTHON` 环境变量（你显式指定的那套）
2. 项目内 `.ace_env`
3. 本机常见开发环境
4. PATH 上的 `python` / `python3`
5. `py -3` 启动器

都没有 → 在项目下建 `.ace_env` 并安装依赖。装完会明确告诉你**用的是哪个解释器**，以及
"当前这个不是它、下次请用 `ace` 启动器"。

## ✨ 离线也能装

内网 / 没 pip 源的环境：把 wheel 放进 `vendor/`，再跑 `ace --setup` —— 会优先用本地 wheel
（`pip install --no-index vendor/*.whl`），装不上才退回在线。

```bash
pip download prompt_toolkit -d vendor/     # 在能联网的机器上准备
ace --setup                                # 目标机器离线安装
```

## ✨ 多套环境并存

| 变量 | 作用 |
|---|---|
| `ACE_PYTHON` | 显式指定某个解释器（优先级最高） |
| `ACE_ENV_DIR` | 把本地环境建到别处（默认 `<项目>/.ace_env`），多套可以并存 |

`ace.cmd` 现在会向 `setup_env.py --print-python` 问路，**不再靠猜哪个 Python 装了依赖**；
`setup_env.py` 也能单独用：

```bash
python setup_env.py            # 人看：列出这台机器上找到的环境，标出哪个可用
python setup_env.py --check    # 只看状态，不创建
python setup_env.py --json     # 机器读：{"python": …, "source": …, "candidates": [...]}
```

## 🐛 顺带修掉

`probe()` 在"不要求任何模块"时会拼出 `import ` 这样的语法错 —— 于是一个**完全可用**的解释器
会被判成不可用（测试当场抓到）。

## 📋 兼容性

- 无破坏性变更；**核心仍是零依赖**：没装 `prompt_toolkit` 也有内置输入行（菜单/历史/行编辑，
  标准库实现），只是不画浮层
- 新增测试段 `[58]`（23 项断言）
- 下一批：全屏鼠标滚轮与点击、折叠读搜组的进行中实时说明、通知区、历史视图第二层

---

# ACE v3.32.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3320-2026-09-19). No breaking changes.

## In one line

Whether the menu worked used to depend on luck — only a Python that happened to have `prompt_toolkit` got the overlay menu. This release makes it deterministic: find a usable environment, create one if there is none, and work offline too.

## ✨ Prepare the environment in one command

```bash
ace --setup            # or ace --install-ui
```

It checks, in order, and **actually runs `import prompt_toolkit`** at every step instead of guessing: `ACE_PYTHON` → project-local `.ace_env` → common local dev environments → `python`/`python3` on PATH → `py -3`. If none works, it creates `.ace_env` and installs the dependency, then tells you exactly **which interpreter** is now in use (and that the one you are running is not it — use the `ace` launcher next time).

## ✨ Works offline

On an air-gapped machine, drop the wheel into `vendor/` and run `ace --setup`: local wheels are tried first (`pip install --no-index vendor/*.whl`), online pip is the fallback.

## ✨ Multiple environments side by side

`ACE_PYTHON` pins one explicitly (highest priority); `ACE_ENV_DIR` puts the local environment somewhere else (default `<project>/.ace_env`). The launcher now asks `setup_env.py --print-python` for the answer instead of guessing, and the script is usable on its own (`--check`, `--json`).

## 🐛 Also fixed

`probe()` built `import ` (a syntax error) when asked to require no modules, so a perfectly usable interpreter was judged unusable — the test caught it.

## 📋 Compatibility

- No breaking changes; **the core is still zero-dependency** — without `prompt_toolkit` you still get the built-in input line (menu, history, line editing), just without the overlay
- New test section `[58]` (23 assertions)
- Next batch: mouse wheel and click in full screen, live progress inside collapsed groups, the notification area, and the second layer of the history view
