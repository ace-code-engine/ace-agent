# 远程仓库元信息

- **数据来源**：`RAW/remote.txt`、`RAW/repo_meta.txt`、`RAW/snapshot_env.txt`
- **采集时间**：2026-09-25 22:51:44 +08:00
- **采集时 HEAD**：`be2d03fd4b226ad08f93b947f8c0068a9cb169e2`

> ⚠️ **本仓库处于活动开发中。** 采集时 `main` 领先 `origin/main` **11 个提交**，且工作区有 3 个文件未提交改动。本证据包是**某一时刻的快照**，后续数字会变化。

---

## 一、当前 remote

原始命令：

```bash
git remote -v
```

原始输出（`RAW/remote.txt`）：

```
origin  https://github.com/ace-code-engine/ace-agent.git (fetch)
origin  https://github.com/ace-code-engine/ace-agent.git (push)
```

| 项目 | 值 |
|---|---|
| remote 名 | `origin` |
| 组织/账户 | **`ace-code-engine`** |
| 仓库名 | `ace-agent` |
| URL | `https://github.com/ace-code-engine/ace-agent.git` |
| 协议 | HTTPS |

采集时仓库中**只有 `origin` 一个 remote**，无 `upstream` 或其他 remote。

---

## 二、时间与规模

原始命令与输出（`RAW/repo_meta.txt`）：

```bash
git rev-list --count HEAD
# 284

git log --reverse --format="%ad" --date=iso | head -1
# 2026-08-19 20:32:46 +0800

git log -1 --format="%ad" --date=iso
# 2026-09-25 22:47:27 +0800
```

| 指标 | 值 |
|---|---|
| 总 commit 数 | **284** |
| 最早 commit 日期 | **2026-08-19 20:32:46 +0800** |
| 最新 commit 日期 | **2026-09-25 22:47:27 +0800** |
| 跨度 | 约 **37 天** |
| tag 总数 | **46** |
| 作者标识去重结果 | **1 个**：`jincheng3870682453-hash <jincheng3870682453-hash@users.noreply.github.com>` |

**作者唯一性**：`git log --format='%an|%ae' | sort -u` 在全部 284 个提交上只返回 **1 条**记录。提交者（`%cn|%ce`）同样是这 1 条。

关于该标识的形式：带 `-hash` 后缀、且邮箱是 `<用户名>@users.noreply.github.com`，是 GitHub 对**未在账户中公开真实姓名/邮箱**的提交所做的匿名化呈现形式。**不能据此推断真实身份**，本证据包也不做此推断。

---

## 三、迁移说明

> **本节已于 2026-09-25 更新**：原「transfer 无法验证」的结论**已被推翻**。仓库转移现已确证，证据见 3.2。原始证据留档：`RAW/transfer_evidence.txt`。

### 3.1 已验证的事实

| 事实 | 证据 |
|---|---|
| 当前 remote 指向 **组织账户** `ace-code-engine` | `RAW/remote.txt` |
| 全部 284 个提交的作者标识唯一，为 `jincheng3870682453-hash` | `RAW/repo_meta.txt` |
| 本机存在另一份 clone：`G:\AI_Project\ai angent`，其 `origin` 为**个人账户** `https://github.com/jincheng3870682453-hash/ace-agent.git` | `git -C "G:\AI_Project\ai angent" remote -v` |
| **两份 clone 的最早 commit hash 完全相同**：`549db5773eddddd46f7f7896d0a8b4d61839c655` | `RAW/transfer_evidence.txt` 证据 4 |
| **个人账户的仓库 URL 被 301 重定向到组织仓库**，且两者 GitHub 仓库 `id` 相同（`1339557972`） | `RAW/transfer_evidence.txt` 证据 1、2 |
| 组织仓库 `created_at` = `2026-08-19T12:31:22Z`（= 20:31:22 +0800），比最早 commit 早 1 分 24 秒 | `RAW/transfer_evidence.txt` 证据 3 |

### 3.2 ✅ 仓库转移已确证（原「无法验证」项已推翻）

**结论**：`ace-code-engine/ace-agent` 确实是由个人账户 `jincheng3870682453-hash` **转移（transfer）**而来。

两条独立证据：

**证据 A — commit hash 相同**

```
个人仓库 clone 最早 commit: 549db5773eddddd46f7f7896d0a8b4d61839c655
组织仓库 clone 最早 commit: 549db5773eddddd46f7f7896d0a8b4d61839c655
```

commit hash 由「内容 + 父提交 + 作者 + 时间戳」计算得出。**两份独立 clone 出现相同 hash，只能是同一份历史**——各自独立提交不可能产生相同 hash。这一条在本机即可复核，无需联网。

**证据 B — 旧 URL 永久重定向 + 仓库 id 相同**

请求 `https://api.github.com/repos/jincheng3870682453-hash/ace-agent`，API 返回的最终对象是 `ace-code-engine/ace-agent`（`id` 同为 `1339557972`）。HTML 页同理。

GitHub **只在仓库被 transfer 之后才保留这种永久重定向**（会保留 stars / watch / fork 与全部历史）。被 fork 出来的仓库**不会**产生反向重定向。

**旁证 C — `created_at` 早于最早 commit 1 分 24 秒**

