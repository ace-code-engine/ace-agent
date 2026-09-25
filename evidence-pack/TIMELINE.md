# 公开时间线总表

- **本表只收录可溯源事件**：每一行都必须在 `RAW/` 或对应 `.md` 中找到出处。
- **时间口径**：一律 ISO 8601、带时区（`+0800` 为本机/仓库提交时区，`UTC` 为 arXiv 时区）。
- **数据来源**：`RAW/commits_earliest.txt`、`RAW/tags.txt`、`RAW/tag_*.txt`、`RAW/changelog_*.txt`、`RAW/security_audit_reconcile.txt`、`RAW/repo_meta.txt`、`RAW/snapshot_env.txt`

---

## ⚠️ 两条必须先读的限定

1. **这里的「时间」是公开可见时间。** commit 时间反映的是**代码被提交的时间**，arXiv `Submitted on` 反映的是**预印本向 arXiv 提交的时间**。**两者都不代表构思、研发或内部完成的起点。**

2. **本表并列 ACE 与 DSec 只为提供时间坐标。** 本证据包**不对两者之间的关系作任何判断**，也不构成任何指控。ACE 的时间线中还包含大量与 DSec 无关的独立开发活动（UI 重构、i18n、MCP 客户端、打包等）。

---

## 时间线总表（按日期升序）

