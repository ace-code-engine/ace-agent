# ACE 作为 MCP 安全子层（ACE-as-a-service）—— 立项卡

> 一句话：把 ACE 的**裁决点 + 安全体检**打包成一个完整的 MCP 服务 —— 主 agent（任意 MCP host）
> 挂上它当**子安全层**：主 agent 负责想，ACE 负责"这一下能不能动"并给出**可判定**的安全事实，
> 两者**共用同一个 CubeSandbox 虚拟化安全底座**（不可信代码都进同一套 KVM MicroVM）。
>
> **SEC 编号：`SEC-022`**（`docs/security/SECURITY-AUDIT.md` 的 `SEC-001~019` 已用满、
> `SEC-020` 归 WP-9 卡、`SEC-021` 已闭合，本条为新登记）。
> 上级：`docs/design/MCP-SERVER.md`（M1–M7 已落地：协议层 / 裁决 / 接线 / 台账 / `test_all [72]` /
> `e2e/mcp_probe.py` 39 条）· `docs/design/WP-9-SANDBOX-BACKEND.md`（C6 · 三层沙箱 · 四条验收）。
> 沙箱底座：TencentCloud/CubeSandbox（RustVMM + KVM microVM + eBPF 出网闸门，E2B SDK 兼容；
> 本机镜像 `G:\agents\repos\CubeSandbox`，含 `sdk/python`）。

## 一、结构

```
主 agent（Claude Code / Cline / Codex / 自研 —— 任意 MCP host）
   │  stdio MCP（initialize / tools/list / tools/call）
   ▼
ACE `--mcp`（execution_layer = **唯一裁决点**；已有，M1–M7）
   ├─ 既有白名单工具（file_read / terminal_exec / … 51 选 33）
   ├─ ★新：ace_security_scan  —— 静态安全扫描（子安全层的"体检"）
   └─ ★新：ace_sandbox_exec   —— 不可信代码 → 共用底座
                     │
                     ▼
        CubeSandbox（KVM MicroVM · eBPF 出网闸门）—— **主 agent 与 ACE 共用的同一套服务**
```

分工三句话：**主 agent 负责想**（计划 / 判断 / 读报告）、**ACE 负责裁决与体检**（能不能动 +
动之前看到了什么）、**CubeSandbox 负责第二道边界**（跑起来之后它还碰不到宿主）。

## 二、新增的两个工具（只进 MCP 面，不进 `tools/registry.py`）

`tools/registry.py` 是**给 ACE 内部模型**的常驻工具面；这两个是**给外部主 agent 的
服务面**工具 —— 不进注册表的理由与 `tool_search` 不进注册表同一条（模型的常驻面
每加一个都吃前缀预算，而这里没有模型要啃它）。

| 工具 | 干什么 | 关键边界 |
|---|---|---|
| `ace_security_scan {path, deep?}` | 对一个目录做**静态**安全扫描，返回结构化发现 | **默认路径级**（只判文件名/路径，不读内容）；`deep: true` = 内容级，**只读名字已命中凭据的文件**（≤64 KB/文件、≤200 个），高精度规则、宁可漏不可误报，超限如实说 skipped |
| `ace_sandbox_exec {code, language, timeout_s}` | 把一段代码丢进 CubeSandbox 跑，带回 stdout/stderr/exit | **Tier-0 铁律**：沙箱不可达 → 拒绝（`isError` + 部署指引），**绝不**退回本地执行 |

扫描判据**全部复用既有名单，不另立**：`core/sensitive.py`（`sensitive_target` /
`is_credential_file` / `SENSITIVE_DIR_PREFIXES`）、`tools/base._OS_HANDOFF_BLOCKED_SUFFIXES`
（ShellExecute 会**运行**的后缀）、`tools/base.network_path_reason`（UNC 是出站连接）。

## 三、S-1 边界（从 WP-9 卡移植，一个字不改）

> **可以把「执行边界」外包给沙箱；不可以把「决定权」外包出去。**

这个子层不新增任何裁决路径：能不能调用工具、动哪个路径，仍然是 `execution_layer`
那三道（权限档 / 敏感目标与规则 / 授权令）。沙箱只是 Tier 0 拒绝掉的缺口的补集。

## 四、验收（可断言，红先行）

1. **沙箱不可达 → Tier 0 拒绝**：`ace_sandbox_exec` 返回 `isError`，文案点名"沙箱不可达"
   与缺什么（`ACE_SANDBOX_API` + `pip install e2b` + 部署指引），**不**说"命令跑完了"。
2. **凭据绝不进沙箱**（WP-9 验收 1）：backend 不注入任何宿主环境变量；断言 fake 沙箱收到的
   `env == {}`（用户显式配的出网 allowlist 除外，那是白名单参数不是凭据）。
