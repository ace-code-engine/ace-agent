# ACE v3.43.0 · 把"信任"从判据挪到结构上

> 本条同时作为 v3.43.0 的发布说明，可直接粘进 Release。
> 一行摘要：**修掉一道能被伪造的写前快照**（签名密钥移出工作区）· **给会话台账加链式签名**
> （改过、删过、插过都看得见）· **两条要改判据的东西先只测量**（来源归属、可逆性）。

发布物与 v3.42.0 相同（5 平台执行器 + Windows 单目录包）。**本版不改任何裁决行为** ——
两条判据只测量，`/audit stats` 里那两行是"若开判据会怎样"的预测。

## 这一版给你什么

- **写前快照不再可伪造**（缺陷先复现过）：密钥原来住在 `<项目>/.guardian/signing_key`，而 `.guardian` 就在项目里 —— 拿到项目目录读写权限就能读出密钥、改副本、修摘要、重签，`verify_snapshot()` 照样返回 `True`。现在密钥放在**工作区之外**的锚目录，老项目自动迁移（**搬**，不是拷）；锚不可用时写操作直接拒绝（fail-close），不会悄悄生成未签名快照。
- **审计记录改不动了**：每条会话事件带 `mac = HMAC(台账密钥, 上一条的 mac ‖ 该条正文)` —— 改内容、删中间一条、剥掉某条的签名、尾部追加伪造，`/audit stats` 全部报 `broken` 并指出第几条；老日志如实报 `unverifiable`（不冒充 ok，也不冤枉成 broken）。
- **两条判据的前置测量**：① 来源归属 —— 同一句删除，配"用户要求"/"指令来自读到的内容"/"用户没提过"，现在三条裁决仍然一样（**这是实测复现的缺陷**），本版先把"目标有没有被用户提过"记下来；② 可逆性 —— 把"命令危险吗"换成"**被写的对象能不能重建**"，真实工作区实测可重建 **85.7%**、说不清 **8.2%**（就是开判据后要问人的那部分）。
- **锚可自检**：`python -m cli.ace_mandate issue ...` 签一张**授权令**（一次任务一张，签名用同一个锚），贴进配置的 `mandate` 键之后，"项目外已存在对象的确认"与 `edit_file`/`terminal_exec` 的逐次确认不再逐次弹窗 —— 实测同样 5 次项目外写：**不配令 5 次确认 → 配令 0 次**，配额只给 2 时仍有 3 次（额度是真边界）。`python -m cli.ace_doctor` 报告锚路径、已有密钥、锚根来源、锚是否误落在工作区内、项目内是否还残留旧密钥副本。

## 升级注意

| 变化 | 影响 |
|---|---|
| 签名密钥移出项目目录 | 首次启动自动迁移；旧快照仍验得过 |
| 锚不可写 → 写操作被拒 | 这是 fail-close 不是 bug；`ace doctor` 会说明锚的状态 |
| 会话日志多 `mac` 字段 | 老日志判 `unverifiable`，如实 |
| `/audit stats` 多两行 | 台账整链 + 两条测量，均注明"未参与裁决" |
| 新增配置键 `mandate` | **不配就什么都没有**（行为与以前逐字相同）；配了才收拢逐次确认 |

## 验证到什么程度

- 端到端套件新增 **34 条**回归断言（`test_all` 段 `[71]`），每条对应一个先复现过的缺陷或一条踩出来的口径；全量以 `python test_all.py` 输出为准。
- 关键前后对照：修复前"改内容+修摘要+用项目内密钥重签" → 快照 `verify=True`；修复后 → `verify=False`。
- 开销量过：单条 MAC **6.5 µs**；`append` 整条路径 11.4 ms/条，绝大部分是既有的 `os.fsync`。

## 已知未验证

- 两条判据的**翻判**未做（来源归属需要模型侧引用=协议改动；可逆性需要清单逐条看过），要有真会话数据。
- 锚落在不可写目录时写操作被拒（受限环境实测如此，行为正确但陡峭）—— 用 `ACE_ANCHOR_DIR` 指到可写位置。
- POSIX 路径与 `0600` 有断言但**无实机冒烟**（本机 Windows）。

**完整细节** → [`docs/RELEASE-NOTES-v3.43.0.md`](docs/RELEASE-NOTES-v3.43.0.md) · [`CHANGELOG.md`](CHANGELOG.md)
**设计文档（含每条的前置门与"明确不做"）** → [`docs/design/RGTC-LANDING.md`](docs/design/RGTC-LANDING.md)
**架构图（Mermaid，GitHub 直接渲染）** → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

本项目有一条纪律：**没真正跑过的，不许说成"应该没问题"。**

---

## English

