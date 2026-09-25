# ACE 公开时间线证据包

> 用于撰写技术文章的**时间线证据**。**28 个文件** = 9 份 `.md` + `RAW/` 19 份；其中 **22 个 / 76.6 KB 从未改动**。
> 首次采集 **2026-09-25 22:51:44 +08:00**（HEAD `be2d03f`）；最后修订 **2026-09-25 23:27**。
> 位置：`G:\AI_Project\ace\evidence-pack\`（**仓库内**，已登记进权威树；见 §三）。
>
> ⚠️ 这是一份**时间点快照**。仓库仍在开发，现在重跑本包任何命令都会得到不同结果。**动笔前先读 §二末与 §五。**

---

## ⚠️ 首要声明

**本证据包的内容全部来自公开 git 仓库记录，不构成对任何机构或个人的抄袭指控。**

补充限定（逐条请勿删改引用）：

1. 本证据包呈现的是**公开可见时间**，**不代表任何项目的内部研发起点**。commit 时间反映代码被提交的时间；arXiv `Submitted on` 反映预印本提交时间。两者都不是构思或研发的起点。
2. 本证据包**不对** ACE 与 DeepSeek DSec 论文之间的关系作任何判断（因果、相关、借鉴与否均不在支持范围内）。`EXTERNAL_REF.md` 与 `TIMELINE.md` 只并列时间坐标。
3. 本证据包**未联网抓取** GitHub Releases 页面与 GitHub API。所有未采集项已逐条标注为「未采集 / 无法验证」，**未以推测填充**。
4. 任务描述中对三个版本的定性存在两处不准确，已在 `VERSIONS.md` 与 `RELEASES.md` 头部如实标出，并按实际情况书写。**不替原始记录润色。**

> **第 3 条有一半已失效（原文照留）**：为验证仓库转移，后来**取用了 GitHub API**（`RAW/transfer_evidence.txt`）与贡献图接口（`RAW/contributions_jogruber.txt`）。Releases 页面仍未采集；「未以推测填充」仍成立。

---

## 一、核心事实（可直接引用）

| 结论 | 值 | 出处 |
|---|---|---|
| 最早**公开可验证** commit | 2026-08-19 20:32:46 +0800，`549db57` | `RAW/commits_earliest.txt` |
| 仓库创建（GitHub `created_at`） | 2026-08-19T12:31:22Z，比首提交早 **1 分 24 秒** | `RAW/transfer_evidence.txt` |
| 采集时规模 | **284** commit / **48** tag（本机 clone 只有 46）/ 跨度约 37 天 | `RAW/repo_meta.txt`、`RAW/tags_remote.txt` |
| 作者标识 | 唯一 1 个，为 GitHub **noreply** 匿名化形式 | `RAW/repo_meta.txt` |
| 「P0 安全批」真实落点 | 2026-09-05 17:03 / 17:11，`554cb6f` + `80b974b`（**属 v3.2，未打 tag**） | `RAW/changelog_v3.2.txt` |
| 安全审计 19 条对账 | 2026-09-18，19 条全部有结论，唯一新发现 SEC-009 | `RAW/security_audit_reconcile.txt` |
| 外部对比对象公开时间 | 2026-09-19 12:20:26 UTC，`arXiv:2609.22978` v1，cs.DC | `EXTERNAL_REF.md` |
| 仓库转移（个人账户 → 组织） | **已确证** | `RAW/transfer_evidence.txt` |
| 账户公开贡献 | 2026 年 **377** 次；**2026-07-14 之前全年为 0** | `CONTRIBUTIONS.md` §1 |

**两条时间关系**：P0 安全批（09-05）早于 DSec 公开（09-19）**14 天**；`docs/SECURITY-AUDIT.md` 首轮 **08-22**。

> 所有计数都是**采集时值**，引用必须带「截至 2026-09-25」。

---

## 二、能写什么、不能写什么

**✅ 可以写**：最早可验证 commit 2026-08-19（须写成「**公开可验证**」，不能写「项目始于」）/ 仓库创建于 08-19 / P0 安全批早于 DSec 14 天 / 仓库由个人账户 **transfer** 而来（hash 相同 + 301 重定向 + id 相同）/ 采集时 284 commit、48 tag（带日期限定）/ 贡献图与 git 逐日吻合（16 个活动日中 10 日完全相等）。

**❌ 不可以写**：

| 不能写 | 原因 |
|---|---|
| **ACE 与 DSec 有借鉴 / 因果 / 关联** | 本包不作此判断，也**不提供支持该结论的证据** |
| 转移的**发生日期**、该账户在组织中的**角色**、转移前可见性 | 公开数据不提供 |
| 用贡献图证明「从个人账户迁移到组织」 | 贡献图**不含仓库维度、不显示组织归属** |
| 账户在 2026-07-14 之前有公开活跃期 | 实测该日前全年为 0 |
| 「v3.3 是 P0 安全批」 | 实为 **v3.2**，且未打 tag |
| 「v3.10.1 是 real-model smoke test 修复」 | 冒烟是**发现手段**；主题是协议纠错死锁 / 执行器 Tier-1 降级 / 启动器 CRLF |
| 「`v3.7.0` / `v3.41.0` 没有 tag」 | **两者都有** —— 见下 |

### ⚠️ 本包曾误判（已更正，勿沿用旧版结论）

旧版据**本机 clone** 的 tag 引用断言 `v3.7.0`、`v3.41.0`「不存在」。**两者都存在**，且是**轻量 tag**（远端 48 个 tag，本机 clone 只有 46 个）。

> **硬规则**：任何「某 tag 不存在」的断言，**必须用 `git ls-remote --tags origin` 验证** —— 本机 clone 的 tag 引用会**静默落后**。出处：`RAW/tags_remote.txt`。

> **取范围边界**：本包只覆盖**时间线 / tag / release / 远程元信息 / 外部对象公开时间**。ACE 的技术主张（依赖策略、安全模型、性能数字等）**不在本包取证范围内**，请另行取证。

---

## 三、位置说明

```
G:\AI_Project\ace\evidence-pack\
```

**本包最初落在仓库之外**（`C:\Users\69215\Desktop\evidence-pack\`）—— 因为任务同时要求「输出 `./evidence-pack/`」与「**不修改仓库任何文件**」，两条在字面上冲突。**后经仓库所有者决定移入仓库**，并已登记进 `docs/ARCHITECTURE.md` 的权威树（`test_all.py` 的 `[38]` 段会校验仓库根级条目）。

**采集时校验（历史记录，不是当前状态）**：采集发生在**移入之前**，那一次**未写入仓库任何文件**。`git status --short` 记为 **3 个**改动文件（`core/canonical.py`、`core/guardian.py`、`execution_layer.py`，见 `RAW/snapshot_env.txt`），HEAD 为 `be2d03f`。

> 旧版此处写「4 个（含 `test_all.py`）**与 RAW 记录一致**」——**与 RAW 不符**（RAW 记的是 3 个）。工作区随后已被提交，该清单**无法事后重建**，已列入 §四。

---

## 四、文件与不确定项

| 文件 | 内容 |
|---|---|
| `TIMELINE.md` | 时间线总表（升序，每行附来源与证据位置） |
| `COMMITS_EARLIEST.md` | 最早 20 条 commit |
| `TAGS.md` | 48 个 tag（远端）、命名规律、远端多出的 2 个 |
| `RELEASES.md` | release notes 清单与关键内容摘录 |
| `VERSIONS.md` | v3.3 / v3.8.0 / v3.10.1 的真实内容 |
| `REMOTE_INFO.md` | remote、规模、迁移说明（分已验证 / 无法验证） |
| `EXTERNAL_REF.md` | DSec 论文公开时间（只写事实） |
| `CONTRIBUTIONS.md` | 贡献图 + git↔贡献图逐日对账（**追加项**） |
| `RAW/` | 19 份原始输出；权威清单见 `RAW/00_INDEX.md` |

**不确定项**（写文章时**勿**当事实）：

| 项 | 状态 |
|---|---|
| `v3.7` / `v3.8` **裸名** tag | ❌ 不存在（远端也没有；实际为 `v3.7.0` / `v3.8.0`） |
| `v3.7.0` / `v3.41.0` tag | ✅ **存在**（原「不存在」已推翻） |
| 本机 clone 的 tag 总数 46 | ⚠️ **≠ 仓库总数**（远端 **48**） |
| v3.3 / v3.8 / v3.10.1 的独立 `RELEASE-NOTES` | ❌ 未找到（该类文件自 v3.11.0 起） |
| CHANGELOG 的 `## [v3.8]` 段 | ❌ 未找到 |
| GitHub Releases 页面内容 | ⬜ 未采集 |
| 转移的发生日期 / 转移前可见性 / 组织角色 | ⚠️ 无法验证 |
| 采集时工作区改动文件的**完整清单** | ⚠️ 无法事后重建（RAW 记 3 个） |
| 账户所属组织 / 仓库列表 | ⬜ 未采集 |
| 任务所称「v3.3 P0 安全批」 | ⚠️ 定性不准确（实为 v3.2） |

