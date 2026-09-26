# ACE v3.42.0 · 执行层的承诺对齐 + 一个只读的元处理内核

> 本条同时作为 v3.42.0 的发布说明，可直接粘进 Release。
> 一行摘要：**修掉 6 处"文档说了、代码没做"的边界；新增 Rust 元处理内核（只算不裁）；
> 补上一个以前答不出来的问题——我在这台机器上花了多少。**

发布物与 v3.41.0 相同（同一个 tag 下 5 平台执行器 + Windows 单目录包）。新增的 Rust 引擎**不进包**，
冻结版自动降级为等价的纯 Python 实现（功能在，只是部分命令略慢）。

## 这一版给你什么

- **6 处"承诺了、没做"被对齐**：`code_execute` 在 `job` 档静默回落到宿主执行 → 与 `terminal_exec` 同口径 **503**；L4 守门"第一条失败就返回"，前两条恰是 warn 级，一个未注解 `def` 就让密钥/SQL/递归检查一次都没跑 → 跑满全部规则再按 **block > warn** 汇总；项目级 MCP 无信任门（克隆陌生仓库即执行它指定的二进制）→ 复用 hooks 信任门、默认不加载并说明原因、子进程剥离敏感环境变量；飞轮把违规原文写进项目内文件 → 只留规则名 + sha256 + 长度；`!命令` 与 `/review` 回填绕过权限/快照/审计 → 新增 `run_tool_direct()`（刻意不设"已确认"）；`--serve` 的 `v` 缺省被接受、坏值抛裸异常 → **必填且必须是整数**。
- **三类静默丢数据**：一条坏 entry 让整份记忆归零（→ 逐条容错，整个文件读不出来时**隔离**成 `.corrupt-<时间戳>`，绝不就地清空）；主会话与子代理互相覆盖（→ 写回前与磁盘合并、按身份去重）；`disarm` 被静默复活（→ 变更前重读磁盘，CAS 比的是磁盘当前值）。
- **新增：Rust 元处理内核**（只读 · 只算不裁），第一个切片是**会话事件流索引**。第一个数就值得看：一份 132 KB / 122 事件的真实日志里 **95% 是重复字节**（132,350 → 去重 6,871），主因是每轮重写完整系统提示词（占 88%）。边界写死在代码里：不判权限、不看路径、不碰文件系统、不联网 —— 坏掉只会变慢，不会放宽任何闸门。零依赖，离线可构建。
- **新增：运行度量与跨会话成本**。工具耗时与 token 用量以前只活在内存里（日志时间戳只有秒级：262 份真实日志实测平均 11.2 条事件却只有 1.8 个不同时间戳，推不出来）。现在它们落进日志：`/status`、主页、`/audit stats` 各多一行；成本仍由本地价目表算，查不到价格就显示 `—`，不编数字。
- **写前快照 4.4×**（并行读回，判定与顺序版逐字一致），另有 `snapshot_verify=rollback` 的 **12×** 档：校验一步没少，只是挪到撤销那一刻 —— 坏快照在任何一档都不会被静默恢复。

## 升级注意

| 变化 | 影响 |
|---|---|
| `!命令` / `/review` 回填受权限档约束 | 只读档下被拒并提示 `/permission write` |
| 飞轮不再落违规原文 | 取样需按 sha256 从会话日志取回并自行脱敏 |
| `disarm` 不再被别的实例写回 | 恢复需显式 `resume` |
| `/status`、主页、`/audit stats` 各多一行 | 老日志的耗时/token 显示 0（"当时没记"，不是"没算"） |
| 四张演示图已重录 | 顺带修掉"折叠路径时框缺一角、路径长度进产物"的老问题 |

