# 安全模型（Security Model）

> 本文档由 README「安全模型」一节拆分而来（docs/design/README-RESTRUCTURE.md，v3.7），内容与当时 README 保持一致。
> README 入口见「安全设计」；漏洞报告流程见仓库根 [SECURITY.md](../SECURITY.md)；历史安全审计见 [SECURITY-AUDIT.md](SECURITY-AUDIT.md)。

配置优先级：命令行参数 > `~/.ai_code.json` > `~/.claude/settings.json` > 环境变量。

**权限与授权**

- 默认 `readonly`；写工具需显式 `/permission write` 或 `--permission write`
- 授权两档：「本次」用后即焚，「本会话」本会话内不再询问
- `terminal_exec` 强制逐次确认，不接受会话级授权
- **外发工具**（`api_get` / `api_post` / `browser_open` / `browser_navigate` / `notify_send`）在目的地不在白名单内时逐次确认，同样不接受会话级授权——会话级授权是按工具名给的，不区分目的地，"本会话 api_post 免问"等于把出口整个打开
- **`never` 必须配真边界（启动即拒绝）**：`approval_policy=never`（从不问人）+ `sandbox=off`（没有内核边界）会被**直接拒绝启动**，`never` + `sandbox_policy=danger_full_access` 同理——ADR-002 原话是"无人值守叠加无隔离等于完全没有边界，这个组合不存在合理用途"。注意 `never` 本身不会让危险动作变多（判定为需审批的一律拒绝），它的问题是挡不住**不需要审批**的那批工具；CLI 退出码 2，库调用方会在 `ExecutionLayer(...)` 构造时拿到 `PolicyRefused`
- 非交互模式（非 tty）下一切授权请求与计划审批都 fail-close 拒绝

**执行隔离**

- `terminal_view`：白名单只读命令，内建实现不经 shell，拦 shell 元字符，版本参数严格校验
- `code_execute`：AST 拦危险模块（os/subprocess/socket/pickle/importlib…）与内建逃逸链（`__builtins__`/`__class__`）、`open` 全禁 → 环境变量清洗 → 临时目录 + 30s 超时
- `math_calc`：白名单 AST 求值，仅纯算术，幂运算限 100^1000，杜绝 eval 逃逸与指数 DoS

**路径边界**

- 文件工具默认限制在项目目录内（`confine_files`，含跨盘符检查）；`grep`/`glob` 无条件限项目内，只读检索也不放开项目外
- 读越界按"泄露什么"分档：**读文件内容一律限项目内**（`cat`/`type`、外部命令路径参数、`file_read` 均 403）；**列目录名单允许越界**（`ls`/`dir`）。前者泄露的是凭据本身，后者只是文件名
- 敏感目标硬拦截：绝对路径写入放行（"放到桌面"）但不含凭据与自启动入口（`~/.ssh`、`~/.bashrc`、`~/.ai_code.json`、`.pem`/`.key` 等）
- **项目外"已存在的东西"要问人**（v3.8 补）：绝对路径本身是"用户明确意图"——往桌面丢个**新**文件不问；但**覆盖或删除项目外已经在那儿的文件**会逐次确认，因为项目外没有快照可回滚，一次误写是永久的。确认按**路径**授权：会话级批准只记住那一条路径，换个文件还要问；命中敏感目标（凭据/私钥等）则直接 403，不给你一个"点了也没用"的确认框

**回滚与网络**

- 写入前自动快照，快照元信息可用 `signing_key` 做 HMAC-SHA256 签名；快照数量有硬上限，自动清理最旧
- `.guardian/` 快照目录对所有工具只读且不可写删——它就在 Agent 可写的项目目录里，不挡住的话改一行 `meta.json` 就能让熔断回滚静默失效；回滚失败会告警而不是静默吞掉
- 同理，**Agent 自己的运行与审计状态**也纳入敏感目标：`.ace_sessions/`（会话事件日志）、`.agent_flywheel/`（SFT 样本）、`.poc_reports/`、`.ace_goals.json`（目标）、`.agent_memory.json`（记忆）文件工具一律写不进、删不掉——让被审计方自己可写的记录等于没有记录；要动它们只剩 `terminal_exec`，而那一步每次都过人
- 回滚是**逐项容错**的：删除、恢复、校验三个阶段单个文件失败（Windows 上被编辑器/杀软占用很常见）不会让其余文件停在"已删除、未恢复"，失败项逐条列出并保留删除前的备份供人工恢复，返回失败而不是抛异常
- 守门分层：block 级拦截并回滚本轮快照，warn 级不阻断；只回滚本轮，不动无关修改
- `api_get`/`api_post` 仅 http/https，且 **DNS 解析后**拦截内网 / 回环 / 链路本地地址（防 SSRF）；未实现的工具返回 501 而非假成功