`2026-08-19T12:31:22Z`（建仓）→ `2026-08-19 20:32:46 +0800`（首次提交）。同日建仓、随即首提交，符合「新建仓库后立刻开始开发」的形态。

### 3.3 仍然无法验证的部分

| 待验证项 | 状态 | 说明 |
|---|---|---|
| **转移发生的具体日期** | **无法验证** | 公开 API 不提供 transfer 时间戳。`created_at` 反映的是**原始创建时间**（transfer 会保留它），不是转移时间 |
| 转移前该仓库的可见性（public / private） | **无法验证** | 公开数据不提供历史可见性 |
| 该账户在 `ace-code-engine` 组织中的角色（owner / member） | **无法验证** | 组织成员列表不公开 |
| 是否存在旧 remote 痕迹（`git reflog` 中的 remote 变更） | **未采集** | 未执行 reflog 扫描；如需要可补。**但转移已由 3.2 的两条证据独立确证，此项不再是必要证据** |

### 3.4 关于「GitHub 页面 created_at 可能是迁移/重建时间」

现已采集到实际值，该提醒**部分**得到印证、**部分**需要修正：

| 原提醒 | 采集后的实际情况 |
|---|---|
| 「`created_at` 可能是迁移/重建时间」 | ❌ **不成立**。`created_at` = `2026-08-19T12:31:22Z`，比最早 commit 仅早 84 秒。**transfer 保留了原始 `created_at`，没有被重置为转移时间** |
| 「本证据包以最早 commit 为准」 | ✅ **保留此判定规则**，但它与 `created_at` 在本例中并不冲突（仅差 84 秒） |

**方法学结论（修正后）**：`created_at` 在 **transfer 场景下保留原始创建时间**，因此它**可以**用来佐证「项目起始时间」；只有在**仓库被删除后重建**的场景下才会重置。本例属于前者。

**判定规则（保留原文，已被上表修正）**：若 `created_at` 与最早 commit 出现较大差异，**以 `git log` 的最早 commit 为准**——`created_at` 反映 GitHub 仓库对象的创建时间，`git log` 反映提交历史时间；重建（re-create）会让 `created_at` 晚于提交历史，而 transfer 不会。

---

## 四、采集时的仓库状态

原始输出（`RAW/snapshot_env.txt`，采集时刻 2026-09-25 22:51:44 +0800）：

```bash
git status -sb
# ## main...origin/main [ahead 11]  M core/canonical.py  M core/guardian.py  M execution_layer.py
```

| 项目 | 采集时刻值 | 复核时刻值（同日稍晚） |
|---|---|---|
| 当前分支 | `main` | `main` |
| 与 origin 的关系 | **ahead 11** | **ahead 11** |
| 未提交改动文件数 | 3 | **8** |
| 工作区是否干净 | ❌ 否 | ❌ 否 |

> **注意**：复核时未提交文件已从 3 个增加到 8 个（新增 `docs/GETTING-STARTED.md`、`docs/INTERFACES.md`、`docs/SECURITY-MODEL.md`、`docs/design/SAFETY-HARDENING.md`，`test_all.py` 亦在内）。**该仓库正在被活跃开发中**，工作区状态随时变化。以 `RAW/snapshot_env.txt` 为准的是采集时刻值。

**写文章注意**：ahead 11 表示**采集时刻**有 11 个提交尚未出现在 GitHub 上。这意味着 GitHub 上可见的历史**落后于**本地历史。若文章引用「最新版本」，应以 GitHub 上的实际可见状态为准，而非本地 HEAD。

**与 GitHub API 的交叉验证**：API 返回 `pushed_at` = `2026-09-25T05:46:56Z`（= 13:46:56 +0800），而本地 `origin/main` 最新提交为 `a70fc99`（2026-09-25 13:38:53 +0800）。两者相差约 8 分钟，指向同一次推送。

---

## 五、复核方式

```bash
cd <仓库路径>
git remote -v
git rev-list --count HEAD
git log --reverse --format="%ad" --date=iso | head -1
git log -1 --format="%ad" --date=iso
git log --format="%an|%ae" | sort -u
git status -sb
git rev-parse HEAD

# 转移验证（本机可复核，无需联网）
git log --reverse --format='%H' | head -1          # 应输出 549db5773eddddd46f7f7896d0a8b4d61839c655
git -C "G:\AI_Project\ai angent" log --reverse --format='%H' | head -1   # 应输出同一 hash
git -C "G:\AI_Project\ai angent" remote -v         # 应显示个人账户 URL
```

联网复核（转移证据 B）：

```bash
curl -sI https://api.github.com/repos/jincheng3870682453-hash/ace-agent   # 预期 Location 指向 ace-code-engine
curl -s  https://api.github.com/repos/jincheng3870682453-hash/ace-agent   # 预期返回 full_name = ace-code-engine/ace-agent, id = 1339557972
```

逐项对比 `RAW/remote.txt`、`RAW/repo_meta.txt`、`RAW/snapshot_env.txt`、`RAW/transfer_evidence.txt`。**数字会随时间变化，比对时请以采集时 HEAD `be2d03f` 为准**（可用 `git checkout be2d03f` 或 `git log be2d03f` 复核）。
