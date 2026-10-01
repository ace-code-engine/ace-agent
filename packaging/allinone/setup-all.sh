#!/bin/sh
# setup-all.sh - POSIX one command: base verdict (+ optional base install) and the MCP block to paste.
#
#   bash setup-all.sh                       # 只判定 + 打印要粘的配置
#   sudo bash setup-all.sh --with-base      # 顺带装底座（要先通过 preflight）
#   bash setup-all.sh --sandbox-api http://10.0.0.5:3000
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
WITH_BASE=0
SBX_API="${ACE_SANDBOX_API:-}"
SBX_KEY="${ACE_SANDBOX_KEY:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --with-base) WITH_BASE=1 ;;
    --sandbox-api) shift; SBX_API="${1:-}" ;;
    --sandbox-key) shift; SBX_KEY="${1:-}" ;;
    *) echo "[setup-all] 未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

echo "== ① 底座判定（这台机器能不能当底座）=="
set +e
sudo -n true 2>/dev/null || true
sh "$HERE/sandbox/preflight.sh"
VERDICT=$?
set -e

if [ "$WITH_BASE" = "1" ]; then
  echo ""
  if [ "$VERDICT" -eq 2 ]; then
    echo "[setup-all] preflight 判定不能装 —— 已停下。要硬走 PVM：CUBE_PVM_ENABLE=1 sudo -E bash sandbox/setup-sandbox.sh"
    exit 2
  fi
  echo "== ② 安装底座 =="
  # 需要 root：这里显式检查，避免在用户 shell 里静默失败
  if [ "$(id -u)" != "0" ]; then
    echo "[setup-all] --with-base 需要 root：sudo bash $0 --with-base" >&2
    exit 2
  fi
  sh "$HERE/sandbox/setup-sandbox.sh"
fi

echo ""
echo "== ③ 把这一段合进你 host 的 MCP 配置 =="
if [ -z "$SBX_API" ]; then
  SBX_API="http://<底座地址>:3000"
  echo "（没给 --sandbox-api：先按占位符填；ace_sandbox_exec 在底座可达前会一律拒绝，这是设计行为）"
fi
cat <<EOF
{
  "mcpServers": {
    "ace": {
      "command": "$HERE/ace-mcp.sh",
      "args": [],
      "env": {
        "ACE_SANDBOX_API": "$SBX_API"$([ -n "$SBX_KEY" ] && printf ',\n        "ACE_SANDBOX_KEY": "%s"' "$SBX_KEY")
      }
    }
  }
}
EOF
echo ""
echo "== ④ 验 =="
echo "  python3 $HERE/verify-mcp.py"
echo "  python3 $HERE/sandbox/verify-sandbox.py"
