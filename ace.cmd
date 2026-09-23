@echo off
rem ACE 启动器：只负责"找出一个能用的 Python"，其余交给 ai_code.py。
rem 用法: ace [参数]   例:  ace --input "现在几点"   ·   ace --install-ui  ·   ace --setup
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
rem 默认进主界面菜单；想直接进聊天: set ACE_DIRECT_CHAT=1
cd /d "%~dp0"

rem 解释器解析顺序（多环境）：
rem   1) ACE_PYTHON 环境变量（你显式指定的那套）
rem   2) setup_env.py --print-python：它按 ACE_PYTHON → 项目内 .ace_env → 本机常见开发
rem      环境 → PATH 的顺序，挑**第一个真的能 import prompt_toolkit** 的解释器
rem   3) 上面都没结论时，退回一个"能跑起来"的解释器（功能照用，只是没有浮层菜单）
rem   4) py -3 启动器
rem 关键点：不再靠"猜哪个 python 装了依赖" —— 每一步都真的跑一次 import 来验证。
set "_ACE_PROBE="
if defined ACE_PYTHON (set "_ACE_PROBE=%ACE_PYTHON%")
if not defined _ACE_PROBE (if exist "C:\aider_env\Scripts\python.exe" set "_ACE_PROBE=C:\aider_env\Scripts\python.exe")
if not defined _ACE_PROBE (if exist ".ace_env\Scripts\python.exe" set "_ACE_PROBE=.ace_env\Scripts\python.exe")
if not defined _ACE_PROBE (where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "_ACE_PROBE=python")
if not defined _ACE_PROBE (where py >nul 2>nul && set "_ACE_PROBE=py -3")

set "_ACE_PY="
if defined ACE_PYTHON (set "_ACE_PY=%ACE_PYTHON%")
if not defined _ACE_PY (if defined _ACE_PROBE if exist "setup_env.py" (
    for /f "usebackq delims=" %%p in (`%_ACE_PROBE% "setup_env.py" --print-python 2^>nul`) do set "_ACE_PY=%%p"
))
if not defined _ACE_PY (if defined _ACE_PROBE set "_ACE_PY=%_ACE_PROBE%")

if not defined _ACE_PY (
    echo [ACE] 没找到可用的 Python。装一个 3.10+ 并加入 PATH，
    echo       或把 ACE_PYTHON 设成你的 python.exe 全路径。
    pause
    exit /b 1
)

rem --setup / --install-ui：先把界面依赖准备好（建 .ace_env 或装进现有环境），再启动。
if /i "%~1"=="--setup" (
    "%_ACE_PY%" setup_env.py --ensure || goto :env_failed
    shift
)
if /i "%~1"=="--install-ui" (
    "%_ACE_PY%" setup_env.py --ensure || goto :env_failed
    shift
)

"%_ACE_PY%" ai_code.py --tools --max-history 12 %*
goto :eof

:env_failed
echo [ACE] 环境准备失败（上面有原因）。离线安装：把 prompt_toolkit 的 wheel 放进 vendor\ 再试。
pause
exit /b 1
