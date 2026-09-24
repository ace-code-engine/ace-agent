# 打包分发：Windows 单目录发行包（PyInstaller）

> 本文件讲的是 **exe 这条分发路**。`docs/PACKAGING.md` 讲的是 **wheel/pyproject 那条路**，
> 结论是"暂不产出"——两者不冲突，原因见下。

## 为什么 exe 走得通，wheel 走不通

`docs/PACKAGING.md` 拒绝 wheel 的理由是：运行时代码把资源按 `__file__` 相对模块解析，
扁平安装后 `prompts/`、`locales/`、`executor/` 会散落到 `site-packages` 根，出现
"装得上跑不动"。

**PyInstaller 恰好绕开了这一点**：它把资源连同解释器一起收进一个自包含目录，并在运行时
设置 `sys._MEIPASS`，而 `__file__` 相对解析在冻结包里照旧成立。所以：

| | wheel / pip 安装 | exe（PyInstaller 单目录） |
|---|---|---|
| 资源 `__file__` 相对解析 | ✗ 散落 site-packages | ✅ 包内相对路径成立 |
| 用户机器上需要 Python | 需要 | **不需要**（自带解释器） |
| `code_execute` | ✅ | ❌ 见下 |

## 冻结后不成立的东西（exe 会明说，不会悄悄坏）

| 能力 | 状态 | 原因 |
|---|---|---|
| 对话 / 工具 / 文件 / 终端 / 权限裁决 / 快照回滚 | ✅ | 纯 stdlib 核心，资源随包 |
| `code_execute` | ❌ **501** | 它靠 `subprocess.run([sys.executable, tmp_file])` 跑 Python 代码；冻结后 `sys.executable` 是 `ace.exe` 自己，不是解释器，而最小环境又把 PATH 洗掉，找不到第二个解释器。已加冻结探测（`tools/code_tools.py: _is_frozen()`），`test_all [10]` 有 5 条断言盯着 |
| `--install-ui` / `--setup` | ❌ 无意义 | 包内已自带解释器与界面依赖；`setup_env.py` 那套"找/建解释器"逻辑在冻结包里没有用武之地 |
| `--install-executor` | ⚠️ 视情况 | 打包时 `executor/` 里有 Go 二进制就一并带上；没带则需要联网下载 |

**不悄悄退回"找系统 Python"是有意的**：那会把"宿主机装没装 Python"变成行为差异，同一份
发行包在两台机器上能力不同——比明确禁用更难排查。这与 ACE 其余"不静默降级"的取态一致。

## 怎么构建

```powershell
# 需要先把 PyInstaller 装进用来冻结的那个解释器
<python> -m pip install pyinstaller

powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_exe.ps1
#   -Python <路径>   指定冻结用的解释器（默认依次试 ACE_PYTHON / C:\aider_env / .ace_env / PATH）
#   -Clean           先清掉 build/ 与 dist/
#   -SkipSmoke       只构建（会打一条醒目的"这个包没跑过"警告）
```

产物：`dist\ace\`（整个目录就是要发布的包，压缩后挂 Release）。脚本最后会打印体积。

## 冒烟门禁：为什么构建脚本敢说自己成功

**没跑过的 exe 一律不算构建成功。** `build_exe.ps1` 在报告成功之前，会把打包出来的
`dist\ace\ace.exe` 真的跑四个场景，每个都要求：退出码 0、无 Traceback、无
`UnicodeEncodeError`、无替换符 `U+FFFD`，**且输出里真的出现了预期内容**（只看"能启动"
是抓不到"资源没打进包"的）：

| 场景 | 抓什么 |
|---|---|
| `--version` | 进程能不能起来 |
| `--preview` | **资源是否齐**——首屏要读 `locales/` 的每一句标签和 `assets/` 的 logo |
| `--mock --input …` | 离线全链路：模型 → 执行层 → 工具往返 |
| `--tools --permission full --input "run this python code…"` | `code_execute` 是否**如实**报 501，而不是拿 `ace.exe` 去跑 `.py` |

任一场景失败 → 脚本非零退出 → 不发布。证据落在 `packaging\_smoke\`。

## 发布

`.github/workflows/release-exe.yml`（手动触发，或由发布流程调用）：

1. 装构建依赖 → 读 `core/version.py` 拿版本；
2. **先跑源码全量测试**（打包不该掩盖一个本来就红的仓库）；
3. 构建 + 冒烟门禁；
4. 压缩成 `ace-<版本>-windows-amd64.zip` 上传 artifact；
5. 挂到 tag `v<版本>` 的 Release 上（Release 不存在就创建）。

**与 `release-executor.yml` 共用同一个 tag `v<版本>`。** 两者谁先跑都行：先跑的创建
Release，后跑的 `gh release upload --clobber` 追加资产。

## 在 CI 上构建，而不是在这台机器上

PyInstaller 不在仓库的离线 wheel 清单里（`vendor/` 只覆盖界面依赖），所以构建必须发生在
**能访问 PyPI 的环境**。GitHub Actions 的 `windows-latest` 满足这一点；离线机器则需要先把
PyInstaller 的 wheel 拿到本地再 `pip install <wheel>`。