| 日期 (ISO 8601) | 事件 | 来源 | 证据位置 |
|---|---|---|---|
| 2026-08-19 20:32:46 +0800 | **ACE 最早可验证 commit**：`549db57` 「ACE v1.0: AI Code Engine - 沙盒 Agent 执行层 + 命令行终端」 | `git log --reverse` | `RAW/commits_earliest.txt` 第 3 行；`COMMITS_EARLIEST.md` |
| 2026-08-19 20:32–20:53 +0800 | 奠基 4 连提交（执行层/终端 → 首页 → mock 切换修复 → README 重构），约 21 分钟内 | 同上 | `RAW/commits_earliest.txt` 第 3–6 行 |
| 2026-08-20 11:53:03 +0800 | 首个 CI 工作流落地（3.10–3.12 矩阵 + `test_all.py` + ruff 安全子集） | `git log` | `RAW/commits_earliest.txt` 第 7 行 |
| 2026-08-21 15:19:14 +0800 | 原生工具调用 / Plan Mode / 权限申请 / `@` 快捷方式 | `git log` | `RAW/commits_earliest.txt` 第 16 行 |
| **2026-09-05 17:03:09 +0800** | ⭐ **P0 安全批（第一批）**：`554cb6f`「fix(security): P0 安全批 - SEC-01 沙箱引用级拦截/别名lambda脱壳, SEC-02 parse_document 越界与 file_read 同口径, SEC-03 agent_runner 默认 readonly」 | `git log` | `git show 554cb6f`；`RELEASES.md` §2 v3.2；`RAW/changelog_v3.2.txt` |
| 2026-09-05 17:11:47 +0800 | ⭐ **P0 安全批（第二批）**：`80b974b`「fix(security): SEC-04 快照签名默认开启+敏感文件不进快照, SEC-05 browser_screenshot 降权, SEC-06 execpolicy git config/--opt路径」 | `git log` | `git show 80b974b`；同上 |
| 2026-09-05 17:38:10 +0800 | v3.3 release commit `bbd02c9`「release(v3.3): 工程化质量收尾」 | `git show v3.3` | `RAW/tag_v3.3.txt`；`VERSIONS.md` §1 |
| **2026-09-05 17:38:17 +0800** | ⭐ **tag `v3.3` 创建**（第 1 个 tag） | `for-each-ref` | `RAW/tags.txt` 第 3 行；`TAGS.md` |
| 2026-09-05 21:14:22 +0800 | tag `v3.6` 创建（该日 4 个 tag 的最后 1 个） | `for-each-ref` | `RAW/tags.txt` 第 6 行 |
| 2026-09-06（CHANGELOG 段） | CHANGELOG `## [v3.7]` 段；该版本**有 tag**：`v3.7.0`（**轻量 tag**，指向 `37f9dfe`，2026-09-06 13:58:00 +0800）。⚠️ 原版写「**该版本未打 tag**」，**已更正** | `CHANGELOG.md` 第 1606 行、`git ls-remote --tags origin` | `RELEASES.md` §3；`TAGS.md` 命名规律节、`RAW/tags_remote.txt` |
| **2026-09-18 19:51:03 +0800** | ⭐ **tag `v3.8.0` 创建**：「文档与安全承诺守卫、审计 19 条对账、场景示例（P1 全清）」 | `for-each-ref` + `git tag -n99` | `RAW/tags.txt` 第 7 行；`RAW/tag_v3.8.0.txt`；`VERSIONS.md` §2 |
| 2026-09-18（同日） | ⭐ **安全审计 19 条对账**（`docs/SECURITY-AUDIT.md`「对账状态（v3.8 复核，2026-09-18）」节）：19 条全部有结论，唯一新发现为 SEC-009 | `docs/SECURITY-AUDIT.md` 第 14–42 行 | `RAW/security_audit_reconcile.txt`；`VERSIONS.md` §2 |
| 2026-09-18 20:17:02 / 20:29:00 / 20:43:02 / 20:45:34 +0800 | tag `v3.8.1` / `v3.8.2` / `v3.8.3` / `v3.8.4`（同日 4 个补丁 tag） | `for-each-ref` | `RAW/tags.txt` 第 8–11 行 |
| 2026-09-18 21:04:16 +0800 | tag `v3.9.0`「P2 结构重构落地」 | `for-each-ref` | `RAW/tags.txt` 第 12 行 |
| 2026-09-18 22:24:38 +0800 | tag `v3.10.0`「根目录瘦身 ui/cli/core + README 英文为主」 | `for-each-ref` | `RAW/tags.txt` 第 13 行 |
| **2026-09-19 10:36:13 +0800** | v3.10.1 release commit `7b3dbd3`「chore(release): v3.10.1 —— 协议纠错死锁 / 执行器 Tier-1 降级 / 启动器 CRLF」 | `git show v3.10.1` | `RAW/tag_v3.10.1.txt`；`VERSIONS.md` §3 |
| **2026-09-19 10:37:09 +0800** | ⭐ **tag `v3.10.1` 创建** | `for-each-ref` | `RAW/tags.txt` 第 14 行；`TAGS.md` |
| 2026-09-19（该版本记录） | ⭐ v3.10.1 修复的缺陷由**真机冒烟**暴露：模型连续 5 轮拒绝改格式、第 6 轮被 `STALL_ABORT_ROUNDS` 中止，系统曾把责任归给模型 | `CHANGELOG.md` 第 1485 行起 | `RAW/changelog_v3.10.1.txt`；`VERSIONS.md` §3「关于 real-model smoke test 的准确表述」 |
| 2026-09-19 11:39:02 +0800 | tag `v3.11.0`「容器档运行参数加固 + 可选镜像拉取 + CI 容器 smoke」 | `for-each-ref` | `RAW/tags.txt` 第 15 行 |
| 2026-09-19 18:13:38 – 20:32:05 +0800 | 同日密集发布：`v3.11.1` → `v3.21.0`（共 11 个 tag，约 2 小时 19 分） | `for-each-ref` | `RAW/tags.txt` 第 16–27 行 |
| **2026-09-19 12:20:26 UTC**（= 20:20:26 +0800） | ⭐ **DeepSeek DSec 论文 v1 提交至 arXiv**（`arXiv:2609.22978`，cs.DC，31 页 13 图） | arXiv abs 页面 | `EXTERNAL_REF.md` |
| **2026-09-19**（日期口径） | ⭐ DSec 论文 arXiv 公开提交日期（`Submitted on 19 Sep 2026`） | arXiv abs 页面 | `EXTERNAL_REF.md` |
| 2026-09-22 19:54:38 – 22:54:47 +0800 | 发布 `v3.22.0` → `v3.31.0`（10 个 tag，UI/交互/授权规则主题） | `for-each-ref` | `RAW/tags.txt` 第 28–37 行 |
| 2026-09-23 20:02:59 – 22:01:07 +0800 | 发布 `v3.32.0` → `v3.37.0`（Textual 全屏界面、运行环境、演示图守卫） | `for-each-ref` | `RAW/tags.txt` 第 38–44 行 |
| 2026-09-24 04:32:12 / 05:00:41 +0800 | tag `v3.38.0`（与 Claude 对齐：行编辑/撤销/Esc 两态）/ `v3.39.0`（主页·功能面板·两段式回溯） | `for-each-ref` | `RAW/tags.txt` 第 45–46 行 |
| 2026-09-24 21:52:11 / 23:04:17 +0800 | tag `v3.40.0` / `v3.40.1`（终端编码防线）。⚠️ 原版称这两个是「最后两个 tag」，**已更正**（最后一个见下一行） | `for-each-ref` | `RAW/tags.txt` 第 47–48 行 |
| **2026-09-25 01:36:37 +0800** | ⭐ **tag `v3.41.0` 创建**（**轻量 tag**，指向 `d09ee80`「fix(packaging): 脚本里的中文注释弄红 CI 第三次 —— 加提交前自检门」）。⚠️ 这是**仅有的两个「本机 clone 缺失、远端存在」的 tag** 之一 —— 原版因此漏了它 | `git ls-remote --tags origin` | `RAW/tags_remote.txt`；`TAGS.md`「远端多出的 2 个 tag」 |
| 2026-09-25 22:47:27 +0800 | **采集时最新 commit** `be2d03f`「test(H-22): 两条守卫把「REQUIRED 长大而 vendor/ 没跟上」变成红灯」 | `git log -1` | `RAW/snapshot_env.txt`；`REMOTE_INFO.md` §2 |
| 2026-09-25 22:51:44 +0800 | **本证据包采集时刻**（HEAD `be2d03f`，`main` ahead 11） | 采集 | `RAW/snapshot_env.txt` |

