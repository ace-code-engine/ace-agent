### RAW/ 内容清单

> **采集于 2026-09-25**；**本文件于 2026-09-25 23:15:15 +08:00 重新生成**，**并于 23:2x 补入 `tags_remote.txt`**。
>
> **为什么不再记录本文件自己的体积**：原版本对**本文件自身**那一行的计数是过期的（自述 `725 B / 21 行`，磁盘上已是 `766 B / 22 行`）。原因是自引用清单**永远落后一代**：写完全自己的体积，文件本身就已经变了。这是**结构性**问题，不是一次性笔误。本版本把自己的那一行记为 `——`，因此不会再过期。
>
> **校验口径**：行数 = **换行符个数**（文件以换行结尾时，EOF 处的换行**不**额外算一行）。该口径经 18 个文件逐一比对，与磁盘完全一致。
>
> **除本文件自身外**的 18 个文件仍为采集时原样、未被改写，合计 **46,564 字节**。

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

### `tags_remote.txt` 是干什么的（**重要**）

它是**后补的一份证据**，用途是纠正一类**方法学错误**：

`tags.txt` 来自 `git for-each-ref refs/tags` —— 读的是**本机这份 clone 的 tag 引用**。而这份 clone 的 tag 引用**落后于远端**：本地 46 个、远端 **48** 个，本地缺 `v3.41.0` 与 `v3.7.0`。

于是「`git tag` 里没有 X」**不等于**「仓库没有 X」。原版本的 `TAGS.md` / `TIMELINE.md` / `RELEASES.md` 由前者推出了后者，产生了 **2 处假否定**。`tags_remote.txt` 用 `git ls-remote --tags origin` 拿到**远端权威列表**作为正确出处。

### 如何用本清单做完整性校验

```powershell
$d = 'C:\Users\69215\Desktop\evidence-pack\RAW'
Get-ChildItem $d -File | Sort-Object Name | ForEach-Object {
  $b = [System.IO.File]::ReadAllBytes($_.FullName)
  $nl = 0; foreach ($x in $b) { if ($x -eq 10) { $nl++ } }
  '{0}|{1}|{2}' -f $_.Name, $b.Length, $nl
}
```

**对照口径**：排除 `00_INDEX.md` 后，逐行与上表比对。**本文件自身不在校验范围内**（理由见上）。
