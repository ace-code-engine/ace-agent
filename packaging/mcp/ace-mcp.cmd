@echo off
rem ACE MCP 启动器（非侵入式接入包）
rem
rem 为什么要有它：host 的 MCP 配置只需要一个 command 字符串，而这个字符串里
rem 不该出现"用户的 python 装在哪"或者"解压到了哪"—— 那些都在这里解决掉。
rem   · %~dp0 = 本文件所在目录（解压位置随即确定，配置里不用写死）
rem   · --project-root 不传 = ACE 用 cwd，也就是 **host 的工作区**（最自然的非侵入式默认）
rem   · 后面的 %* 让 host 仍可追加 --permission write / --project-root 等参数
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ACE_MCP_DIR=%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ace-mcp] 找不到 python。请装 Python 3.10+ 并确保它在 PATH 里， 1>&2
  echo [ace-mcp] 或者改用已安装的 ACE 冻结版：ace.exe --mcp  ， 1>&2
  exit /b 127
)

python "%ACE_MCP_DIR%ai_code.py" --mcp %*
exit /b %errorlevel%