---

## 五、复核

```bash
cd G:\AI_Project\ace
git log --reverse --format='%H|%ad|%an|%s' --date=iso | head -20   # → RAW/commits_earliest.txt
git rev-list --count HEAD                                          # → RAW/repo_meta.txt
git show --stat 554cb6f ; git show --stat 80b974b                  # P0 安全批两个 commit
sed -n '14,42p' docs/SECURITY-AUDIT.md                             # 19 条对账
```

| 想确认 | 命令 | 对照 |
|---|---|---|
| **某个 tag 到底存不存在** | ⚠️ `git ls-remote --tags origin \| grep <名字>` | `RAW/tags_remote.txt` |
| 远端 tag 总数 | `git ls-remote --tags origin`（48 个，去掉 `^{}` 皮） | `RAW/tags_remote.txt` |
| 仓库转移 | `curl -s https://api.github.com/repos/jincheng3870682453-hash/ace-agent \| head` | `RAW/transfer_evidence.txt` |
| 其余逐项 | 见 `TIMELINE.md` 与 `RAW/00_INDEX.md` 各自的复核命令段 | —— |

**注意事项**

1. **仓库在活动开发中。** 采集时 `main` 领先 `origin/main` **11 个提交**；本 README 修订时已到 `1f65d7d`（**285** commit、工作树干净、ahead 12）。要复现采集状态：`git checkout be2d03f`。
2. **tag 必须查远端**（见 §二 硬规则）。
3. **编码**：`CHANGELOG.md`、各 `RELEASE-NOTES`、本包 `.md` 为 UTF-8；本机 PowerShell 读中文需 `-Encoding UTF8`。
4. **时区**：git 为 `+0800`，arXiv 为 `UTC`（`2026-09-19 12:20:26 UTC` = `2026-09-19 20:20:26 +0800`）。
5. **凡引用数字，都带「截至 2026-09-25」的限定。**