3. **出网默认拒绝**（WP-9 验收 3）：未配置 egress allowlist 时 backend **不传任何**出网参数
   （沙箱侧默认拒）；配置了才传，且取值与 ACE 的 `egress_allowlist` **同一份清单、同一个来源**。
4. **扫描如实声明（SEC-022 的落点）**：报告开头写明扫描范围（"只判文件名/路径，不读内容"），
   防止"ACE 扫过了"被读成"安全了" —— 那才是这个子层最危险的失败方向（虚假保证）。
5. **MCP 面收口**：`tools/list` 多出这两条（白名单守卫 `e2e/mcp_probe.py` 同步更新 ——
   它本来就断言"一个不多一个不少"，不改会红）；未知工具仍 `-32602`；调用照旧进
   台账（`source="mcp"`）。

## 五、不做（防范围漂移）

- **不自研** microVM / 容器（`ROADMAP` NG-01）：接 CubeSandbox，不是重写它。
- **不新增裁决路径**（S-1）；`ace_sandbox_exec` 不 fallback 到本地（Tier 0 铁律）。
- **默认不读文件内容**；`deep` 只读"名字已命中凭据"的那批（v2 已落地），
  **不做全树内容级正则扫描**（读一切 + 大文件 IO + 正则噪音的整套论证不在本卡）。
- 不做 HTTP transport（`MCP-SERVER.md` §2 已定）。
- **不强制依赖 e2b SDK**：可选装（`pip install e2b`），装了 + 配了 API 才真的连通；
  没装就如实拒绝 —— "没装 SDK"不是"沙箱坏了"，文案分得清。
- 不动 CubeTemplateCenter 的模板市场（那是 CubeSandbox 的产品面）。

## 六、里程碑

| # | 内容 | 完成判据 |
|---|---|---|
| A1 | 本卡 + `SEC-022` 登记 | 文档守卫过 |
| A2 | `core/ace_secscan.py` + `core/ace_cubesandbox.py`（纯逻辑 + fail-close） | `test_all [89]` 前半红→绿 |
| A3 | MCP 接线（`_run_mcp` 拼工具面 + 路由）+ `e2e/mcp_probe.py` 新用例 | 四闸全绿，探针全过 |
| A4 | ARCHITECTURE / CHANGELOG / ROADMAP 进度 | 文档守卫过 |
| A5（人做） | **真机冒烟**：部署 CubeSandbox → 设 `ACE_SANDBOX_API` → 主 agent 调 `ace_sandbox_exec` 跑一段隔离代码，并在 `/audit` 里看到它 | 与 `MCP-SERVER.md` 的 M8 同一条口径：**只能由真跑过的人说"跑过"** |

## 七、已知风险（照实写）

- **这个子层最大的失败方式不是"被绕过"，是"被当成安全证明"**：主 agent 拿到一份扫描报告
  就下"安全"的结论，而报告只是**路径级**的。所以验收 4 要求报告自带范围声明，并且
  工具 description 里就写着"这是路径级扫描" —— 不把"扫过"与"安全"混成同一个词。
- CubeSandbox 需要 `/dev/kvm`（裸金属最稳，云 VM 走 PVM，WSL2 要开嵌套虚拟化）；
  本机目前**没有部署** —— 因此 `ace_sandbox_exec` 在本机实测的常态就是 Tier 0 拒绝，
  而"拒绝得对不对"正是验收 1 要钉的。
- e2b SDK 的真实 wire 行为只在 A5 真机冒烟时才会被真实验证；单测用的是注入的 fake，
  形状照着 E2B Python SDK（`Sandbox.create` / `run_code` / `Execution.stdout·stderr·exit_code`）写。

## 八、主 agent 侧配置片段（打包形态）

通用形状见 `docs/MCP-SERVER.md` §1；**安全子层这个角色**多两个键（Windows 上 `python`
写全路径或 `py`，各家 host 的键名差异见那节的"未验证"说明）：

```json
{
  "mcpServers": {
    "ace-sec": {
      "command": "python",
      "args": [
        "/abs/path/to/ace/ai_code.py", "--mcp",
        "--project-root", "/abs/path/to/your/project",
        "--permission", "write"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "ACE_SANDBOX_API": "http://<CubeSandbox 部署地址>:8080"
      }
    }
  }
}
```

- `--permission write` 是给"子层也要真跑测试"的场景；只做**扫描**的话保持默认 `readonly` 就够
  （`ace_security_scan` 是只读观察）。
- `ACE_SANDBOX_API` 指向 CubeSandbox 部署 —— **主 agent 自己的不可信执行与这个子层指向
  同一套服务**，这就是"共用一个安全底座"在配置层面的全部含义；出网 allowlist 读
  ACE 自己的 `egress_allowlist` 配置（同一份清单）。
- 装 SDK：`pip install e2b`（可选；不装时 `ace_sandbox_exec` 会如实说"没装 SDK"）。
