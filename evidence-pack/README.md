# ACE 公开时间线证据包

> **这是什么**：ACE 公开 commit / tag / release / 远程元信息的**可复核**时间线取证材料，供写技术文章时引用。每条结论都落到一条命令或一个 `RAW/` 文件。
> **先看哪个**：要引用事实 → §一 ｜ 怕写错 → §二 ｜ 要找文件 → §三 ｜ 要自己复核 → §四 ｜ 要原始材料 → `RAW/`（清单见 `RAW/00_INDEX.md`）。
> 30 个文件 = 9 份 `.md` + `RAW/` 21 份。采集于 **2026-09-25**（当时 HEAD `be2d03f`）。

---

## ⚠️ 首要声明

**本证据包的内容全部来自公开 git 仓库记录，不构成对任何机构或个人的抄袭指控。**

补充限定（逐条请勿删改引用）：

1. 本证据包呈现的是**公开可见时间**，**不代表任何项目的内部研发起点**。commit 时间反映代码被提交的时间；arXiv `Submitted on` 反映预印本提交时间。两者都不是构思或研发的起点。
2. 本证据包**不对** ACE 与 DeepSeek DSec 论文之间的关系作任何判断（因果、相关、借鉴与否均不在支持范围内）。`EXTERNAL_REF.md` 与 `TIMELINE.md` 只并列时间坐标。
3. 本证据包**未联网抓取** GitHub Releases 页面与 GitHub API。所有未采集项已逐条标注为「未采集 / 无法验证」，**未以推测填充**。
4. 任务描述中对三个版本的定性存在两处不准确，已在 `VERSIONS.md` 与 `RELEASES.md` 头部如实标出，并按实际情况书写。**不替原始记录润色。**

> 第 3 条有一半已失效（原文照留）：为验证仓库转移，后来**取用了 GitHub API**（`RAW/transfer_evidence.txt`）。Releases 页面仍未采集。

---

## 一、核心事实

| 结论 | 值 | 出处 |
|---|---|---|
| 最早**公开可验证** commit | 2026-08-19 20:32:46 +0800，`549db57` | `RAW/commits_earliest.txt` |
| 仓库创建（GitHub `created_at`） | 2026-08-19T12:31:22Z，比首提交早 **1 分 24 秒** | `RAW/transfer_evidence.txt` |
| 采集时规模 | **284** commit ／ **48** tag（本机 clone 只有 46）／ 跨度约 37 天 | `RAW/repo_meta.txt`・`RAW/tags_remote.txt` |
| 「P0 安全批」真实落点 | 2026-09-05，`554cb6f` + `80b974b` —— **属 v3.2，未打 tag** | `RAW/changelog_v3.2.txt` |
| 安全审计 19 条对账 | 2026-09-18，19 条全有结论，唯一新发现 SEC-009 | `RAW/security_audit_reconcile.txt` |
| 外部对比对象公开时间 | 2026-09-19 12:20:26 UTC，`arXiv:2609.22978` v1 | `EXTERNAL_REF.md` |
| 仓库转移（个人账户 → 组织） | **已确证** | `RAW/transfer_evidence.txt` |
| 账户公开贡献 | 2026 年 **377** 次；Contributors 页 **156** commits、**+38,776 / −8,221** | `CONTRIBUTIONS.md` |

**两条时间关系**：P0 安全批（09-05）早于 DSec 公开（09-19）**14 天**；`docs/SECURITY-AUDIT.md` 首轮 **08-22**。

**⚠️ 计数有三种口径，不可混用**：`377`（贡献图·账户全部公开贡献）、`156`（Contributors 页·`main`、排除 merge、限区间）、`284`（`git rev-list`·全部提交）。三者互不印证也互不否定 —— 详见 `CONTRIBUTIONS.md` §七。

---

## 二、能写 / 不能写

**✅ 能写**：最早可验证 commit 2026-08-19（须写成「**公开可验证**」，不能写「项目始于」）／仓库创建于 08-19 ／P0 安全批早于 DSec 14 天 ／仓库由个人账户 **transfer** 而来 ／采集时 284 commit、48 tag。

**❌ 不能写**：

