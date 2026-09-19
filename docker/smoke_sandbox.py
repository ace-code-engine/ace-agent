"""CI 冒烟：用**客户端自己的参数构造**真跑一遍沙箱镜像，并断言边界成立。

为什么是仓库里的一个文件，而不是写在工作流的 run: 块里：
    在 YAML 块标量里用 heredoc（`python3 - <<'PY'`）时，heredoc 正文会带着
    它在 YAML 里的缩进一起交给 Python —— 模块级代码带前导空格，直接
    IndentationError。2026-09-19 就是这么失败一次（job 105829105690）。
    YAML 校验器不会报错，本机又没有 CI 日志，于是它躲过了所有本地检查。
    放进文件既躲开这个坑，也能本地跑、能被 review。

用法：
    python3 docker/smoke_sandbox.py                      # 验本地构建的 ace-sandbox:latest
    ACE_SMOKE_IMAGE=ghcr.io/you/ace-sandbox:1 python3 docker/smoke_sandbox.py

CI 上也跑（`.github/workflows/ci.yml` 的 sandbox-smoke job）：先本地构建镜像，
再用这个脚本把它真跑一遍 —— 这样"加固参数被真实 daemon 接受""网络与根文件系统
边界成立"这两件事每次都有人验，而不是只在我本机验过一次。
"""
import os
import sys

# Windows 控制台是 GBK 时，下面的 ✅/❌ 会让 print 抛 UnicodeEncodeError
# （2026-09-19 本机实测）。仓库里几个入口脚本都有这同一段兜底，照抄。
for _s in (sys.stdout, sys.stderr):
    try:
        if _s.encoding and _s.encoding.lower() not in ("utf-8", "utf8"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from tools.docker_sandbox import (DockerSandbox, DockerUnavailable,  # noqa: E402
                                  auto_pull_enabled)

FAILED = []
UNAVAILABLE = False   # 沙箱拿不到时，后面那些断言没有意义：直接失败退出，不刷一屏级联 ❌


def check(name: str, ok: bool, detail="") -> None:
    print("  %s %s%s" % ("✅" if ok else "❌", name,
                         "" if ok else "  -> %s" % detail))
    if not ok:
        FAILED.append(name)


def run(sb: DockerSandbox, command: str) -> dict:
    """跑一条命令；拉取/daemon 失败时返回失败字典而不是抛出去。

    CI 日志里一句 ❌ 比一段 traceback 有用得多 —— 而且脚本存在的意义就是
    把"哪里不成立"说清楚。
    """
    global UNAVAILABLE
    try:
        return sb.run_shell(command)
    except DockerUnavailable as e:
        print("  ❌ 沙箱不可用: %s" % e)
        FAILED.append("沙箱不可用")
        UNAVAILABLE = True
        return {"stdout": "", "stderr": str(e), "returncode": 125,
                "timeout": False, "sandbox_denied": False}


def main() -> int:
    image = os.environ.get("ACE_SMOKE_IMAGE", "ace-sandbox:latest")
    workspace = os.environ.get("ACE_SMOKE_WORKSPACE") or os.getcwd()
    print("image: %s\nworkspace: %s" % (image, workspace))

    sb = DockerSandbox(workspace, image=image, auto_pull=auto_pull_enabled())
    check("docker daemon 可达", sb.probe(), sb.detail)

    # 这一步会走"本地没有 → 拉官方预编译镜像"这条真实路径（CI runner 上是全新的）
    out = run(sb, "python -c \"print('sandbox-ok')\" && echo wrote > /work/smoke.txt")
    print("    rc=%s stdout=%r stderr=%r" % (out["returncode"],
                                             (out["stdout"] or "").strip()[:120],
                                             (out["stderr"] or "").strip()[:200]))
    if UNAVAILABLE:
        print("\nFAIL: 沙箱拿不到（镜像拉不下来或 daemon 不可用），后续断言无意义，直接失败。")
        return 1
    check("加固参数被真实 daemon 接受、命令跑通", out["returncode"] == 0, out)
    check("容器 stdout 正常", "sandbox-ok" in (out["stdout"] or ""), out["stdout"])
    check("工作目录挂载生效（宿主侧能看到容器写的文件）",
          os.path.exists(os.path.join(workspace, "smoke.txt")))

    net = run(sb, "python -c \"import socket;socket.create_connection(('1.1.1.1',53),3)\"")
    check("--network none：容器里没有网络", net["returncode"] != 0, net)

    ro = run(sb, "touch /etc/should-fail")
    check("--read-only：根文件系统写不进", ro["returncode"] != 0, ro)
    check("只读拒绝被识别成 sandbox_denied（不是普通命令失败）",
          bool(ro.get("sandbox_denied")), ro)

    print("digest: %s" % (sb.image_digest or "(未取到 RepoDigest)"))

    if FAILED:
        print("\nFAIL: %d 项未通过 -> %s" % (len(FAILED), FAILED))
        return 1
    print("\nOK: 镜像可用、加固参数被接受、网络与根文件系统边界成立")
    return 0


if __name__ == "__main__":
    sys.exit(main())
