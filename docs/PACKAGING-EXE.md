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

**先跑自检**，再构建。这道自检是在 `build_exe.ps1` 连续三次弄红 CI 之后加的，它盯的正是那三次
的共同根因——**runner 用 Windows PowerShell 5.1 跑这个脚本，而本机用 pwsh 7，5.1 会把无 BOM
的脚本按 ANSI 读**，所以脚本里出现任何一个非 ASCII 字节（连注释里的中文都算）都会让它在 CI 上
**解析失败**，而本机完全看不出来：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/check_packaging.ps1
```

它检查这些事：

| 检查 | 对应踩过的坑 |
|---|---|
| 每个打包脚本都是纯 ASCII（并点名是哪几行） | 注释里写中文 → CI 解析崩 |
| 无 BOM | 一条规则，不留特例 |
| 能被当前 PowerShell 解析 | 同上 |
| 没用 `$Args`/`$Input`/`$Matches` 当参数名 | 自动变量会把参数值吞掉，脚本静默以空参数运行 |
| 冒烟用调用运算符而非 `Start-Process` | `-ArgumentList` 按 C 运行时规则拼行，带空格的参数被拆开 |
| `core/version.py` / CHANGELOG 标题 / tag 三者一致 | 发布步骤 grep 的正是 `## [v<版本>]`；这条判据自己曾因少写一个 `v` 而误报 |

它还会**真跑一遍源码**，确认每个冒烟 mark 都是场景确实会输出的文本——断言一条永不出现的文本，
无论包多正确都不可能通过。

## 图标

`assets/ace.ico` 由 `assets/logo.svg` 生成，**纯标准库、零外部工具**：

```powershell
python packaging/make_icon.py --preview 512   # 另存一张大图便于肉眼核对
```

为什么自己写光栅化：svg→png 那一套（cairosvg / svglib / Pillow / ImageMagick / Inkscape /
无头浏览器）每一条都要联网装或要外部二进制，而本项目的构建依赖刻意为零。`logo.svg` 恰好是
**纯几何图形**，所以一个够用的小光栅化器可行——支持 `<rect>`（含 rx）、`<path>`（M/L/C/Z）、
纯色与 `linearGradient`、`stroke-width/linecap/linejoin`，多一样都不做；抗锯齿用 3×3 超采样。

**一个踩过的坑写在这里**：SVG 的 `gradientUnits` **默认是 `objectBoundingBox`**，即
`x1="0" y1="0" x2="1" y2="1"` 指的是**图形包围盒的比例**而非绝对坐标。第一版把它当绝对坐标，
于是所有采样点的 `t` 都被钳到 0，整条盾牌描边渲染成第一个 stop 的纯青色（浏览器里明明有渐变）。
`make_icon.py` 现在按包围盒换算，并把这份教训写在 `LinearGradient` 的 docstring 里。

生成的 ICO：16 / 24 / 32 / 48 / 64 / 128 / 256 七个尺寸，32bpp，内嵌 PNG（Vista 起支持）。

## 构建

```powershell
# 需要先把 PyInstaller 装进用来冻结的那个解释器
<python> -m pip install pyinstaller requests

powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_exe.ps1
#   -Python <路径或命令名>   指定冻结用的解释器（`python` 这种命令名也行，会真跑一次验证）
#   -Clean                   先清掉 build/ 与 dist/
#   -SkipSmoke               只构建（会打一条醒目的"这个包没跑过"警告）
```

产物：`dist\ace\`（整个目录就是载荷，下一步的安装包与便携 zip 都由它来）。脚本最后会打印体积。

## 安装包（MSI，自带环境，用户机器上不需要 Python）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_installer.ps1
#   -Version 3.41.0   覆盖版本（默认读 core/version.py）
#   -Python <解释器>   生成器用的解释器（默认自动探测）
#   -NoZip            不另出便携 zip
```

产物：`dist\ace-<版本>-windows-amd64.msi`（WiX）＋ 同载荷的便携
`...-windows-amd64.zip`。**两个都挂在 Release 上**：MSI 是主推渠道，zip 给不想装的人。

