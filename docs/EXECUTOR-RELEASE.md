# 执行器发布通道（EXECUTOR-RELEASE）立项卡

> **目标**：消除 `--sandbox job` 的"必须先装 Go 再 `go build`"门槛——通过 CI 交叉编译产出官方预编译二进制并挂到 GitHub Release，宿主侧提供 `ace --install-executor` 一键下载；手工 `go build` 路径保留，且所有"拿不到边界就报错、绝不静默回退"的语义不变。
> **性质**：方案卡。按下方 S1→S5 独立提交、逐项回归执行；行号以 v3.6.0 为准，改动后可能漂移，以代码为准。

---

## 1. 背景

风险清单第 1 条（Windows 中心化）里的子问题成立且有现成缺口：

- Job Object 是 Windows 专属原语，非 Windows 平台 `--sandbox job` 只能诚实返回 503（`executor/sandbox_other.go` 整文件占位，`sandbox.go` 里 `unavailable[tierJobObject]` 写明原因）。这条**不打算改**——Windows 原生边界 + docker 档跨平台是既定威胁模型。
- 但"Go 执行器需要额外编译"是**所有平台共有的摩擦**。现状：CI 在 ubuntu/windows 上 `go build` **只为测试**（`.github/workflows/ci.yml` 的 `go-test` job），从不产出产物；Release 上没有任何预编译二进制。
- 宿主侧预期路径固定为 `executor/ace-executor(.exe)`（`ace_executor.py:default_binary_path()`），找不到时提示"build it with `go build ...`"（`ace_executor.py:262-263`）；`ace_doctor.py:67` 同样只提示手工编译。
- 执行器只用 Go 标准库 + `syscall`（注释明言"不下载任何模块"），`CGO_ENABLED=0` 交叉编译天然可行，无需 cgo。

结论：缺口不是"没有跨平台边界"，而是**边界已经有了、却没有一条低摩擦的获取通道**。本卡只补通道，不改边界本身。

## 2. 目标

1. GitHub Release 上可下载 5 个平台/架构的 `ace-executor` 预编译二进制（Windows amd64、Linux amd64/arm64、macOS amd64/arm64）。
2. `ace --install-executor` 一键下载对应平台产物到 `executor/`，下载后自校验（能打印版本号）才算成功，失败给出 `go build` 回退指引。
3. 全部提示文案（`ace_executor.py`、`ace_doctor.py`、README）指向新通道，同时保留手工编译路径。
4. 语义不变：job 档拿不到边界依旧 503；`--sandbox off` 下执行器依旧"顺带用一下，起不来静默回落"。

## 3. 非目标

- ❌ 给 Linux/macOS 增加新的原生隔离档（Landlock/seccomp/bwrap 等）——那是另一张卡。
- ❌ 改 NDJSON 协议、执行器运行逻辑、docker 档。
- ❌ 引入第三方 CI action（沿用仓库只用官方 action 的习惯；发布用 runner 自带的 `gh` CLI）。

## 4. 现状锚点（v3.6.0）

| 位置 | 现状 | 改动 |
|---|---|---|
| `executor/main.go:22-25` | `serverVersion = "0.1.0"` 是 `const`，无 CLI 参数处理（main 忽略 `os.Args`） | 改 `var` + `--version`/`-v` 分支 |
| `.github/workflows/ci.yml` | `go-test` 只 build+test，无产物 | 不动；新增独立 workflow |
| `ace_executor.py:215-217,262-263` | 二进制路径固定 `executor/ace-executor(.exe)`；缺二进制提示只给 `go build` | 提示加 `ace --install-executor` |
| `ace_doctor.py:62-67` | 探测 `executor/ace-executor(.exe)`/`executor.exe`，未找到只提示 `go build` | 提示加 `ace --install-executor` |
| `ai_code.py` | 已有 `--install-ui` 先例：argparse（L2883）+ 底部 dispatch（L2891 一带）+ REPL 防蠢清单（L190）+ 聊天内快捷提示（L1887 一带） | 新增 `--install-executor`，以 `--install-ui` 的既有触点为模板逐一对齐 |
| `version.py` | `__version__ = "3.6.0"`（版本单源 Q-12） | 发布时随版本号 |
| `README.md` | "唯一需要编译的部分"见 L319、L411；`--sandbox job` 示例 L91、L322；版本历史 L487 仍写"未打 git tag"（过时，仓库已有 v3.3~v3.6 里程碑 tag） | 措辞改预编译通道；L487 去旧描述并注明 v3.7 起随 Release 打同号 tag |
| `.gitignore:26-29` | 已忽略 `executor/ace-executor(.exe)`/`executor.exe` | ✅ 无需改（下载产物不会被误提交） |

## 5. 设计决策

### D1 · 发布触发与 tag 策略 —— `workflow_dispatch` 手动发布，首次发布创建 `v{version}` tag

