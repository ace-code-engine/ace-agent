#!/bin/sh
# ACE MCP 启动器（非侵入式接入包，POSIX）
# 与 ace-mcp.cmd 同一口径：目录由脚本位置决定；不传 --project-root 时用 cwd（host 的工作区）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ace-mcp] 找不到 python3。请装 Python 3.10+，或改用已安装的 ACE 冻结版：ace --mcp" >&2
  exit 127
fi

exec python3 "$HERE/ai_code.py" --mcp "$@"
