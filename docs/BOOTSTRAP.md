# 一条命令跑起来（Bootstrap Playbook）

> 目标：把"环境问题"从拦路虎变成**一行命令**。
> 三条路任选，**都不需要 API Key、不需要联网**（离线演示走 `--mock`）。

## 选哪条路

| 你的情况 | 用这条 | 需要什么 |
|---|---|---|
| 想先看一眼，不想装东西 | **路线 1 · Docker** | Docker |
| 有 Python，打算长期用 | **路线 2 · 源码**（推荐） | Python 3.10–3.12 |
| Windows，不想碰 Python | **路线 3 · 预编译 exe** | 无 |

---

## 路线 1 · Docker（最省事）

```bash
docker compose run --rm ace
```

首次会自动构建镜像。`--mock` 已经写进 `docker-compose.yml` 里那个 service 的 `command`，
所以**不需要任何密钥**；容器内是非 root 用户（`USER ace`），并且建议容器里从 `readonly` 起步。

接真实模型：把 compose 里的 `command` 换成 `python ai_code.py`，或直接用 compose 中那个可选的 `ollama` 服务。

---

## 路线 2 · 源码（推荐）

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
PY=$(python3 setup_env.py --ensure --print-python) && "$PY" ai_code.py --mock
```

这条命令的两个零件都在 `setup_env.py` 里：

| 参数 | 作用 |
|---|---|
| `--ensure` | 依次试候选解释器，返回**第一个真的能 import 界面依赖**的那个；一个都没有就在项目下建 `.ace_env` 并按 **本地 wheel（`vendor/*.whl`，离线可用）→ pip 在线装** 的顺序装依赖 |
| `--print-python` | **只打印一行**解释器路径（没找到就是空行），所以能直接喂给 `$()`，也供 `ace.cmd` 消费 |

它失败时**如实报错并给出可复制的命令**，不会假装成功 —— 因为"看着像装好了"是最坏的结果。

**Windows（PowerShell）**：

```powershell
git clone https://github.com/ace-code-engine/ace-agent.git; cd ace-agent
.\ace.cmd --mock
```

`ace.cmd` 自己会做解释器解析（`ACE_PYTHON` → 项目 `.ace_env` → 本机常见环境 → `PATH` → `py -3`），
**不需要你先想清楚用哪个 python**。界面依赖缺失时：`.\ace.cmd --install-ui`。

---

## 路线 3 · 预编译 exe（Windows，不用装 Python）

到 [Releases 页面](https://github.com/ace-code-engine/ace-agent/releases) 下载
`ace-<版本>-windows-amd64.zip`，解压到任意目录：

```powershell
.\ace\ace.exe --mock     # 离线：确认这个包是完整的
.\ace\ace.exe            # 接真实模型：进首页选 2 走配置向导
```

两件容易意外的事：**SmartScreen 会拦一下**（没有代码签名 —— *更多信息* → *仍要运行*）；
**它是一整个目录，不是单个文件**（`ace.exe` 必须和旁边的 `_internal\` 待在一起）。

冻结发行里哪几项能力不成立、以及"包没跑过就不算构建成功"的冒烟门禁 —— 见 [`PACKAGING-EXE.md`](PACKAGING-EXE.md)。

---

## 三个经典环境坑（以及怎么判断）

| 症状 | 真因 | 怎么办 |
|---|---|---|
| 菜单不能上下选、没有历史、底栏不显示 | 你跑的那个 `python` 没装 `prompt_toolkit` | `python setup_env.py --check` 看它**实际选了哪个**解释器；`--ensure` 建一个能用的 |
| `python` 打开的是应用商店 | Windows 的 Store 占位 exe（不是真 Python） | 用 `py -3`，或直接 `.\ace.cmd`（它会绕过占位） |
| 机器没网，装不上依赖 | 依赖要从 PyPI 拉 | `vendor/` 里已内置 wheel，`--ensure` **会先用它**；要给别的离线机器准备，在有网的机器上跑 `python setup_env.py --vendor` 把 wheel 下进 `vendor/` |

> 这三个坑的共同点是**症状看起来像功能缺失，真因却是环境**。`setup_env.py` 的存在就是为了让
> "用哪个解释器"不再由运气决定。

---

## 装好了怎么验证

```bash
python test_all.py --only 38,39,68     # 纯 stdlib，不需要密钥
```

三段分别是：`[38]` 权威目录树 ↔ 真实文件、`[39]` 文档口径数字 ↔ 源码、`[68]` 无乱码 + 徽章版本单源。
全量是 `python test_all.py`（随平台浮动，以它的实际输出为准）。

---

## 下一步

- 5 分钟上手路径 + 三维度矩阵 + 十个坑：[`GETTING-STARTED.md`](GETTING-STARTED.md)
- 它挡住了什么、没挡住什么：[`security/SECURITY-FAQ.md`](security/SECURITY-FAQ.md)
- 全部文档的入口：[`README.md`](README.md)
