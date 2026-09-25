### RAW/ 内容清单

> **采集于 2026-09-25**。本文件**被重新生成/增补过三次**：23:15（重生成）、23:2x（补 `tags_remote.txt`）、23:4x（补截图证据两个文件）。原因见下。
>
> **为什么不再记录本文件自己的体积**：原版本对**本文件自身**那一行的计数是过期的（自述 `725 B / 21 行`，磁盘上已是 `766 B / 22 行`）。原因是自引用清单**永远落后一代**：写完全自己的体积，文件本身就已经变了。这是**结构性**问题，不是一次性笔误。本版本把自己的那一行记为 `——`。
>
> **校验口径**：行数 = **换行符个数**（文件以换行结尾时，EOF 处的换行**不**额外算一行）；二进制文件记 `—`。
>
> **除本文件自身外**的 20 个文件，合计 **97,962 字节**。

| 文件 | 字节 | 行数 |
|---|---|---|
| `00_INDEX.md` | —— | —— |
| `changelog_v3.10.1.txt` | 6385 | 41 |
| `changelog_v3.2.txt` | 2253 | 14 |
| `changelog_v3.3.txt` | 1151 | 15 |
| `commit_v3.8.0_release.txt` | 820 | 18 |
| `commits_earliest.txt` | 3459 | 22 |
| `commits_per_day.txt` | 318 | 18 |
| `contributions_jogruber.txt` | 1540 | 50 |
| `contributors_page.txt` | 2517 | 46 |
| `contributors_page_2026-09-25.png` | 48881 | —— |
| `release_notes_index.txt` | 1099 | 36 |
| `remote.txt` | 199 | 6 |
| `repo_meta.txt` | 425 | 14 |
| `security_audit_reconcile.txt` | 8302 | 31 |
| `snapshot_env.txt` | 523 | 14 |
| `tag_v3.10.1.txt` | 1367 | 26 |
| `tag_v3.3.txt` | 977 | 21 |
| `tag_v3.8.0.txt` | 1032 | 21 |
| `tags.txt` | 5632 | 48 |
| `tags_remote.txt` | 6335 | 108 |
| `transfer_evidence.txt` | 4747 | 73 |

### 三份文件的证据等级与其余不同（**用之前先看这节**）

| 文件 | 性质 | 注意 |
|---|---|---|
| 其余 18 份 | **命令输出原样留档** | 可直接复核（命令见各 `.md` 与 `00_INDEX.md` 末尾） |
| `tags_remote.txt` | **后补证据**（23:2x） | 为纠正方法学错误而加：`tags.txt` 读的是**本机 clone** 的 tag 引用，而它落后于远端（本地 46 / 远端 **48**，缺 `v3.41.0`、`v3.7.0`）。「本机没有」≠「仓库没有」。 |
| `contributors_page.txt` + `.png` | **截图转录 + 截图**（23:4x） | **不是命令输出**。页面为动态渲染，未保存 HTML。3 个精确计数（156 commits / 38,776 ++ / 8,221 --）来自**截图转录**，柱高为**目测**。口径与 `git rev-list --count` 不同，**不可互相印证**，详见 `contributors_page.txt`。 |

### 如何用本清单做完整性校验

```powershell
$d = 'G:\AI_Project\ace\evidence-pack\RAW'
Get-ChildItem $d -File | Sort-Object Name | ForEach-Object {
  $b = [System.IO.File]::ReadAllBytes($_.FullName)
  $nl = 0; foreach ($x in $b) { if ($x -eq 10) { $nl++ } }
  '{0}|{1}|{2}' -f $_.Name, $b.Length, $nl
}
$f = Join-Path $d 'contributors_page_2026-09-25.png'
(Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
# 预期 365fe37d29a64e059664e313572899c166c02e1fb4b485b33a301dc8aca591ef
```

**对照口径**：排除 `00_INDEX.md` 后逐行与上表比对，`00_INDEX.md` 自身不在校验范围内（理由见上）。
