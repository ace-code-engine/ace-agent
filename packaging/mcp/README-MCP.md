# ACE · MCP 非侵入式接入包

> 这个包**不改你的 agent**。它只做一件事：让你的主 agent（Cline / Claude Desktop / Cursor / 任何
> MCP host）多出一个工具后端 —— 由 ACE 负责"这一下到底能不能动"，以及安全体检。

## 两种用法，选一个（不用都选）

| | ① 直接用 ACE 自带 agent | ② 把 ACE 当 MCP 子安全层（**本包**） |
|---|---|---|
| 你是谁 | 想要一个自己的编码 agent | 已经有主 agent（Cline/Claude/Cursor），只想多一层安全 |
| 怎么用 | 装 MSI 或解压 zip，跑 `ace` | 解压本包 → 把配置粘进 host → 重启 host |
| 改动 | 装一个程序 | **零改动**（只加一段 MCP 配置，随时删掉就恢复原样） |
| 得到什么 | 四外壳 + 51 工具 + 快照回滚 + `/undo` | `ace_security_scan`（路径级+内容级）· `ace_sandbox_exec`（CubeSandbox）· 以及 31 个可被 host 调用的工具，全部经 ACE 的裁决点 |

**② 的边界（先看清楚再决定）**：裁决权在 ACE 手里 —— 你的主 agent 想让 ACE 动什么，
都要过权限档 / 敏感目标 / 授权令三道。**默认 `readonly`**：能读、能扫，写会收到一条
"缺什么"的诚实拒绝（提权或签令），而不是静默失败。

## 四条接入路线，按你的现状选

### 路线 A（最省事，推荐）：**自包含可执行版** —— 不需要 Python、不需要装 ACE

下载 `hooh-mcp-<版本>-windows-amd64.zip`（Linux/macOS 有对应产物），解压到任意固定目录，
配置直接指向那个可执行文件：

```json
{ "mcpServers": { "ace": {
    "command": "C:\\解压出来的位置\\hooh-mcp.exe",
    "args": ["--project-root", "C:\\你的项目"]
} } }
```

**这个 exe 自带解释器**，目标机器上**不需要 Python / pip / venv**。`--project-root` 不写就用
cwd（= host 的工作区）。这是给"不想装任何环境"的人准备的路线。

### 路线 B：你**已经装了** ACE（MSI / 发布 zip / 冻结版）

不需要本包。在你的 host 配置里直接指向 `ace.exe`：

```json
{ "mcpServers": { "ace": {
    "command": "C:\\Program Files\\ACE\\ace.exe",
    "args": ["--mcp", "--project-root", "C:\\你的项目"]
} } }
```

### 路线 C（本包）：便携源码包，不需要安装 ACE

```json
{ "mcpServers": { "ace": {
    "command": "C:\\解压出来的位置\\ace-mcp.cmd",
    "args": []
} } }
```

`ace-mcp.cmd` 会把 cwd（= 你的工作区）当项目根，所以**不用硬编码路径**。
需要 Python 3.10+；`--mcp` 模式**零第三方依赖**（联网/浏览器类工具缺依赖时会如实报 501/503）。
启动器会**优先找同目录的 `hooh-mcp.exe`**，找到就用它（即路线 A 的 exe 直接扔进本包也能生效）。

### 路线 D（非 Windows）：用 `ace-mcp.sh`

```json
{ "mcpServers": { "ace": {
    "command": "/解压出来的位置/ace-mcp.sh",
    "args": []
} } }
```

## 三步装上（以 Cline 为例）

1. **解压本包**到一个固定位置（别放在会被清理的下载目录）。
2. **写配置**：跑一次 `install-cline.ps1`（会先备份你原来的配置），或者手工把
   `configs/cline_mcp_settings.json` 的内容合进 Cline 的 MCP 配置（把里面的
   `<ABSOLUTE PATH TO THIS FOLDER>` 换成你解压的目录）。
3. **重启 host**（Cline 需要重载窗口），然后在 host 里问一句
   "用 ace 读一下 README.md 的第一行"。

### 装完自己验一下（不用来问我们）

```
python verify-mcp.py            # 拉起本包 → 握手 → tools/list → 真调一次 ace_security_scan
python verify-mcp.py --write    # 额外验证写路径（会真实写一个临时文件到系统临时目录）
```

输出 `OK` 就是通了；`FAIL` 会直接说差在哪（python 版本 / 文件缺失 / 权限档）。

## 各家 host 的配置文件

| Host | 文件 | 放哪 |
|---|---|---|
| Cline（VSCode） | `configs/cline_mcp_settings.json` | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` |
| Claude Desktop | `configs/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cursor | `configs/cursor_mcp.json` | `<项目>/.cursor/mcp.json` |
| 通用 | `configs/generic-mcp.json` | 任何认 `{"mcpServers": {...}}` 的 host |

> 键名照各家公开格式写；本包作者只在 **Cline** 上实测过（见 `docs/MCP-SERVER.md` 的 M8）。
> 别的 host 若键名不同，改配置文件里的键即可，`command`/`args` 的形状是一样的。

## 包里有什么 / 没有什么

**有**：`ai_code.py`、`core/ tools/ cli/ ui/ locales/ prompts/ assets/`（跑 `--mcp` 需要的那部分）、
四份 host 配置、启动器、安装脚本、自检脚本、`VERSION`。

**没有**（有意）：
- **Python 运行时** —— 你自己装（3.10+）。要免 Python 就用路线 A 的冻结版。
- `docs/ demo/ tests/ benchmarks/` —— 仓库资料，装到用户机上只是占地方。
- `frontend/`（Ink 主外壳）—— 本包是非侵入式后端，用不到。
- `skills/` —— 示例内容，不是运行时必需（按 `<项目>/skills/<名字>/SKILL.md` 自建）。

## 安全事实（别把"扫过了"读成"安全了"）

- `ace_security_scan` 默认是**路径级**（只看文件名/路径，**不读文件内容**）。
  `deep: true` 才加内容级，且**只读文件名已命中凭据**的那批（≤64 KB/文件）。报告第一行
  永远写着范围声明 —— 报告干净**不等于**安全。
- `ace_sandbox_exec` 只在 **CubeSandbox 可达**时才跑；不可达一律**拒绝**（Tier 0），
  **绝不**退回你本机执行。凭据不注入沙箱；出网默认拒绝。
- 每次 host 调用都进 ACE 的会话台账（`<项目>/.ace_sessions/*.jsonl`，链式 MAC），
  并带 `mcp:external agent` 归属标记 —— 你能事后查清"哪一步是谁要求的"。
