# HooH 一体包 —— 虚拟化底座 + MCP 挂载

> 两件东西，一个目的：**让用户 agent 生成的代码跑在硬件隔离的底座上，而安全裁决挂在用户自己的 agent 上。**
>
> ```
>   用户的 agent（Cline / Claude / Cursor / 自研）      ← 负责"想"
>        │  MCP（本包 mount 进去的那一层）
>        ▼
>   HooH 执行层（权限 / 审批 / 审计 / 扫描）              ← 负责"这一下能不能动"
>        │  不可信代码
>        ▼
>   底座：CubeSandbox（RustVMM + KVM microVM）          ← 负责"跑起来之后还碰不到宿主"
> ```

## 为什么是两件而不是一件

底座（虚拟化内核）和挂载（MCP 服务）解决的是**两个不同的问题**，混在一起会得到
"装不上就全废"的体验：

| | 底座（CubeSandbox） | 挂载（HooH MCP 包） |
|---|---|---|
| 解决 | **代码跑在哪**（硬件隔离） | **谁来决定它能不能跑**（裁决 + 体检） |
| 依赖 | Linux + KVM（裸金属最稳） | 任何有 Python 3.10+ 的机器 |
| 没有它 | `ace_sandbox_exec` 一律**拒绝**（Tier 0） | agent 少一层安全，但 agent 本身照跑 |

**关键事实**：它们**不要求在同一台机器上**。底座可以是一台 Linux 服务器，多台机器上的
agent 都连它 —— 这就是"共用底座"的通常形态（也是本包默认推荐的形态 C）。

## 三种部署形态

| 形态 | 底座在哪 | 适合 | 怎么装 |
|---|---|---|---|
| **A 同机（最简）** | 用户这台 Linux 机器 | 裸金属 Linux / 开了嵌套虚拟化的云 VM | `sudo bash sandbox/preflight.sh` → `bash sandbox/setup-sandbox.sh` |
| **B 远程共用（推荐）** | 一台 Linux 服务器 | 用户机器是 Windows/macOS，或想一底座多客户端 | 服务器上跑 `setup-sandbox.sh`；用户机器只装挂载 |
| **C 只有挂载** | 没有底座 | 只想先要安全裁决与扫描 | 只跑 `setup-all.ps1` / `setup-all.sh` |

> **Windows / macOS 不能当底座**：CubeSandbox 要 `/dev/kvm`（Linux 内核机制）。WSL2 也只在
> **宿主暴露了嵌套虚拟化**时才可用。跑一下 `sandbox/preflight.ps1`（Windows）或
> `sandbox/preflight.sh`（Linux），它会直接告诉你这台机器的判定与修法 —— **不猜、不试错**。

## 三步装完

### ① 底座（形态 A/B 才有这一步）

```bash
sudo bash sandbox/preflight.sh          # 先看判定：KVM 可用吗
sudo bash sandbox/setup-sandbox.sh      # 钉住版本安装 + smoke + 打印接入参数
```

脚本最后会打印类似：

```
ACE_SANDBOX_API=http://10.0.0.5:3000
E2B_API_KEY=e2b_000000
```

（CubeSandbox 单机 one-click 的默认 E2B 地址是 `:3000`，演示 key 是 `e2b_000000` ——
生产请按它的文档换成自己的 key。见 `deploy/one-click/README.md`。）

### ② 挂载（写进用户的 agent）

- **Cline**：`powershell -File setup-all.ps1`（Windows）或 `bash setup-all.sh`（POSIX，打印要粘的配置）
- **任何 MCP host**：把 `configs/generic-mcp.json` 合进它的配置，并把底座参数填进 `env`：

```json
{ "mcpServers": { "ace": {
    "command": "<本包路径>/ace-mcp.cmd",
    "args": [],
    "env": { "ACE_SANDBOX_API": "http://10.0.0.5:3000",
             "ACE_SANDBOX_KEY": "e2b_000000" }
} } }
```

### ③ 验（别靠感觉）

```bash
python verify-mcp.py                    # MCP 层：握手 / 工具清单 / 真调一次扫描
python sandbox/verify-sandbox.py        # 底座层：TCP 可达 + 真建一个沙箱跑一行代码
python verify-mcp.py --write            # 写路径（可选）
```

然后让用户 agent 说一句 **"用 ace 在沙箱里跑 print(1+1)"** —— 它应该调
`ace_sandbox_exec` 并把沙箱里的 stdout 带回来。**底座不可达时它必须拒绝**（Tier 0），
而"拒绝得对不对"本身就是设计的一部分：宁可拒绝，也绝不在用户机器上跑。

## 边界（先看，再决定要不要装）

- **凭据不注入沙箱**：`ace_sandbox_exec` 不把宿主环境变量带进 microVM（CubeSandbox 自己还有
  credential vault，但本包不依赖它兜底）。
- **出网默认拒绝**：只有用户在 HooH 配置里显式给 `egress_allowlist`，才会把
  `EGRESS_ALLOWLIST` 传给沙箱；否则沙箱侧按默认拒。
- **裁决不外包**：底座只提供执行边界，**不参与**"准不准跑"的决定（S-1）。决定权始终在 HooH 执行层。
- **扫描 ≠ 安全**：`ace_security_scan` 默认只看文件名/路径（`deep: true` 才读内容，且只读名字已命中
  凭据的那批）。报告第一行永远写着范围声明。