> This doubles as the v3.43.0 release note — paste it into the Release as-is.
> One-line summary: **a forgeable pre-write snapshot is fixed** (signing key moved out of the workspace) · **the session ledger is now chained** (edits, deletions and insertions are all visible) · **two criteria that would change verdicts are measured first, not enforced**.

Artifacts are unchanged from v3.42.0 (five executor platforms plus a Windows bundle). **No verdict changes in this version** — both criteria are measurement-only; the two new `/audit stats` lines predict what an enforced rule *would* do.

## What this version gives you

- **Snapshots can no longer be forged** (defect reproduced first): the key used to live in `<project>/.guardian/signing_key`, and `.guardian` sits inside the project — so anyone who could read and write the project directory could read the key, tamper with the copy, fix the digests, re-sign, and `verify_snapshot()` still returned `True`. The key now lives in an anchor directory **outside the workspace**, with automatic migration (**moved**, not copied); when the anchor is unusable, writes are refused (fail-close) instead of quietly producing unsigned snapshots.
- **The audit record can no longer be rewritten**: every event carries `mac = HMAC(ledger key, previous mac ‖ body)` — editing a line, deleting a middle entry, stripping a signature, or appending a forged line all make `/audit stats` report `broken` and name the position; old logs are reported honestly as `unverifiable` (never as ok, never wrongly as broken).
- **Measurement first for two criteria**: ① source attribution — the same delete, paired with "the user asked", "the instruction came from content we read", or "the user never mentioned it", still gets **identical verdicts today** (that is the reproduced defect); this version starts recording whether the target was ever mentioned by the user. ② reversibility — replacing "is this command dangerous" with "**can the written object be rebuilt**": measured across the real workspace, 85.7% is recoverable, 8.2% is unclassifiable (exactly what would start prompting).
- **The anchor is now inspectable**: `python -m cli.ace_mandate issue ...` signs a **mandate** (one per task, signed with the same anchor); paste it into the `mandate` config key and the "outside-project object" confirmation plus the per-call `edit_file`/`terminal_exec` confirmations stop prompting — measured on the same 5 outside writes: **5 prompts without a mandate → 0 with one**, and 3 remain when the quota is only 2 (the quota is a real bound). `python -m cli.ace_doctor` likewise reports the anchor path, which keys exist, where the root comes from, whether it mistakenly sits inside the workspace, and whether a stale in-project key copy lingers.

## Upgrade notes

| Change | Effect |
|---|---|
| Signing key moved out of the project directory | Automatic one-time migration on first start; old snapshots still verify |
| Unwritable anchor ⇒ writes refused | That is fail-close, not a bug; `ace doctor` explains the anchor state |
| Session events gained a `mac` field | Old logs report `unverifiable` — honestly |
| `/audit stats` gained two lines | Ledger chain plus the two measurements, both marked "not enforced" |
| New config key `mandate` | **Absent means nothing changes** (byte-identical behaviour); present means per-call confirmations collapse into one mandate per task |

## How far it is verified

- 34 new regression assertions (section `[71]`), each tied to a defect reproduced first or a criterion the tests forced us to state precisely; `python test_all.py` output is authoritative.
- Key before/after: "edit + fix digest + re-sign with the in-project key" verified `True` before, `False` after.
- Costs measured: 6.5 µs per MAC; 11.4 ms per `append` end-to-end, dominated by the pre-existing `os.fsync`.

## Known unverified items

- Enforcing either criterion is **not** done (attribution needs a model-side citation, i.e. a protocol change; reversibility needs the list reviewed item by item) — both require real session data.
- With an unwritable anchor, writes are refused (observed in a constrained environment; correct but steep) — point `ACE_ANCHOR_DIR` at a writable location.
- POSIX paths and `0600` are asserted but have **no native smoke test** (this machine is Windows).

**Full details** → [`docs/RELEASE-NOTES-v3.43.0.md`](docs/RELEASE-NOTES-v3.43.0.md) · [`CHANGELOG.md`](CHANGELOG.md)
**Design doc (preconditions and explicit non-goals)** → [`docs/design/RGTC-LANDING.md`](docs/design/RGTC-LANDING.md)
**Architecture diagram (Mermaid, rendered by GitHub)** → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

The project has one rule: **anything not actually run does not get described as "should be fine".**

---

**Source** · [Repository](https://github.com/ace-code-engine/ace-agent) · [README](https://github.com/ace-code-engine/ace-agent#readme) · [Getting started](docs/GETTING-STARTED.md) · [Security model](docs/SECURITY-MODEL.md) · [Release notes](docs/RELEASE-NOTES-v3.43.0.md) · [Changelog](CHANGELOG.md)