---

## 六、数据完整性与个人信息

- `RAW/` 下所有文件由 git 命令直接输出，**未经改写**；各 `.md` 的引用段落均为**逐字摘录**。凡互相矛盾的表述（如 v3.3 tag 消息含「P0 安全批」而 CHANGELOG 段落不含），**两者并列保留，不替原始记录统一口径**。
- **`RAW/` 中被动过的只有 2 个**：`00_INDEX.md`（重新生成 —— 它**不再记录自己的体积**，因为自引用清单**永远落后一代**）与 `tags_remote.txt`（新补证据）。其余 **17 份自 22:56:22 起未改动**。校验口径：**行数 = 换行符个数**；`RAW/00_INDEX.md` 对 **18 个非自身文件逐一相符**。
- **个人信息 / 密钥自查**：**无** token / 密钥 / 私密 URL。7 处邮箱形态命中全为公开信息 —— `research@deepseek.com`（论文机构邮箱）×1、`…@users.noreply.github.com`（GitHub **noreply** 匿名化地址）×5、`git@github.com`（API 的 `ssh_url`，**不是邮箱**）×1。
- 全包 28 个文件**无 BOM、无乱码**。

---

## 七、修订记录（简）

| 时间 | 变更 |
|---|---|
| 2026-09-25 22:51–22:56 | 首次采集；追加贡献图对账；追加仓库转移证据（transfer 由「无法验证」改为「已验证」） |
| 23:08–23:15 | 修正 4 处内部不一致（§三 改动文件数、§五 RAW 清单漏列 `transfer_evidence.txt`、§四 标题名实不符、首要声明第 3 条失效）；重新生成 `RAW/00_INDEX.md` |
| 23:17–23:21 | 修正 **2 处假否定**（`v3.7.0` / `v3.41.0`）：新增 `RAW/tags_remote.txt`，更正 `TAGS.md` / `RELEASES.md` / `TIMELINE.md` / 本 README |
| 23:27 | **本 README 精简**（395 行 / 30.7 KB → **162 行 / 11.1 KB**，比原版 188 行还短）：过程记录压进本表，介绍文件只留可用信息。**未改动 `RAW/` 原始输出** |
