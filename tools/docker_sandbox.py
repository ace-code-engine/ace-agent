"""Docker 一次性容器执行层 —— 把命令执行真正关进内核边界。

## 为什么需要这一层

在这之前，ace 的"沙箱"全部是进程内的 Python 层策略：AST 黑名单、路径包含
检查、危险命令正则。`terminal_exec` 是 `subprocess.run(cmd, shell=True)`，
cwd 固定在项目根 —— 但 `shell=True` 下 `cd /` 或写绝对路径随便走，cwd 不是
边界。tools/file_tools.py 的注释自己承认过这件事：黑名单是止血层，真正的
隔离依赖容器或低权限账户。这个模块就是把那句注释兑现。

## 边界在哪

容器提供的是 Python 层拿不到的东西：

- `--network none`：没有网卡，凭据无法外传，也下载不了第二阶段载荷
- `--memory` / `--memory-swap` / `--pids-limit` / `--ulimit nofile`：fork bomb、内存耗尽、
  句柄耗尽都变成容器自己的事
- `--read-only` + `--tmpfs /tmp`：根文件系统不可写，只有挂进来的工作目录可写
- `--cap-drop ALL` + `--security-opt no-new-privileges`：拿不到额外权能
- `--init`：容器里那个 PID 1 是真 init，命令 fork 出来的僵尸由它回收 —— 否则僵尸会
  一直占着 `--pids-limit` 的名额，表现为"跑到一半突然起不了新进程"
- `--rm`：进程树、临时文件、残留状态随容器一起消失

容器不提供的：内核共享。容器逃逸漏洞仍然是逃逸。要更强的边界得上虚拟机。

## 镜像从哪来（2026-09-19 变更）

以前这里是"镜像故意不发布，部署方自己 build"。现在改成：**本地没有就先拉官方预编译镜像**
（`ghcr.io/ace-code-engine/ace-sandbox`），拉不到再告诉你 build 命令；本地已经 build 过的
镜像永远优先（只有缺失才会去拉）。

改的理由是纯粹的门槛：这个镜像里没有 ACE 的代码，它只是个干净执行环境
（`python:3.12-slim` + 非 root 用户），让每个 Linux/macOS 用户先本地 build 一次 ——
而且 build 还得先能连上 Docker Hub 拉基础镜像 —— 挡掉的人远多于它保护的人。

代价必须说清：信任锚从"你自己构建的那份"变成"官方 CI 构建 + registry 分发的那一份"。
所以这一层做三件事：把实际用到的镜像摘要记进工具结果（`sandbox.image_digest`）、
支持 `--sandbox-image ghcr.io/...@sha256:<digest>` 固定、以及 `ACE_SANDBOX_NO_PULL=1`
直接关掉自动拉取（离线/受控环境用本地 build 那份）。

## 一个刻意的设计：不做静默回退

启用了 docker 沙箱但 docker 不可用时，这里返回失败，**不会**偷偷改回宿主
执行。静默回退比没有沙箱更危险——用户以为命令跑在容器里，实际跑在自己机器
上，而且没有任何提示。宁可报错让人去修 docker。

纯标准库实现（subprocess 调 docker CLI），不引入 docker-py。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_IMAGE = "ace-sandbox:latest"

# 官方预编译沙箱镜像。本地那份（DEFAULT_IMAGE）缺失时拉它、再打上本地名 ——
# 这样老用户的本地 build 仍然优先，新用户不必自己构建。
OFFICIAL_IMAGE = "ghcr.io/ace-code-engine/ace-sandbox:latest"

DEFAULT_TIMEOUT = 30
DEFAULT_MEMORY = "512m"
DEFAULT_CPUS = "1.0"
DEFAULT_PIDS = 128
DEFAULT_TMPFS_SIZE = "64m"
# 句柄上限：给足正常构建用，封住"打开十万个 fd"这一类。
DEFAULT_NOFILE = "4096:4096"
# 拉镜像可以慢（首次几 MB～几十 MB），但必须有界：它挡在一条工具调用前面。
PULL_TIMEOUT = 300

# 沙箱策略拒绝的 stderr 方言（借鉴 DSH sandbox-local DENIAL_SIGNATURES / Codex violation.rs）。
# 语义必须与"命令自身失败"分开：前者是限制在按预期生效（模型应换做法），
# 后者才该当普通失败重试。--read-only 根文件系统 + cap-drop ALL 下，
# 越界写/越界操作会稳定产出这些关键词。
DENIAL_SIGNATURES = (
    "permission denied",
    "read-only file system",
    "read-only file",
    "operation not permitted",
    "cannot create directory: read-only",
    "is a read-only file system",
)

# docker daemon 探测的超时。探测本身要快——它挡在每次工具调用前面，
# 不能因为 daemon 卡住就让整个 agent 跟着卡 30 秒。
PROBE_TIMEOUT = 8


class DockerUnavailable(RuntimeError):
    """docker CLI 缺失或 daemon 不可达。调用方应把它变成明确的错误码，不要回退宿主。"""


class DockerSandbox:
    """把单条命令 / 单段代码丢进一次性容器执行。

    workspace 是唯一挂进容器的宿主路径（挂到 /work，容器内 cwd）。
    项目目录之外的东西容器里看不见——这是"隔离"的字面含义。
    """

    def __init__(self, workspace: str, image: str = DEFAULT_IMAGE,
                 timeout: int = DEFAULT_TIMEOUT, memory: str = DEFAULT_MEMORY,
                 cpus: str = DEFAULT_CPUS, pids_limit: int = DEFAULT_PIDS,
                 network: str = "none", auto_pull: bool = True,
                 seccomp: str = "") -> None:
        self.workspace = Path(workspace).resolve()
        self.image = image
        self.timeout = int(timeout)
        self.memory = memory
        self.cpus = cpus
        self.pids_limit = int(pids_limit)
        self.network = network
        self.auto_pull = bool(auto_pull)
        # 自定义 seccomp 配置路径。默认空 = 用 docker 的内置默认 profile
        # （它本来就挡掉约 44 个系统调用）。这里不随缘自带一份：改 seccomp 很容易
        # 连带封掉 clone3/新 glibc 这类正常路径，而"沙箱能用"和"沙箱更严"之间
        # 不该由一份没人能验证的 profile 决定 —— 想更严的人自己指定。
        self.seccomp = str(seccomp or "")
        self._available: Optional[bool] = None   # 探测结果缓存
        self._image_ok: Optional[bool] = None    # 镜像存在性缓存（与探测同理，挡在每条命令前）
        self._detail = ""
        self._pull_error = ""                    # 最近一次拉取失败的原因（进 503 文案）
        self._digest = ""                        # 实际使用的镜像摘要（best-effort）


    # ---------- 可用性 ----------

    def probe(self, force: bool = False) -> bool:
        """docker CLI 在 PATH 且 daemon 应答。结果缓存，避免每条命令都探一次。"""
        if self._available is not None and not force:
            return self._available
        if not shutil.which("docker"):
            self._available, self._detail = False, "PATH 里没有 docker 命令"
            return False
        try:
            r = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=PROBE_TIMEOUT,
                stdin=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired, OSError) as e:
            self._available, self._detail = False, f"docker 探测失败: {e}"
            return False
        if r.returncode != 0:
            # 最典型的情况：Docker Desktop 没启动，daemon 连不上
            self._available = False
            self._detail = (r.stderr or r.stdout or "").strip()[:200] or "daemon 不可达"
            return False
        self._available, self._detail = True, f"docker server {r.stdout.strip()}"
        return True

    @property
    def detail(self) -> str:
        """最近一次探测的说明，用于把失败原因原样告诉用户。"""
        return self._detail

    def image_present(self, force: bool = False) -> bool:
        """沙箱镜像在本地。结果缓存，理由和 probe 一样：它挡在每条命令前面。"""
        if self._image_ok is not None and not force:
            return self._image_ok
        try:
            r = subprocess.run(["docker", "image", "inspect", self.image],
                               capture_output=True, text=True,
                               timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL)
            self._image_ok = (r.returncode == 0)
        except (subprocess.TimeoutExpired, OSError):
            self._image_ok = False
        return self._image_ok

    def _ensure_ready(self) -> None:
        """跑之前把"能不能跑"问清楚，不能跑就抛 DockerUnavailable（调用方会转成 503）。

        镜像缺失单独判一次，而不是让 `docker run` 自己去撞，原因是撞出来的错不对：
        本地找不到 `ace-sandbox:latest` 时 docker 会先当它是远端镜像去 registry 拉，
        于是用户等一个网络超时，然后拿到一句 "pull access denied / not found" ——
        听起来像是仓库配错了或者要登录。

        缺失时的正确动作是**去把官方预编译镜像拉下来**（见 _try_acquire）；只有当拉取
        本身失败时，才把 build 命令作为退路一并给出来。本地已经 build 过的镜像永远优先：
        只有 image_present() 为假才会走到拉取这一步。
        """
        if not self.probe():
            raise DockerUnavailable(self._detail)
        if self.image_present():
            return
        if self.auto_pull and self._try_acquire():
            return
        _why = f"\n    拉取失败: {self._pull_error}" if self._pull_error else ""
        _off = ("" if self.auto_pull
                else "\n    自动拉取已关闭（ACE_SANDBOX_NO_PULL=1）。")
        raise DockerUnavailable(
            f"本地没有沙箱镜像 {self.image}，自动拉取也没成功。{_why}{_off}\n"
            f"    自己构建: docker build -t {self.image} -f docker/Dockerfile.sandbox .\n"
            f"    或指定官方镜像: --sandbox-image {OFFICIAL_IMAGE}\n"
            "    要固定供应链就把镜像写成 <ref>@sha256:<digest>；不想要容器边界就用 --sandbox off。")

    # ---------- 镜像获取 ----------

    @staticmethod
    def is_registry_ref(image: str) -> bool:
        """判断镜像名是否指向 registry（即可 pull 的远端引用）。

        规则照 docker 自己的来：名字的第一段含 `.` 或 `:`，或等于 `localhost`，
        才被当 registry 主机。`ace-sandbox:latest` 的第一段是 `ace-sandbox`，
        没有点也没有冒号 —— 那在 docker 眼里是 Docker Hub 的 library 镜像名，
        不是我们要拉的东西，所以这里必须判成"本地名"。
        """
        first = image.split("/", 1)[0] if "/" in image else ""
        if not first:
            return False
        return "." in first or ":" in first or first == "localhost"

    @staticmethod
    def selinux_enforcing() -> bool:
        """宿主机 SELinux 是否处于 Enforcing。

        为什么要问：Fedora / RHEL / CentOS 默认 Enforcing，此时**容器写不进挂载进来的
        工作目录**（`docker run -v $PWD:/work` 会被 SELinux 拒），报错是 "Permission denied"，
        看起来像沙箱坏了。docker 的标准解法是给挂载点加 `,z`（共享标签）。
        只在 Linux 且 `getenforce` 存在且输出 Enforcing 时才为真 ——
        macOS / Windows 上 getenforce 不存在，永远走不到这条分支。
        """
        if not sys.platform.startswith("linux"):
            return False
        if not shutil.which("getenforce"):
            return False
        try:
            r = subprocess.run(["getenforce"], capture_output=True, text=True,
                               timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired, OSError):
            return False
        return r.stdout.strip().lower() == "enforcing"

    def _docker_pull(self, ref: str) -> Tuple[bool, str]:
        try:
            r = subprocess.run(["docker", "pull", ref], capture_output=True, text=True,
                               timeout=PULL_TIMEOUT, stdin=subprocess.DEVNULL,
                               encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"{type(e).__name__}: {e}"
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "").strip()[:300] or "docker pull 返回非零"
        return True, ""

    def _docker_tag(self, src: str, dst: str) -> Tuple[bool, str]:
        try:
            r = subprocess.run(["docker", "tag", src, dst], capture_output=True, text=True,
                               timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL,
                               encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"{type(e).__name__}: {e}"
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "").strip()[:300] or "docker tag 返回非零"
        return True, ""

    def _image_digest(self) -> str:
        """取本地镜像的摘要（best-effort）。取不到就空串，绝不因此让执行失败。"""
        try:
            r = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", self.image],
                capture_output=True, text=True, timeout=PROBE_TIMEOUT,
                stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError):
            return ""
        return (r.stdout or "").strip() if r.returncode == 0 else ""

    def _try_acquire(self) -> bool:
        """镜像不在本地时把它弄到手。成功返回 True 并置 _image_ok。

        两种情形：
          - 配置的是 registry 引用（`ghcr.io/...`、`myreg:5000/...`）→ 直接拉它；
          - 配置的是本地名（默认 `ace-sandbox:latest`）→ 拉官方预编译镜像，再打上这个名字。
            打名字而不是改 self.image，是为了让状态在 `docker images` 里看得见、
            且后续运行不再需要网络。
        """
        target = self.image
        ref = target if self.is_registry_ref(target) else OFFICIAL_IMAGE
        ok, err = self._docker_pull(ref)
        if not ok:
            self._pull_error = f"{ref}: {err}"
            return False
        if ref != target:
            ok, err = self._docker_tag(ref, target)
            if not ok:
                self._pull_error = f"docker tag {ref} -> {target}: {err}"
                return False
        self._image_ok = True
        self._digest = self._image_digest()
        return True

    @property
    def image_digest(self) -> str:
        """实际使用的镜像摘要（形如 `ghcr.io/x/y@sha256:...`）；未知时为空串。"""
        return self._digest

    # ---------- 执行 ----------

    def _bind_suffix(self) -> str:
        """挂载点的额外选项：SELinux Enforcing 的宿主机上必须带 `,z`。

        不加时，Fedora / RHEL 这类默认 Enforcing 的机器上容器**写不进**挂进来的工作目录，
        报错是一句笼统的 "Permission denied"，看起来像沙箱坏了。`,z` 是 docker 的标准解法
        （给内容打共享标签）。只在实测 Enforcing 时才加 —— macOS / Windows 上
        `getenforce` 根本不存在，不受影响。
        """
        return ",z" if self.selinux_enforcing() else ""

    def _base_args(self, name: str) -> List[str]:
        args = [
            "docker", "run", "--rm", "-i",
            "--name", name,
            # 标签让超时残留的容器能被一条命令收干净：
            #   docker container prune --filter label=ace.sandbox=1
            "--label", "ace.sandbox=1",
            # 真 init 回收僵尸进程。没有它时，命令 fork 出来的僵尸会一直占着
            # --pids-limit 的名额，表现为"跑到一半突然起不了新进程"。
            "--init",
            f"--network={self.network}",
            f"--memory={self.memory}",
            # memory-swap 等于 memory 才算真的封住内存：否则超额部分会换到 swap
            f"--memory-swap={self.memory}",
            f"--cpus={self.cpus}",
            f"--pids-limit={self.pids_limit}",
            "--ulimit", f"nofile={DEFAULT_NOFILE}",
            "--read-only",
            f"--tmpfs=/tmp:rw,nosuid,nodev,size={DEFAULT_TMPFS_SIZE}",
            # 根文件系统只读，$HOME 落在只读层上会让 pip 之类写缓存的工具直接失败，
            # 而 /tmp 已经是可写 tmpfs。沙箱里没有"用户家目录"这个概念，指过去即可。
            "-e", "HOME=/tmp",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "-v", f"{self.workspace}:/work:rw{self._bind_suffix()}",
            "-w", "/work",
        ]
        if self.seccomp:
            args += ["--security-opt", f"seccomp={self.seccomp}"]
        # POSIX 上用调用者的 uid/gid，容器写出来的文件在宿主侧归属正确，
        # 不会留下一堆 root 拥有的产物。Windows 上没有 uid 概念，
        # 交给镜像里的 USER（见 docker/Dockerfile.sandbox）。
        if os.name != "nt" and hasattr(os, "getuid"):
            args += ["-u", f"{os.getuid()}:{os.getgid()}"]
        return args

    def _run(self, args: List[str], name: str,
             stdin_data: Optional[str] = None) -> Dict:
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, timeout=self.timeout,
                input=stdin_data if stdin_data is not None else "",
                encoding="utf-8", errors="replace")
            stderr = r.stderr or ""
            denied = any(sig in stderr.lower() for sig in DENIAL_SIGNATURES)
            return {"stdout": r.stdout, "stderr": stderr,
                    "returncode": r.returncode, "timeout": False,
                    "sandbox_denied": denied}
        except subprocess.TimeoutExpired:
            # subprocess 超时只杀掉 docker 客户端，容器还在跑。必须显式清掉，
            # 否则超时一次就漏一个吃着 CPU 的容器。
            self._force_remove(name)
            return {"stdout": "", "stderr": f"容器执行超时（{self.timeout} 秒），已强制清理",
                    "returncode": 124, "timeout": True, "sandbox_denied": False}

    @staticmethod
    def _force_remove(name: str) -> None:
        try:
            subprocess.run(["docker", "rm", "-f", name],
                           capture_output=True, timeout=PROBE_TIMEOUT,
                           stdin=subprocess.DEVNULL)
        except (subprocess.TimeoutExpired, OSError):
            pass

    def run_shell(self, command: str) -> Dict:
        """在容器里跑一条 shell 命令。命令原文经 argv 传给 sh -c，不经宿主 shell。"""
        self._ensure_ready()
        name = f"ace-sbx-{uuid.uuid4().hex[:10]}"
        args = self._base_args(name) + [self.image, "sh", "-c", command]
        return self._run(args, name)

    def run_python(self, code: str) -> Dict:
        """在容器里跑一段 Python。代码经 stdin 喂给 `python -`，不落宿主磁盘。"""
        self._ensure_ready()
        name = f"ace-sbx-{uuid.uuid4().hex[:10]}"
        args = self._base_args(name) + [
            "-e", "PYTHONIOENCODING=utf-8",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            self.image, "python", "-",
        ]
        return self._run(args, name, stdin_data=code)


def auto_pull_enabled() -> bool:
    """镜像缺失时是否自动去拉官方预编译镜像。默认开。

    `ACE_SANDBOX_NO_PULL=1` 关掉 —— 离线环境、或者"只用我自己构建的那份镜像"
    的受控部署该关掉它。关掉后镜像缺失会直接报错并给出 build 命令。
    """
    return os.environ.get("ACE_SANDBOX_NO_PULL", "").strip().lower() not in (
        "1", "true", "yes", "on")


def build_sandbox(config: Optional[Dict], workspace: str) -> Optional[DockerSandbox]:
    """按配置造沙箱；未启用返回 None。

    config 形如 {"mode": "docker", "image": ..., "timeout": ..., "auto_pull": ..., "seccomp": ...}。
    mode 不是 "docker" 就当没启用——保持默认关闭，不给现有用户变行为。

    未显式给出的两项看环境变量：`ACE_SANDBOX_NO_PULL=1` 关自动拉取，
    `ACE_SANDBOX_IMAGE` / `ACE_SANDBOX_SECCOMP` 指定镜像与 seccomp profile。
    """
    cfg = config or {}
    if str(cfg.get("mode", "off")).lower() != "docker":
        return None
    _pull = cfg.get("auto_pull")
    return DockerSandbox(
        workspace=workspace,
        image=cfg.get("image") or os.environ.get("ACE_SANDBOX_IMAGE") or DEFAULT_IMAGE,
        timeout=int(cfg.get("timeout") or DEFAULT_TIMEOUT),
        memory=cfg.get("memory") or DEFAULT_MEMORY,
        cpus=str(cfg.get("cpus") or DEFAULT_CPUS),
        pids_limit=int(cfg.get("pids_limit") or DEFAULT_PIDS),
        network=cfg.get("network") or "none",
        auto_pull=auto_pull_enabled() if _pull is None else bool(_pull),
        seccomp=cfg.get("seccomp") or os.environ.get("ACE_SANDBOX_SECCOMP", ""),
    )