**外发闸门（谁能把数据带出去）**

白名单（`egress_allowlist`）回答的是"能不能去这个站点"，默认**关闭**；关闭时谁都能收，所以默认档还需要另一道：

| 目的地 | 没配 `egress_allowlist` | 配了 |
|---|---|---|
| 内置端点（搜索 / 图片服务等） | 直接放行 | 直接放行（清单是**并集**，不是覆盖） |
| 用户在清单里写了 | —— | 直接放行（等于一次性授权） |
| 其他任何域名 | **逐次确认**：弹给用户看"发往哪个主机、发的是什么 URL" | **403**，文案告诉模型"重试同一个地址不会变，只有人能把域名加进清单" |

- 判定点在执行层（`_stage_permission` 的 `_egress_confirm_reason`），工具自己也会再过一次——两道都对同一个目的地判定，工具内那次负责在 DNS 解析前掐断。
- 确认被拒后**不许模型"换个工具再试"**：指令里明写不许重复调用、不许绕过，且不许它自己去改白名单（那是人的动作）。
- `notify_send` 按渠道判：`console`/`file`/`toast` 不出本机不问，`email` 的收件人由模型给 → 每次问。
- `image_generate` 的目的地是固定的内置图片服务（不是模型挑的），所以不问；但 **prompt 明文交给第三方**，别让它写不该出去的内容。
- 这几条与 `terminal_exec` 同源：黑名单/清单枚举不完，最终防线是"人看一眼这次到底要发什么"。

**安全事件分级与告警（SEC-017）**

403 里面有两类完全不同的东西：**执行层主动防御**（路径越界 / 白名单 / 沙盒拦截 / 敏感目标）与**模型把参数写错了**。混在一条失败路径里，事后既没法按安全事件检索，也没人被告知"有人在试"。

- 前者单独计数、单独写事件日志（`security/denied`，`/audit` 里带 `⚠` 前缀与累计次数）。
- **到阈值（默认 3 次）就向用户告警**，中英日三语：次数、最近一次是哪个工具、涉及了哪些工具，以及"如果这不是你让它做的，可能有东西在借被读取的文件/网页注入指令——先停下核对来源，或直接结束会话"。这不是静默计数器，审计的原始建议就是"要告警"。
- 阈值按**会话累计**而非严格连续：中间夹一次成功调用不该把试探清零（与熔断计数同一取法）。越过阈值后每 +5 次再提醒一次，不做成刷屏。
- 同时把"已向用户告警"写回给模型的 instruction——让它知道人已经知情，而不是继续换路径试。

**无人值守 / 自动化部署（CI、批处理、定时任务）**

非交互（管道 / CI / 无 tty）下的真实行为**与直觉相反**，所以结论先说：**需要审批的动作会被直接拒绝，而不需要审批的写/执行工具照跑。**

- 所有审批入口（计划审批、临时授权、逐次确认、外发确认、项目外覆盖确认）在非 tty 下统一 **fail-close 拒绝**（`ask_yes_no` / `ask_grant` 是唯一入口）。所以 `terminal_exec`、`api_post` 到未授权域名、覆盖项目外已有文件，**在 CI 里根本走不通**——不是"没人看着所以危险"，是"没人在就拒绝"。
- 真正跑得动的是**不需要审批**的那一批：`file_write` / `file_delete` / `code_execute` / `db_write` / `api_post`（清单内）……它们只受进程内策略（AST、路径闸门、出站清单、写前快照）约束。**这就是"止血层"在无人值守下的真实暴露面**：要担心的不是 `terminal_exec`，是这些。
- 想跑无人值守就给真边界，并显式选择审批策略：`--sandbox job`（Windows Job Object）或 `--sandbox docker`，配 `--approval-policy on_failure`（"先试后问"：判定为需审批的命令交给边界执行，沙箱拦下才升级给人）。边界拿不到就 503，**依然不静默回退**。
- **反过来的组合会被拒绝启动**：`approval_policy=never` + `sandbox=off`（或 `danger_full_access`）直接退出码 2——"没人 + 没边界"没有可辩护的用途（ADR-002）。想做无人值守请走上一行，而不是把审批关掉凑合。
- 启动时**主动提示**风险组合（非交互 + `off` 档 + 非只读）：提示就打在终端里，不藏在文档里。判定函数 `execution_layer.unattended_without_boundary()` 是纯函数，有断言覆盖。
- 最小权限原则在这里最值钱：低权限账户 + `readonly` 起步 + `egress_allowlist` 只放必要域名 + `signing_key` 放项目外。