仓库现状：版本号在 version.py/README/CHANGELOG 三处同步（Q-12）；里程碑 tag v3.3~v3.6 本地已存在（README L487 的"未打 git tag"是过时描述，S4 一并修正），但**从无携带产物的 GitHub Release**。GitHub Release 必须有 tag 载体。

- 新 workflow `.github/workflows/release-executor.yml`：`workflow_dispatch` 触发，输入 `version`（可空）；为空时由 step 读 `version.py`（`python -c "import version;print(version.__version__)"`）。
- `gh release create v{version} <产物…> --title "ace-executor v{version}" --notes "…"`。发布时自动在远端创建/更新 tag `v{version}`——v3.7.0 是**第一个与 GitHub Release 绑定的 tag**，延续既有 v{version} 里程碑 tag 命名，不引入新的日常提交纪律。
- 理由：发布是显式人工动作（workflow_dispatch），不是每次提交的默认行为；未来若想 tag 驱动可在此 workflow 加 `push: tags: v*` 扩展点。

### D2 · 产物矩阵与发布流程（交叉编译 + 原生冒烟 + Release）

产物矩阵（构建 job 在 ubuntu-latest 上交叉编译，`CGO_ENABLED=0`）：

| GOOS/GOARCH | 产物名 | 说明 |
|---|---|---|
| windows/amd64 | `ace-executor-windows-amd64.exe` | 主目标（job 档唯一入口） |
| linux/amd64 | `ace-executor-linux-amd64` | 常见服务器 |
| linux/arm64 | `ace-executor-linux-arm64` | |
| darwin/amd64 | `ace-executor-darwin-amd64` | Intel Mac |
| darwin/arm64 | `ace-executor-darwin-arm64` | Apple Silicon |

- 编译参数：`CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X main.serverVersion={version}" ./`。
- workflow 分三步 job，产物经 `upload-artifact`/`download-artifact` 交接（两者均为 actions 官方 action，与仓库只用官方 action 的习惯一致；发布本身用 runner 自带的 `gh` CLI，不引入第三方 action）：
  1. `build`（矩阵 5 产物）→ `upload-artifact`；
  2. `native-smoke`（矩阵 windows-latest / ubuntu-latest / macos-14）：checkout 后本机 `go build` + 运行 `--version`——**原生验证 D4 的 flag 在三个 OS 家族都能编译并运行**（macos-14 为 arm64 runner，顺带覆盖 darwin/arm64）；
  3. `release`（`needs: [build, native-smoke]`）→ `download-artifact` → `gh release create`。
- 失败即红：产物矩阵任一构建失败，整个发布失败，不发布半套。残余盲区仅 darwin/amd64（Intel mac 交叉产物无原生 CI），首次发布后人工冒烟一次即可（同源代码 + 全 stdlib，风险低）。

### D3 · `ace --install-executor`（ai_code.py）

以 `--install-ui` 的既有触点为模板逐一对齐（argparse / 底部 dispatch / REPL 防蠢清单 L190 / 聊天内快捷提示 ~L1887）：

1. argparse 增 `--install-executor`（help 注明"下载官方预编译执行器，替代手工 go build"）；底部 dispatch 在 flag 置位时调用 helper 后退出。
2. 模块级 helper（放 `_pip_install_with_fallbacks` 旁）：
   - 实现机制用**标准库 `urllib.request`**（带 UA、超时），不新增依赖——`requests` 本就是可选项，安装通道不该反过来要求它。
   - `platform` + `platform.machine()` 规范化（`AMD64`/`x86_64`→`amd64`；`arm64`/`aarch64`→`arm64`）→ 查 D2 表；查不到（如 win32/arm64）明确报"无预编译产物，请 `cd executor && go build`"。
   - 下载源：默认 `https://github.com/jincheng3870682453-hash/ace-agent/releases/latest/download/{asset}`（owner/repo 写死在 helper，与 README 徽章一致），环境变量 `ACE_EXECUTOR_BASE_URL` 可覆盖（镜像/内网）。
   - 下载到 `executor/ace-executor(.exe)`（临时文件 + rename，非 Windows `chmod 0o755`）。
   - **自校验**：跑 `{binary} --version`，能打印版本即成功；失败删除文件并提示手工 `go build`。绝不把"看着像下载成功"当成功。
   - 成功文案带下一步：`python ai_code.py --sandbox job`（Windows）或说明非 Windows 上 job 档不可用、二进制供 `off` 档进程树回收/未来档位。
3. REPL 防蠢清单（`ai_code.py:190` 附近）把 `--install-executor` 与 `--install-ui` 并列加入，避免用户把命令行参数打进聊天；若 `--install-ui` 在聊天输入侧还有快捷提示（~L1887），对 `--install-executor` 做对称处理或不加提示而只在防蠢清单中拦截。

### D4 · Go 侧 `--version`（executor/main.go）

