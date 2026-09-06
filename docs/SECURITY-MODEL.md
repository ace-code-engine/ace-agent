# 安全模型（Security Model）

> 本文档由 README「安全模型」一节拆分而来（docs/README-RESTRUCTURE.md，v3.7），内容与当时 README 保持一致。
> README 入口见「安全设计」；漏洞报告流程见仓库根 [SECURITY.md](../SECURITY.md)；历史安全审计见 [SECURITY-AUDIT.md](SECURITY-AUDIT.md)。

配置优先级：命令行参数 > `~/.ai_code.json` > `~/.claude/settings.json` > 环境变量。

**权限与授权**

- 默认 `readonly`；写工具需显式 `/permission write` 或 `--permission write`
- 授权两档：「本次」用后即焚，「本会话」本会话内不再询问
- `terminal_exec` 强制逐次确认，不接受会话级授权
- 非交互模式（非 tty）下一切授权请求与计划审批都 fail-close 拒绝

**执行隔离**

- `terminal_view`：白名单只读命令，内建实现不经 shell，拦 shell 元字符，版本参数严格校验
- `code_execute`：AST 拦危险模块（os/subprocess/socket/pickle/importlib…）与内建逃逸链（`__builtins__`/`__class__`）、`open` 全禁 → 环境变量清洗 → 临时目录 + 30s 超时
- `math_calc`：白名单 AST 求值，仅纯算术，幂运算限 100^1000，杜绝 eval 逃逸与指数 DoS

**路径边界**

- 文件工具默认限制在项目目录内（`confine_files`，含跨盘符检查）；`grep`/`glob` 无条件限项目内，只读检索也不放开项目外
- 读越界按"泄露什么"分档：**读文件内容一律限项目内**（`cat`/`type`、外部命令路径参数、`file_read` 均 403）；**列目录名单允许越界**（`ls`/`dir`）。前者泄露的是凭据本身，后者只是文件名
- 敏感目标硬拦截：绝对路径写入放行（"放到桌面"）但不含凭据与自启动入口（`~/.ssh`、`~/.bashrc`、`~/.ai_code.json`、`.pem`/`.key` 等）

**回滚与网络**

- 写入前自动快照，快照元信息可用 `signing_key` 做 HMAC-SHA256 签名；快照数量有硬上限，自动清理最旧
- `.guardian/` 快照目录对所有工具只读且不可写删——它就在 Agent 可写的项目目录里，不挡住的话改一行 `meta.json` 就能让熔断回滚静默失效；回滚失败会告警而不是静默吞掉
- 守门分层：block 级拦截并回滚本轮快照，warn 级不阻断；只回滚本轮，不动无关修改
- `api_get`/`api_post` 仅 http/https，且 **DNS 解析后**拦截内网 / 回环 / 链路本地地址（防 SSRF）；未实现的工具返回 501 而非假成功

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

上面所有校验都是进程内的 Python 逻辑。`terminal_exec` 是 `shell=True`，cwd 固定在项目根挡不住 `cd /`；`code_execute` 的 AST 黑名单也不可能枚举完。真正的边界要靠内核：

```bash
docker build -t ace-sandbox:latest -f docker/Dockerfile.sandbox .
python ai_code.py --sandbox docker
```

开启后 `terminal_exec` / `code_execute` 的每次调用都是一个一次性容器：`--network none`（凭据出不去、也下载不了第二阶段载荷）、`--read-only` + `--tmpfs /tmp`、`--cap-drop ALL` + `no-new-privileges`、内存与 `--pids-limit` 上限（fork bomb 变成容器自己的事）、只挂工作目录到 `/work`、`--rm` 跑完即销毁。其余工具仍在宿主，所以"在桌面建个文件"这类请求照常能做。

两点要知道：容器共享内核，容器逃逸漏洞仍然是逃逸，更强的边界得上虚拟机；**开了沙箱但 Docker 不可用时直接返回 503，不会静默回退宿主执行**——回退会让你以为命令跑在容器里而实际跑在自己机器上。

镜像必须自己 build，它不会发布到任何 registry：它就是执行边界，里面装了什么得由部署方掌握。所以"镜像没构建"是单独判、单独报的一档 503，直接把上面那条 `docker build` 给你——而不是让 `docker run` 去 registry 找 `ace-sandbox`，先等一个网络超时、再回一句 `pull access denied` 让你以为是要登录。

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