**静态检测的边界（AST / 黑名单 / 正则）**

`code_execute` 的引用级 AST 拦截、`execpolicy` 的命令三值判定、出站清单与逐跳复检都是**静态/模式层**：它们抬高攻击成本、挡住已知形态、让"未知一律拦"，但**枚举不完**（审计报告自己反复强调这一点）。所以：

- 不要把"这次没被拦下"读成"安全"；真正的边界是 `--sandbox job/docker` 与低权限账户。
- 复杂或多步拼装的恶意行为（分多次调用拼装、借合法工具的语义绕过）不在静态检测射程内——这是设计边界，不是漏检。
- 判定的分层关系见 [`docs/ADR-002-executor-boundary.md`](ADR-002-executor-boundary.md)：宿主判一次、Go 执行器再复检一次，但两次都是**策略**，边界仍在 OS/容器。

**联网搜索双通道（免 key 爬虫主通道 + 可选第三方搜索 API）**

- 默认**不需要任何 key**：`search` / `search_read` 走免 key 爬虫——Bing RSS → DuckDuckGo 兜底，结果页正文用 `_page_text` 去噪抽取，不依赖模型 API key，也不依赖任何第三方服务 key
- 可选 **API-key 通道**（结果更准、带官方摘要）：一旦配置就自动成为首选，失败自动回退上面的爬虫：

  ```bash
  set ACE_SEARCH_API_KEY=你的key        # 或写进 ~/.ai_code.json 的 search_api_key
  set ACE_SEARCH_API_PROVIDER=bocha     # 参考实现: 博查 Web Search（api.bocha.cn，有免费额度）
  # provider=custom 时另配端点: set ACE_SEARCH_API_URL=https://你的端点
  ```

- API 通道任何失败（key 没配 / 无效 / 超时 / 连不上 / 返回 0 条）都会**自动回退免 key 爬虫**，结果里带 `route` / `api_fallback` / `api_reason` 如实标注给模型和人看，绝不报错糊弄或假装 API 成功

**容器隔离（`--sandbox docker`）**

上面所有校验都是进程内的 Python 逻辑。`terminal_exec` 是 `shell=True`，cwd 固定在项目根挡不住 `cd /`；`code_execute` 的 AST 黑名单也不可能枚举完。真正的边界要靠内核 —— Linux 与 macOS（Docker Desktop）上一条命令就够：

```bash
python ai_code.py --sandbox docker           # 镜像缺失时自动拉官方预编译镜像
```

开启后 `terminal_exec` / `code_execute` 的每次调用都是一个一次性容器：`--network none`（凭据出不去、也下载不了第二阶段载荷）、`--read-only` + `--tmpfs /tmp`、`--cap-drop ALL` + `no-new-privileges`、`--init`（回收僵尸，否则僵尸一直占着 pids 名额）、`--ulimit nofile`（封住句柄耗尽）、内存与 `--pids-limit` 上限（fork bomb 变成容器自己的事）、只挂工作目录到 `/work`、`--rm` 跑完即销毁。SELinux Enforcing 的宿主机（Fedora / RHEL）上挂载点自动带 `,z` —— 不带的话容器写不进工作目录，报错只有一句笼统的 `Permission denied`。其余工具仍在宿主，所以"在桌面建个文件"这类请求照常能做。

两点要知道：容器共享内核，容器逃逸漏洞仍然是逃逸，更强的边界得上虚拟机；**开了沙箱但 Docker 不可用时直接返回 503，不会静默回退宿主执行**——回退会让你以为命令跑在容器里而实际跑在自己机器上。

**镜像从哪来（2026-09-19 起）**：以前的口径是"必须自己 build"。现在改为：本地没有就**自动拉官方预编译镜像** `ghcr.io/ace-code-engine/ace-sandbox`（多架构 `linux/amd64` + `linux/arm64`，Apple Silicon 上是原生而非模拟）；只有拉取本身失败时，才把 `docker build` 作为退路一并告诉你。本地已经 build 过的镜像**永远优先** —— 只有缺失才会触发拉取。