---

## 关于「ACE 与 DSec 在时间上接近」这一点

上表显示：**2026-09-19 12:20:26 UTC（20:20:26 +0800）DSec 提交 arXiv**，而 ACE 当天（+0800）发布了 `v3.11.0`（11:39）到 `v3.21.0`（20:32）共 11 个 tag。

**本证据包只并列这两个时间坐标，不作任何因果或相关性推断。** 说明：

- ACE 在 2026-09-19 当天发布的内容（容器参数加固、选择器排版、`/expand`、上下文占比、首屏重构、工具可视化、输入体验、MCP 客户端、扩展点、headless 事件流、会话管理、改动审阅）**与该日 DSec 论文主题（集群级沙箱基础设施）无对应关系**。逐项内容见 `RAW/tags.txt` 第 15–27 行。
- ACE 的 P0 安全批发生在 **2026-09-05**，早于 DSec 论文公开 **14 天**。逐条 commit 见本表 2026-09-05 两行。
- ACE 的核心安全文档 `docs/SECURITY-AUDIT.md` 的首轮为 **2026-08-22**（该文件第 16 行自述「2026-08-22 首轮 + 同日复审」），同样早于 DSec 公开。

**任何超出「时间先后」的推论都不在本证据包的支持范围内。** 若文章需要更强的判断，应另行补充证据。

---

## 本表的不确定项（未找到 / 无法验证 / 已确证）

> **标题原为「未找到 / 无法验证」项，但表内已含 ✅ 已确证行**，名实不符，已改为中性标题。**写文章时请勿把非 ✅ 项当作事实。**

