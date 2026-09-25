# v3.11.0 · 更新介绍

> 这一版是**容器档（Linux / macOS）**的一轮加固，外加一次**没做成**的发布尝试 —— 两件都写在这里。
> 逐条变更见 [`CHANGELOG.md`](../CHANGELOG.md#v3110-2026-09-19)；容器用法见 [`docker/README-Docker.md`](../docker/README-Docker.md) 与 [`docs/SECURITY-MODEL.md`](SECURITY-MODEL.md)。

---

## English (short)

**v3.11.0 — the container tier got hardened, and this time it is verified by running it.**

- `--sandbox docker` run flags hardened: `--init` (reap zombies, or they eat the `--pids-limit` budget), `--ulimit nofile`, `HOME=/tmp` (pip can't write cache under a read-only root), automatic `,z` on SELinux-enforcing hosts (Fedora/RHEL otherwise can't write the mount), `--label` for cleanup, optional `ACE_SANDBOX_SECCOMP`.
- Those flags are now **verified against a real daemon**, not by reading code: a new `sandbox-smoke` CI job builds the image and runs it through the client's own argument construction, asserting that `--network none` really has no network and `--read-only` really cannot write `/etc`.
- **No official prebuilt image.** We tried — multi-arch GHCR builds with provenance and SBOM, and the images did get pushed — but the organization's package policy forbids making packages public (`Setting is disabled by organization administrators`), so anonymous `docker pull` fails. An "auto-pull that cannot pull" default would only make every new user wait for a timeout and then see a permission error, so the default is back to **build the image once locally**; `ACE_SANDBOX_PULL=1` stays as an opt-in for your own registry.
- Nothing is breaking, no config changes are required.

---

## 中文（详细）

### 一、容器档的运行参数加固

`--sandbox docker` 原本已经有一套还行的参数（`--network none` / `--read-only` / `--cap-drop ALL` / `no-new-privileges` / 内存与 pid 上限 / 只挂工作目录）。这一版按"每条对应一类具体威胁"又补了五项：

| 新增 | 挡的是什么 |
|---|---|
| `--init` | 容器里的 PID 1 是真 init，回收僵尸进程。没有它时僵尸会一直占着 `--pids-limit` 的名额，表现为"跑到一半突然起不了新进程"——这种故障最难查，因为它看起来像资源不够 |
| `--ulimit nofile=4096:4096` | 封住句柄耗尽 |
| `-e HOME=/tmp` | 根文件系统只读时 `$HOME` 落在只读层上，pip 之类写缓存的工具会直接失败（`/tmp` 本就是可写 tmpfs） |
| 挂载点自动加 `,z` | Fedora / RHEL 默认 SELinux Enforcing，不加 `,z` 时容器**写不进**工作目录，报错只有一句笼统的 `Permission denied`，看起来像沙箱坏了。只在实测 Enforcing 时才加 —— macOS / Windows 上 `getenforce` 根本不存在，不受影响 |
| `--label ace.sandbox=1` | 超时残留的容器能被一条命令收干净：`docker container prune --filter label=ace.sandbox=1` |

另加一个可选开关 `ACE_SANDBOX_SECCOMP=<profile.json>`：想更严就挂自己的 seccomp 配置。默认仍用 docker 内置 profile（本就挡掉约 44 个系统调用）——项目刻意**不**随缘自带一份，因为改 seccomp 很容易连带封掉 `clone3` 这类正常路径，这种取舍该由部署方做。

### 二、这次是"跑过"，不是"读代码觉得没问题"

这句话是这一版真正的重点。上面那些参数，在此之前的验证方式是**读代码**；而"容器参数会不会被 daemon 拒绝""边界是不是真的成立"，读代码是答不出来的。

现在有三层证据：

1. **CI 每次提交都跑**：`ci.yml` 新增 `sandbox-smoke` job —— 本地构建沙箱镜像，再用**客户端自己的参数构造**把命令真跑一遍：

   ```
   [ok] Sandbox smoke (build image + run through DockerSandbox)
        step: Build the sandbox image locally     success
        step: Run through DockerSandbox           success
   ```

2. **脚本本身就是断言**（`docker/smoke_sandbox.py`），它验 7 件事：daemon 可达、加固参数被接受且命令跑通、容器 stdout 正常、工作目录挂载生效（宿主侧能看到容器写的文件）、`--network none` 下确实连不出去、`--read-only` 下确实写不进 `/etc`、只读拒绝被正确识别成 `sandbox_denied`（而不是当成普通命令失败让模型重试）。

3. **本机真机验过一次**（Docker Desktop 29.7.2 / linux 容器），7 项全绿，并打印出实际使用的镜像摘要。

顺带记录：这个脚本自己踩了两个坑，都修在文件里并留了注释 —— ① 把它写成工作流里的 heredoc 时，YAML 缩进会一起进 Python（`IndentationError`），所以脚本必须放仓库里；② 在 GBK 控制台下打印 ✅/❌ 会 `UnicodeEncodeError`，仓库几个入口脚本早有 stdio 兜底。

### 三、一次没做成的发布（如实记录）

原本这一版的主题是"给 Linux / macOS 用户提供预编译容器镜像，不必自己 build"。做完了：工作流写好了（多架构 `linux/amd64` + `linux/arm64`、provenance、SBOM、以及一个真跑镜像的 smoke），镜像也确实推进了 GHCR。

**但它不成立**：组织的包策略不允许把包设为公开（GitHub 对话框原话：`Setting is disabled by organization administrators`），匿名 `docker pull` 会被要求登录。一个"默认去拉、但拉不到"的默认行为，只会让每个新用户先等一次网络超时、再看到一个权限错误 —— 比"直接告诉你 build 一次"更糟。

所以这一版**撤回发布、默认回到本地构建**：

```bash
docker build -t ace-sandbox:latest -f docker/Dockerfile.sandbox .   # 一次即可
python ai_code.py --sandbox docker
```

镜像缺失时不会去 registry 撞超时，而是把上面那条 build 命令直接给你。拉取机制保留（`ACE_SANDBOX_PULL=1`，适用于自建 registry / 私有 GHCR），本地已有的镜像永远优先。

### 四、升级注意

- **不需要改配置。** 默认行为与 v3.10.x 一致：镜像自己构建一次
- 新增可选开关：`ACE_SANDBOX_PULL=1`（自建 registry 自动拉）、`ACE_SANDBOX_SECCOMP=<path>`（自定义 seccomp）
- 工具结果里会带 `sandbox.image_digest` —— 这次到底跑在哪一份镜像上，可追溯；要固定供应链就把镜像写成 `<ref>@sha256:<digest>`
- Windows 的 `--sandbox job` 那条线不受本版影响（v3.10.1 已重发过预编译执行器产物）
- 已知未验证项照旧写在 README 的 [Known gaps and unverified items](../README.md#done-and-still-unverified)

### 五、版本线（最近三个）

| 版本 | 一句话 |
|---|---|
| **v3.11.0** | 容器档运行参数加固 + 可选镜像拉取；发布预编译镜像这条路暂时搁置（组织策略不允许公开包） |
| v3.10.1 | 协议纠错死锁（错误回喂不再套外部内容块）/ 执行器 Tier-1 在受限令牌宿主下可降级生效 / `ace.cmd` 改 CRLF |
| v3.10.0 | 根目录瘦身（`ui/` `cli/` `core/`）+ README 英文为主 + "被拦下"演示 |