改这个的理由是门槛：这个镜像里没有 ACE 的代码，它只是一个干净执行环境（`python:3.12-slim` + 非 root 用户），而让每个 Linux/macOS 用户先本地构建一次（还得先连得上 Docker Hub 拉基础镜像）挡掉的人远多于它保护的人。

代价是**信任锚变了**：从"你自己构建的那一份"变成"官方 CI 构建并分发的那一份"。所以这一层给三个把手，用不用由你：

- 工具结果里带 `sandbox.image_digest` —— 实际跑的是哪一份镜像，可追溯、可取证的
- `--sandbox-image ghcr.io/ace-code-engine/ace-sandbox@sha256:<digest>` —— 固定到具体摘要，registry 被换掉也拦得住
- `ACE_SANDBOX_NO_PULL=1` —— 关掉自动拉取，只用你本地 build 的那份（离线、或"边界镜像只认自己的构建"的受控部署）

镜像由 CI 构建并附 provenance 与 SBOM（[`.github/workflows/release-images.yml`](../.github/workflows/release-images.yml)），构建脚本就是仓库里的 [`docker/Dockerfile.sandbox`](../docker/Dockerfile.sandbox)，任何人都能自己复现一份对比。想更严还可以 `ACE_SANDBOX_SECCOMP=<profile.json>` 挂自己的 seccomp 配置 —— 默认用 docker 内置 profile（本就挡掉约 44 个系统调用），项目不随缘自带一份：改 seccomp 很容易连带封掉 `clone3` 这类正常路径，这种取舍该由部署方做。

**Job Object 隔离（`--sandbox job`，Windows）**

Docker 没装、或者装了但不想为一条 `dir` 起容器时，还有一档更轻的边界。它由 `executor/` 下的 Go 执行器提供。执行器是项目里唯一需要编译的组件，但**通常不需要你编译**——官方预编译二进制一条命令即可下载，只有想自己编译时才需要 Go 工具链：

```bash
ace --install-executor                          # 下载官方预编译二进制（5 平台产物，无需本机 Go）
cd executor && go build -o ace-executor.exe .   # 想自编译也可以（非 Windows 去掉 .exe）
python ai_code.py --sandbox job
```

命令会跑在一个 Windows Job Object 里：内存与子进程数上限、限制性令牌 + 中等完整性级别、退出时整棵进程树一起回收。最后那条是宿主直跑做不到的——Python 的 `Process.kill()` 只杀直接子进程，孙进程会变孤儿留在后台。

`terminal_exec` 与 `code_execute` 都走这条边界（代码片段经 `exec_python`：临时文件落盘、`-I -B` 隔离运行，源码不经命令行避免 32K 上限与引号改写）。

执行器同时是第二道判定闸：宿主已经判过的 `policy_decision` 会在独立进程里再检一次，宿主侧写错一处逻辑时它还拦得住。

与 docker 档同样的原则：**二进制没编译、本平台不支持 Tier-1、或隔离只部分生效，都返回 503**，不会偷偷改回宿主执行。`--sandbox off`（默认）下执行器若存在会顺带用一下（只为拿进程树回收），起不来则静默回落宿主——这一档本来就没承诺任何边界。设 `ACE_USE_GO_EXECUTOR=0` 可完全关掉这个可选增强。

> **生产部署必读**：不开 `--sandbox docker` 时，`code_execute` 与 `terminal_exec` 只是进程内策略层，**不是 OS 级隔离**，`python -c` 一类等价路径无法靠枚举封死。生产环境还应配合：低权限账户运行、按需授权而非常开 `write`、`signing_key` 置于项目目录之外。

> **这份文档的边界（请照做）**：它是**自评 + 断言**，不是第三方审计。
> - 有断言守着的部分：`test_all [40]`（`SECURITY-AUDIT` 里那些原始 payload）、`[38]`（结构树 ↔ 真实文件）、`[39]`（文档口径数字），以及各节末尾点名的断言——这些改坏了 CI 会红。
> - **没有断言覆盖的结论仍然只是当时的实测记录**（例如"某条 payload 现在打不穿"），随时间与重构可能失效。
> - 因此生产使用前请走自己的评估与红队演练，起点可以直接用 `docs/SECURITY-AUDIT.md` 的 payload 清单与本文的边界表，至少覆盖：间接注入 → 读项目外 → 外发链路；`code_execute` 逃逸与 `terminal_exec` 包装绕过；快照/审计日志篡改；以及**无人值守组合**（非交互 + `off` 档 + 非只读）到底能跑通什么。