| 项 | 状态 | 说明 |
|---|---|---|
| `v3.8` 这个精确 tag 名 | **不存在** | 只有 `v3.8.0`–`v3.8.4`。见 `TAGS.md` |
| `v3.7.0` tag | ✅ **存在**（原「不存在」**已推翻**） | 轻量 tag，指向 `37f9dfe`（2026-09-06 13:58:00 +0800）。**原版错在只查了本机 clone 的 tag 引用**（本地 46 / 远端 48）。出处：`RAW/tags_remote.txt` |
| v3.3 / v3.8 / v3.10.1 的独立 `RELEASE-NOTES` 文件 | **未找到** | 仓库内 release notes 从 `v3.11.0` 开始。见 `RELEASES.md` §1 |
| CHANGELOG 中的 `## [v3.8]` 段 | **未找到** | 尽管 v3.8.0 的 release commit 声称「拆出 v3.8 段」。见 `RELEASES.md` §3 |
| GitHub Releases 页面内容 | **未采集** | 未联网抓取。见 `RELEASES.md` §4 |
| GitHub 仓库 `created_at` | ✅ **已采集**：`2026-08-19T12:31:22Z` | 见 `REMOTE_INFO.md` §3.3 |
| 「个人账户 → 组织」transfer 操作本身 | ✅ **已验证**（原「无法验证」已推翻） | 证据：**两份 clone 最早 commit hash 相同**（`549db57`）+ **旧 URL 301 重定向到组织仓库**。见 `REMOTE_INFO.md` §3.2、`RAW/transfer_evidence.txt` |
| transfer 的**发生日期** | **无法验证** | 公开数据不提供；`created_at` 保留的是原始创建时间 |
| `v3.7`（精确名，无 `.0`）为何不存在 | **不作推断** | 实际只有 `v3.7.0`。只记录差异 |
| `v3.41.0` tag | ✅ **存在**（轻量 tag，指向 `d09ee80`） | 本机 clone 缺失、远端存在。出处：`RAW/tags_remote.txt` |

### 转移时间线补充（2026-08-19）

| 日期 (ISO 8601) | 事件 | 来源 | 证据位置 |
|---|---|---|---|
| 2026-08-19 12:31:22 UTC（= 20:31:22 +0800） | 仓库 `created_at`（原始创建时间；transfer 后被保留） | GitHub API | `RAW/transfer_evidence.txt` 证据 3 |
| 2026-08-19 20:32:46 +0800 | 首次提交（比 `created_at` 晚 1 分 24 秒） | `git log --reverse` | `RAW/commits_earliest.txt` |
| 日期不明 | 仓库由个人账户 `jincheng3870682453-hash` **转移**至组织 `ace-code-engine` | 旧 URL 301 重定向 + 仓库 `id` 相同 | `RAW/transfer_evidence.txt` 证据 1、2 |

---

## 复核方式

```bash
cd <仓库路径>

# 最早 20 条 commit
git log --reverse --format="%H|%ad|%an|%s" --date=iso | head -20

# 全部 tag
git for-each-ref --sort=creatordate \
  --format='%(refname:short)|%(creatordate:iso)|%(objectname:short)|%(subject)' refs/tags

# P0 安全批的两个真实 commit
git show --stat 554cb6f
git show --stat 80b974b

# 三个点名版本
git show --stat --format="%H%n%ad%n%s%n%b" --date=iso v3.3
git show --stat --format="%H%n%ad%n%s%n%b" --date=iso v3.8.0
git show --stat --format="%H%n%ad%n%s%n%b" --date=iso v3.10.1

# 19 条对账
sed -n '14,42p' docs/SECURITY-AUDIT.md

# 确认 v3.8（精确名）不存在、而 v3.7.0 存在
# ⚠️ 必须查【远端】：本机 clone 的 tag 引用可能落后 —— 本次实测落后 2 个（v3.7.0、v3.41.0）
git ls-remote --tags origin | grep -E 'refs/tags/v3\.(7|8)'
#   ↑ 应看到 refs/tags/v3.7.0 与 refs/tags/v3.8.0；不应看到裸 v3.7 / v3.8
git tag -l 'v3.8'    # 本机预期：无输出（远端同样没有）
git tag -l 'v3.7*'   # ⚠️ 本机可能无输出 —— 那是 clone 落后，【不代表仓库没有】

# 仓库规模与状态
git rev-list --count HEAD
git status -sb
```
