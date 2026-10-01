#!/bin/sh
# setup-sandbox.sh - install the virtualization base (CubeSandbox) on THIS Linux host.
#
# 本脚本是**薄包装**，不重写上游安装器：
#   · 先跑 preflight.sh（不能跑就直接退出，不让你装到一半才发现）
#   · 从**钉住的 commit** 取上游 one-click 安装器来跑（钉的是安装器本体）
#   · 装完立刻验一次（verify-sandbox.py），并打印挂载侧要填的参数
#
# 用法：
#   sudo bash setup-sandbox.sh                 # 默认：从官方渠道装 latest
#   sudo bash setup-sandbox.sh --url=<bundle>  # 钉住某个 bundle（离线/内网镜像）
#   CUBE_PVM_ENABLE=1 sudo -E bash setup-sandbox.sh   # 无 KVM 的 Linux 云 VM 走 PVM（重）
set -eu

CUBE_REF="c33a8a5efbcf5cac0e26d68467bbac25dcfa8972"   # 钉住：2026-09-23
RAW_BASE="https://raw.githubusercontent.com/TencentCloud/CubeSandbox/${CUBE_REF}"
HERE="$(cd "$(dirname "$0")" && pwd)"
URL_ARG=""

for arg in "$@"; do
  case "$arg" in
    --url=*) URL_ARG="${arg#--url=}" ;;
    *) echo "[setup] 未知参数：$arg（认得 --url=<bundle>）" >&2; exit 2 ;;
  esac
done

echo "== ① 前置检查 =="
if [ "$(id -u)" != "0" ]; then
  echo "[setup] 需要 root（要装 systemd 服务与内核资产）：sudo bash $0 $*" >&2
  exit 2
fi
if [ "${CUBE_PVM_ENABLE:-0}" = "1" ]; then
  echo "[setup] PVM 模式（无 KVM 的自建内核路线）—— 它会替换宿主内核并经 GRUB 生效，属于重活"
else
  set +e
  sh "$HERE/preflight.sh"
  _v=$?
  set -e
  if [ "$_v" -eq 2 ]; then
    echo ""
    echo "[setup] 判定为『这台机器不能当底座』—— 已停下（不装到一半）。"
    echo "        要硬走 PVM：CUBE_PVM_ENABLE=1 sudo -E bash $0"
    echo "        或改形态 B：底座装在别的 Linux 上，本机只挂 MCP。"
    exit 2
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[setup] 没装 docker（上游一键安装需要 docker-ce）。" >&2
  echo "        装法见 https://docs.docker.com/engine/install/  —— 不要用 snap 版（读不了 /usr/local/services）" >&2
  exit 2
fi
case "$(command -v docker)" in
  /snap/*) echo "[setup] 检测到 snap docker，上游明确不支持：sudo snap remove docker" >&2; exit 2 ;;
esac

echo ""
echo "== ② 取上游安装器（钉住 ${CUBE_REF}）=="
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$RAW_BASE/deploy/one-click/online-install.sh" -o "$TMP/online-install.sh"
else
  wget -qO "$TMP/online-install.sh" "$RAW_BASE/deploy/one-click/online-install.sh"
fi
echo "    已获取 $(wc -c < "$TMP/online-install.sh") 字节"

echo ""
echo "== ③ 安装 =="
if [ -n "$URL_ARG" ]; then
  # shellcheck disable=SC2086
  sh "$TMP/online-install.sh" "--url=$URL_ARG"
else
  sh "$TMP/online-install.sh"
fi

echo ""
echo "== ④ 验证底座 =="
if [ -x "$HERE/verify-sandbox.py" ] || [ -f "$HERE/verify-sandbox.py" ]; then
  ACE_SANDBOX_API="${ACE_SANDBOX_API:-http://127.0.0.1:3000}" python3 "$HERE/verify-sandbox.py" || true
fi

cat <<EOF

== ⑤ 挂载侧要填的参数 ==
  单机 one-click 的默认 E2B 入口与演示 key（见上游 deploy/one-click/README.md）：
    ACE_SANDBOX_API=http://$(hostname -I 2>/dev/null | awk '{print $1}'):3000
    ACE_SANDBOX_KEY=e2b_000000
  把它填进用户 agent 的 MCP 配置 env（见本包 README-ALLINONE.md 第 ② 步）。
  生产环境请按上游文档换成自己的 key，不要长期用演示 key。
EOF