- `serverVersion` 由 `const` 改 `var`（默认仍 `"0.1.0"`，供本地开发构建），支持 `-ldflags -X main.serverVersion=…` 注入发布版本。
- `main()` 开头：`len(os.Args) > 1 && (os.Args[1] == "--version" || os.Args[1] == "-v")` → 打印 `ace-executor {serverVersion} {goos}/{goarch}` 后 `os.Exit(0)`，不进会话循环。
- 理由：安装器自校验、`ace_doctor` 报版本、用户排查都依赖一个零成本的版本出口；protocol 里 `server.version` 已存在但不适合做命令行冒烟。

### D5 · 文案联动（每处独立小改）

| 文件 | 改动 |
|---|---|
| `ace_executor.py:262-263` | start() 缺二进制提示追加 "；或 `ace --install-executor` 下载官方预编译二进制" |
| `ace_doctor.py:67` | warn 文案追加同款指引 |
| `README.md` | L91（快速开始 sandbox job 行）、L319-323（job 段"唯一需要编译的部分"→"默认用官方预编译二进制，需自行编译时…"）、L411（项目结构 executor 注释）、L487（版本历史"未打 git tag"→"v3.7.0 起随发布打 tag"） |
| `version.py` + `CHANGELOG.md` | 3.6.0 → 3.7.0 + v3.7.0 条目（含本卡）；`docs/DEVELOPMENT.md` 若含发布/产物流程描述则同步补一步 |

## 6. 落地步骤（每步独立提交 + 回归）

- **S1 · Go 版本出口**：`executor/main.go`（D4）+ `go vet`、`go test ./...`（本机）。协议零改动。
- **S2 · 发布工作流**：新建 `.github/workflows/release-executor.yml`（D1+D2）。本地无法完整验证，需 push 后手动 dispatch 一次（见 S5）。
- **S3 · 安装器**：`ai_code.py`（D3 各触点点位）+ `ace_executor.py`、`ace_doctor.py` 提示（D5）。回归：`ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` + `python test_all.py`。
- **S4 · 版本与文档**：`version.py` 3.7.0、`CHANGELOG.md` v3.7.0、`README.md`（D5 四处）。回归：README 徽章/CHANGELOG 首条/version.py 三者一致（Q-12 纪律）。
- **S5 · 发布与真机验证（需有 push 权限 + GitHub token 的环境）**：
  1. push S1-S4 → 手动 dispatch `release-executor` → Release 出现 `v3.7.0` + 5 产物；
  2. 本机删掉 `executor/ace-executor.exe` → `python ai_code.py --install-executor` → 下载 + `--version` 自校验通过；
  3. `python ace_doctor.py` 显示执行器已找到；`python test_all.py` 全绿（含执行器用例）。

## 7. 全局验收清单

- [ ] `--install-executor` 在无 Go 环境的 Windows 上装出可用二进制（`--version` 通过），`--sandbox job` 不再需要手工编译。
- [ ] 非 Windows 平台点安装器：正确下载对应 linux/darwin 产物；对不存在的档位仍诚实报错/指引，无静默降级。
- [ ] 网络不通 / 平台无产物 / 下载校验失败 → 明确报错并回退提示 `go build`，绝不假装成功。
- [ ] 下载产物被 `.gitignore` 覆盖，`git status` 干净。
- [ ] 所有"需要 go build"的用户可见文案都有 `--install-executor` 替代指引。
- [ ] `test_all.py` 全绿、ruff 零命中、版本号三处一致。
- [ ] Release 含 5 个命名规范的产物（D2 表）。

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 仓库此前 tag 只是里程碑代称、从不挂产物 | v3.7 起 tag 与 GitHub Release 绑定（同 v{version} 命名）；重复运行幂等：已有 Release 只 upload 产物，不重建 |
| `gh` 缺权限 | workflow `permissions: contents: write`；ubuntu runner 自带 `gh`；失败即红，可重跑 |
| 国内访问 github.com Release 慢/不通 | 保留 `go build` 路径；`ACE_EXECUTOR_BASE_URL` 支持镜像覆盖（与 `--install-ui` 多镜像思路一致） |
| 二进制与宿主协议版本漂移 | 协议本有 `initialize` 版本协商；产物按 `version.py` 对齐；`server.version` 可在 `--version` 与 doctor 中比对 |
| darwin/amd64（Intel）交叉产物无原生 CI | macos-14 原生冒烟已覆盖 darwin/arm64；darwin/amd64 首版发布后人工 mac 冒烟一次（同源代码 + 全 stdlib，风险低） |
| workflow 需真实 push/dispatch，本地沙箱无法端到端 | S5 明确列为"需在具备 push 权限的环境执行"的 GitHub 侧动作，本机侧验证（下载/doctor/test）不受限 |

## 9. 不在本卡范围

- Linux/macOS 原生隔离档（Landlock 等）——需另立卡评估。
- 执行器/协议任何行为改动。
- PyPI/wheel 打包（见 `docs/PACKAGING.md`，与本卡独立）。