`packaging/make_wix.py` 由载荷目录**生成** WiX 源文件（每个文件一个 `<Component>`，GUID 用
`uuid5(固定命名空间, 相对路径)` 确定性推出——MSI 的升级/卸载依赖产品身份稳定，随机 GUID 会让
每次构建变成不同产品），然后调 `candle` + `light` 编译。生成过程本身就**顺带验了载荷完整性**：
少一个文件就少一个组件引用。编译完还会把 MSI 读回来，确认里面真有 `ace.exe` 的引用——
只信 `light` 的退出码不够，一个空壳 MSI 也能编出来。

### 为什么是 WiX，不是 Inno Setup

两者都能做"自带环境、双击安装"。选 WiX 的理由只有一条，但很硬：**能用的 WiX 工具链在这台机器上
存在，Inno Setup 不存在。** 而"本地不可验证"在这条发布链上已经连续弄红 CI 五次——每次都是同一个
模式：**我在本地看不到 CI 会看到的东西**。所以凡是在本地能真跑一遍的方案，优先于"理论上更好但
只能靠 CI 兜底"的方案。第一版确实是 Inno Setup，写完才发现本机没有 ISCC，也就无法编译验证，
于是换掉。

代价要说清楚：**WiX 3 的 MSI 门槛比 Inno 高**。所以第一版的安装包能力是收窄的——

| 能力 | Inno 版（未采用） | WiX 版（当前） |
|---|---|---|
| 装到 `Program Files\ACE` | ✅ | ✅（`InstallScope="perMachine"`） |
| 开始菜单两项（正常 / 离线演示，`cmd /k` 起终端） | ✅ | ✅ |
| 卸载干净 | ✅ | ✅（组件 GUID 稳定，MSI 自己记账） |
| 只装给当前用户 | ✅ | ❌ 暂只支持全机安装 |
| 可选加入 PATH | ✅ | ❌ 暂不做（改 PATH 需要 `Environment` 表或自定义动作，而 MSI 的自定义动作是最容易做坏的一块；宁可先不做） |
| 可选桌面快捷方式 | ✅ | ❌ 同上，先不做 |

后三项不是"做不了"，是**先把能验证的部分做对**。要补时按同样纪律：补上就得能在本机验。

**为什么单开一步而不是塞进 `build_exe.ps1`**：构建并验证载荷是一件事，把它包起来是另一件事。
分开之后，改安装行为不必重新冻结，而且冒烟门禁的意义保持纯粹——它验的是载荷，不是包装。
所以 `build_installer.ps1` **不自己构建载荷**：`dist\ace\` 不存在就停下并告诉你该跑哪条命令。
包一个没验过的载荷是本末倒置。

**CI 上要装 WiX v3**：`windows-latest` 预装的是 v4/v5（只有 `wix.exe`，没有 `candle`/`light`），
而生成器 target 的是 v3 schema。工作流里显式 `choco install wixtoolset`。

## 冒烟门禁：为什么构建脚本敢说自己成功

**没跑过的 exe 一律不算构建成功。** `build_exe.ps1` 在报告成功之前，会把打包出来的
`dist\ace\ace.exe` 真的跑四个场景，每个都要求：退出码 0、无 Traceback、无
`UnicodeEncodeError`、无替换符 `U+FFFD`，**且输出里真的出现了预期内容**（只看"能启动"
是抓不到"资源没打进包"的）：

| 场景 | 抓什么 |
|---|---|
| `--version` | 进程能不能起来 |
| `--preview` | **资源是否齐**——首屏要读 `locales/` 的每一句标签和 `assets/` 的 logo |
| `--mock --permission readonly --input …` | 离线全链路：模型 → 执行层 → 工具往返 |
| `--mock --tools --permission full --input …` | 原生工具调用路径在冻结包里也通 |

任一场景失败 → 脚本非零退出 → 不发布。证据落在 `packaging\_smoke\`。

**为什么不把 `code_execute` 的 501 也做成冒烟场景**：mock 模型是脚本化的，只调 `datetime_now`，
永远不会调 `code_execute` —— 断言一条注定不出现的文本，无论包多正确都不可能通过（这条我犯过）。
它由 `test_all [10]` 直接断言（打桩 `sys.frozen` 驱动工具），那才是它该待的地方：
**冒烟门禁只该断言它能真正观察到的东西**。

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
