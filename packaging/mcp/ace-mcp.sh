#!/bin/sh
# HooH MCP launcher (non-intrusive attach pack, POSIX)
# Same contract as ace-mcp.cmd: directory comes from the script location, and
# with no --project-root the cwd (the host's workspace) is used.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# Three layouts, best first. The frozen build is the one that works on a machine
# with no Python, so it wins whenever it is present.
if [ -x "$HERE/hooh-mcp" ]; then
  exec "$HERE/hooh-mcp" "$@"
fi
if [ -x "$HERE/frozen/hooh-mcp/hooh-mcp" ]; then
  exec "$HERE/frozen/hooh-mcp/hooh-mcp" "$@"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[hooh-mcp] no hooh-mcp binary here and no python3 on PATH." >&2
  echo "[hooh-mcp] Get the self-contained build (hooh-mcp-<version>-linux-amd64.zip" >&2
  echo "[hooh-mcp] or -macos-arm64.zip), or install Python 3.10+ for the source pack." >&2
  exit 127
fi

exec python3 "$HERE/ai_code.py" --mcp "$@"
