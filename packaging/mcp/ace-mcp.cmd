@echo off
rem HooH MCP launcher (non-intrusive attach pack)
rem
rem Why this file exists: a host's MCP config takes ONE command string, and that
rem string must not contain "where is your python" or "where did you unzip it".
rem   * %~dp0 = this file's directory (the unzip location resolves itself)
rem   * no --project-root = HooH uses cwd, which is the HOST's workspace (the
rem     natural non-intrusive default)
rem   * %* lets the host still append --permission write / --project-root ...
rem
rem THREE layouts are supported, tried in this order -- best first:
rem   1. hooh-mcp.exe sitting next to this script  -> self-contained, no Python
rem   2. frozen\hooh-mcp\hooh-mcp.exe              -> the "both packs" layout
rem   3. python + ai_code.py                       -> the original source pack
rem Order matters: the frozen build is the one that works on a machine with no
rem Python, so it must win whenever it is present.
rem
rem ASCII-ONLY ON PURPOSE. See ace.cmd's header for the full explanation: cmd.exe
rem tracks its position in a batch file by byte offset, and multi-byte characters
rem break that bookkeeping once the code page changes.
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "ACE_MCP_DIR=%~dp0"

if exist "%ACE_MCP_DIR%hooh-mcp.exe" (
  "%ACE_MCP_DIR%hooh-mcp.exe" %*
  exit /b %errorlevel%
)
if exist "%ACE_MCP_DIR%frozen\hooh-mcp\hooh-mcp.exe" (
  "%ACE_MCP_DIR%frozen\hooh-mcp\hooh-mcp.exe" %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if errorlevel 1 (
  echo [hooh-mcp] No hooh-mcp.exe in this folder and no python on PATH. 1>&2
  echo [hooh-mcp] Get the self-contained build: hooh-mcp-^<version^>-windows-amd64.zip , 1>&2
  echo [hooh-mcp] or install Python 3.10+ and keep the source pack. , 1>&2
  exit /b 127
)

python "%ACE_MCP_DIR%ai_code.py" --mcp %*
exit /b %errorlevel%