| 不能写 | 原因 |
|---|---|
| **ACE 与 DSec 有借鉴 / 因果 / 关联** | 本包不作此判断，也**不提供支持该结论的证据** |
| 转移的**具体日期**、账户在组织中的**角色**、转移前可见性 | 公开数据不提供 |
| 用贡献图证明「从个人账户迁移到组织」 | 贡献图/Contributors 页**不含仓库维度、不显示组织归属** |
| 账户在 2026-07-14 之前有公开活跃期 | 实测该日前全年为 0 |
| 「v3.3 是 P0 安全批」 | 实为 **v3.2**，且未打 tag |
| 「v3.10.1 是 real-model smoke test 修复」 | 冒烟是**发现手段**；主题是协议纠错死锁 / 执行器 Tier-1 降级 / 启动器 CRLF |
| 「`v3.7.0` / `v3.41.0` 没有 tag」 | **两者都有** —— 见下 |

> ⚠️ **本包曾误判，已更正（勿沿用旧版结论）**：旧版据**本机 clone** 的 tag 引用断言 `v3.7.0`、`v3.41.0`「不存在」——**两者都存在**，且是**轻量 tag**。
> **硬规则**：任何「某 tag 不存在」的断言，**必须用 `git ls-remote --tags origin` 验证** —— 本机 clone 的 tag 引用会**静默落后**（本地 46 / 远端 48）。出处：`RAW/tags_remote.txt`。
>
> **取证范围边界**：只覆盖**时间线 / tag / release / 远程元信息 / 外部对象公开时间**。ACE 的技术主张（依赖策略、安全模型、性能数字等）**不在本包范围内**，请另行取证。

---

## 三、文件导航

| 想看什么 | 看哪个 |
|---|---|
| 时间线总表（升序，每行附出处） | `TIMELINE.md` |
| 全部 tag + 命名规律 | `TAGS.md` |
| v3.3 / v3.8.0 / v3.10.1 的真实内容 | `VERSIONS.md` |
| release notes 清单与摘录 | `RELEASES.md` |
| 最早 20 条 commit | `COMMITS_EARLIEST.md` |
| remote、规模、迁移说明 | `REMOTE_INFO.md` |
| 外部对象公开时间（只写事实） | `EXTERNAL_REF.md` |
| 贡献数据与逐日对账 | `CONTRIBUTIONS.md` |
| **原始输出**（18 份命令输出 + 索引 + 2 份截图证据） | `RAW/`，权威清单见 `RAW/00_INDEX.md` |

**不确定项（勿当事实）**：`v3.7` / `v3.8` **裸名** tag 不存在（实为 `v3.7.0` / `v3.8.0`）｜本机 clone 的 46 个 tag ≠ 仓库的 48 个｜v3.3・v3.8・v3.10.1 无独立 `RELEASE-NOTES`｜CHANGELOG 无 `## [v3.8]` 段｜GitHub Releases 页面未采集｜转移的发生日期・转移前可见性・组织角色无法验证｜采集时工作区改动清单无法事后重建。

---

## 四、复核与注意

```bash
git ls-remote --tags origin                    # ⚠️ tag 必须查远端 → RAW/tags_remote.txt
git rev-list --count HEAD                      # → RAW/repo_meta.txt
git show --stat 554cb6f ; git show --stat 80b974b   # P0 安全批两个 commit
git checkout be2d03f                           # 复现采集时状态
```
其余逐项命令在各文件自己的「复核」段与 `RAW/00_INDEX.md` 末尾。

1. **仓库在活动开发中** —— 采集时 ahead 11，本包移入仓库时已到 286 commit。
2. **凡引用数字，都带「截至 2026-09-25」的限定。** 时区：git `+0800`、arXiv `UTC`；本包 `.md` 为 UTF-8（PowerShell 读中文需 `-Encoding UTF8`）。
3. **数据完整性**：`RAW/` 命令输出**未改写**；原始记录里的矛盾表述**两者并列保留，不统一口径**。全包**无 token / 密钥 / 私密 URL**；唯一个人信息是公开账号名与其 GitHub **noreply** 地址。
4. **本包位置**：`evidence-pack/`，已登记进 `docs/ARCHITECTURE.md` 的权威树（`test_all.py` 的 `[38]` 段校验仓库根级条目）。