## 怎么开始

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python test_all.py         # 端到端套件；安全核心为纯标准库
python ai_code.py --mock   # 离线演示：模型 ↔ 执行层完整闭环
```

复核本版只需三条：`python test_all.py --only 70`（本版全部缺陷回归）·
`cd engine && cargo test --offline && ./target/release/ace-engine --selftest` ·
`python engine/tools/xcheck.py`（真实数据对拍）。

## 验证到什么程度

- 端到端套件 **2310 / 2310 通过**，跳过 3 项（本机缺 Windows Job Object 档能力时的探测项）。
- 本版新增断言 **56 条**（52 条对应**先复现过**的缺陷 + 4 条演示录制不变量）；全量随平台浮动，以 `python test_all.py` 输出为准。
- 引擎侧：单元测试 20、自检 16、真实数据对拍 8。**CI 现在会真的编译并测试引擎** —— 此前它从未被编译，`test_all` 里"引擎路径 == 纯 Python 降级路径"那批断言等于自己跟自己比。
- 用户数据完好：记忆文件仍 517 条，无隔离文件。

## 已知未验证

- `darwin/amd64` 执行器产物没有原生冒烟（交叉编译成功，无 Intel Mac 实机）；真 TTY 下的全屏界面与非 Windows 控制台同样未做真机冒烟。
- 引擎不进发布包是**刻意的**（实测在热路径上没有收益）：冻结版走同口径纯 Python 路径，见 `docs/PACKAGING-EXE.md`。

**架构图（Mermaid，GitHub 直接渲染）** → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
**本版完整细节** → [`docs/RELEASE-NOTES-v3.42.0.md`](docs/RELEASE-NOTES-v3.42.0.md) · [`CHANGELOG.md`](CHANGELOG.md)

本项目有一条纪律：**没真正跑过的，不许说成"应该没问题"。**

---

## English

> This doubles as the v3.42.0 release note — paste it into the Release as-is.
> One-line summary: **six places where the docs promised something the code did not do are now aligned; a read-only Rust meta-processing kernel; and an answer to a question we could not answer before — how much did this cost me on this machine.**

Artifacts are unchanged from v3.41.0 (five executor platforms plus a Windows bundle under the same tag). The new Rust engine is **not shipped**; a frozen build degrades to the equivalent pure-Python path (same features, a few commands slower).

## What this version gives you

- **Six promises the code did not keep, now aligned**: `code_execute` silently fell back to host execution under `--sandbox job` → same contract as `terminal_exec`, **503**; the L4 guard returned on the first failing rule and the first two are `warn` level, so one unannotated `def` disabled the secret/SQL/recursion checks entirely → all rules run, then **block > warn**; project-level MCP had no trust gate (cloning an unfamiliar repo executed the binary it names) → reuses the hooks trust gate, off by default and says why, child environment stripped; the flywheel wrote raw violating output into a project file → rule name + sha256 + length only; `!cmd` and the `/review` write-back bypassed permissions/snapshots/audit → new `run_tool_direct()` (which deliberately does not mark the call "confirmed"); `ace --serve` accepted a missing `v` and let `v="abc"` raise through the main loop → **required and integer-typed**.
- **Three kinds of silent data loss**: one bad entry flattened the entire memory (→ per-entry tolerance; an unreadable file is **quarantined** as `.corrupt-<ts>`, never overwritten); the main session and a subagent overwrote each other (→ writes merge with disk, deduplicated by identity); `disarm` was silently resurrected (→ mutations re-read the disk first, CAS against the file).
- **New: a Rust meta-processing kernel** (read-only, computes only — never decides). Its first slice indexes the session event stream, and its first finding is worth reading: in a real 132 KB / 122-event log, **95% of the bytes are duplicates** (132,350 → 6,871 unique), mostly the full system prompt rewritten every round (88%). The boundary is hard-coded: no permission decisions, no path inspection, no filesystem, no network — broken, it only gets slower and can never loosen a gate. Zero dependencies, buildable offline.
- **New: runtime metrics and cross-session cost.** Tool elapsed time and token usage used to live only in memory (log timestamps are second-granular: 262 real logs average 11.2 events but only 1.8 distinct timestamps, so they were underivable). Both are now recorded: `/status`, the landing page and `/audit stats` each gained a line. Cost still comes from the local price table; with no price it shows `—` rather than inventing a number.
- **Pre-write snapshots 4.4× faster** (parallel read-back, byte-identical verdicts), plus an opt-in **12×** via `snapshot_verify=rollback`: no check is skipped, it just moves to undo time — a corrupt snapshot is never silently restored in either mode.

## Upgrade notes

| Change | Effect |
|---|---|
| `!cmd` / `/review` write-back respects the permission level | In `readonly` it is refused with a hint to run `/permission write` |
| The flywheel no longer stores raw violating output | Retrieve by sha256 from the session log and redact it yourself |
| `disarm` is no longer overwritten by other instances | Resuming requires an explicit `resume` |
| `/status`, the landing page and `/audit stats` each gained a line | Old logs show 0 for elapsed/tokens — "not recorded then", not "not computed" |
| All four demo SVGs re-recorded | Along with the old "folded path leaves the box missing a corner and bakes the path length into the artifact" defect |

## Getting started

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python test_all.py         # end-to-end suite; the safety core is pure stdlib
python ai_code.py --mock   # offline demo: the full model <-> execution-layer loop
```

Three commands verify this release: `python test_all.py --only 70` (every regression added here) ·
`cd engine && cargo test --offline && ./target/release/ace-engine --selftest` ·
`python engine/tools/xcheck.py` (cross-checks the kernel against the pure-Python path on real data).

## How far it is verified

- End-to-end suite: **2310 / 2310 passing**, 3 skipped (capability probes for the Windows Job Object tier on this machine).
- This release adds **56 assertions** (52 tied to defects that were **reproduced first**, plus 4 demo-recorder invariants); totals float by platform, `python test_all.py` output is authoritative.
- Kernel side: 20 unit tests, 16 self-test checks, 8 real-data cross-checks. **CI now actually compiles and tests the kernel** — it was never compiled before, which made the "engine path == pure-Python fallback" assertions compare the fallback with itself.
- Your data is intact: the memory file still holds 517 entries, with no quarantine files.

## Known unverified items

- The `darwin/amd64` executor has no native smoke test (it cross-compiles; no Intel Mac has run it), and neither the full-screen TUI under a real TTY nor non-Windows consoles have a native smoke run.
- The kernel is deliberately **not shipped in the release bundle** (measurements show no gain on hot paths): a frozen build uses the equivalent pure-Python path — see `docs/PACKAGING-EXE.md`.

**Architecture diagram (Mermaid, rendered by GitHub)** → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
**Full details for this version** → [`docs/RELEASE-NOTES-v3.42.0.md`](docs/RELEASE-NOTES-v3.42.0.md) · [`CHANGELOG.md`](CHANGELOG.md)

The project has one rule: **anything not actually run does not get described as "should be fine".**

---

**Source** · [Repository](https://github.com/ace-code-engine/ace-agent) · [README](https://github.com/ace-code-engine/ace-agent#readme) · [Getting started](docs/GETTING-STARTED.md) · [Security model](docs/SECURITY-MODEL.md) · [Release notes](docs/RELEASE-NOTES-v3.42.0.md) · [Changelog](CHANGELOG.md)
