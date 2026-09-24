# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— ACE 单目录发行包（packaging/build_exe.ps1 会用它）。

为什么用**单目录**而不是单文件：单文件每次启动都要把整个包解到临时目录，ACE 启动要读
prompts/ 与 locales/，那几秒的解包延迟落在每一次冷启动上；单目录解一次就完事，也便于
用户自己翻看包内容排障。两种形态的资源解析都靠 PyInstaller 设置 sys._MEIPASS，本仓库
的资源一律走 `Path(__file__).parent`，所以两边都能工作 —— 但单目录对用户更友好。

本文件**不用非 ASCII 字符**：spec 是在 Windows 上被读的，而这条链路上出现过两次
"无 BOM 的 UTF-8 被按 ANSI 读"的事故（见 CHANGELOG v3.40.2 / REL-03）。注释里写中文
在这里没有收益，只有风险。

冻结后仍然成立 / 不再成立的东西，写在这里免得下一个人重新踩：

  成立：prompts/ locales/ assets/ tui/ 等资源 —— 一律按 __file__ 相对解析，
        PyInstaller 会一并设置 sys._MEIPASS，路径照旧。
  不再成立：
    * tools/code_tools.py 的 code_execute —— 它 `[sys.executable, tmp_file]` 去跑
      Python 代码，而冻结后 sys.executable 是 ace.exe 自己。代码里已加冻结探测，
      如实返回 501（有断言盯着，见 test_all [10]）。
    * setup_env.py 的那套"找/建解释器"逻辑 —— 冻结包自带解释器，没有它的用武之地；
      同理 --install-ui / --setup 在冻结包里没有意义。
    * ace --install-executor —— 那条路从 GitHub Release 下载 Go 执行器；如果打包时
      executor/ 里有二进制（本 spec 会带上），它就无需再下载。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent

# ---- 随包资源 --------------------------------------------------------------
# 只带**运行时会读**的东西。docs/ demo/ examples/ benchmarks/ e2e/ 是仓库资料，
# 不进发行包（它们会让包变大，且冻结后也没有对应的命令去用）。
datas = [
    (str(ROOT / "prompts"), "prompts"),
    (str(ROOT / "locales"), "locales"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "vendor"), "vendor"),
]
if (ROOT / "README.md").is_file():
    datas.append((str(ROOT / "README.md"), "."))
if (ROOT / "SECURITY.md").is_file():
    datas.append((str(ROOT / "SECURITY.md"), "."))
if (ROOT / "LICENSE").is_file():
    datas.append((str(ROOT / "LICENSE"), "."))
# Go 执行器（job 档）：本机 go build 过就有，没有也不影响打包 —— 打包时如实报告带没带。
if (ROOT / "executor").is_dir():
    datas.append((str(ROOT / "executor"), "executor"))

# ---- 隐式导入 --------------------------------------------------------------
# 目的是"别漏模块"，不是"把整个世界装进来"。collect_submodules 对仓库内的包是必要的：
# 有些模块只在运行时按名字取（MCP 的 mcp__ 前缀工具、status/registry 的处理器表、
# tui 的界面后端），静态分析看不见。
hiddenimports = []
for pkg in ("core", "tools", "ui", "cli", "tui", "gateway_v2"):
    if (ROOT / pkg).is_dir():
        hiddenimports += collect_submodules(pkg)

# 可选依赖：装了就有对应能力（联网搜索 / 浏览器 / 图像 / 全屏界面）。缺了不当失败，
# 运行时那些工具会如实报 501/503 —— 这正是本仓库一贯的语义。
for opt in ("requests", "prompt_toolkit", "textual", "rich", "playwright", "PIL",
            "markdown_it", "mdit_py_plugins", "linkify_it", "pygments", "wcwidth"):
    hiddenimports.append(opt)

# ---- 明确排除 --------------------------------------------------------------
# 排除不是"省体积"的微调：这些库一旦被拖进来，包会从几十 MB 涨到几百 MB，
# 而 ACE 的运行时代码不 import 它们（vendor/ 里的 wheel 是给 setup_env 离线安装用的，
# 已经作为 data 带上，不会被当模块分析）。
excludes = [
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "IPython", "notebook",
    "pytest", "sphinx", "setuptools", "pip", "wheel", "distutils",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
]

a = Analysis(
    [str(ROOT / "ai_code.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX 在 Windows 上常被杀软误报；这点体积不值得
    console=True,         # ACE 是终端程序，必须留控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "ace.ico") if (ROOT / "assets" / "ace.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ace",
)
