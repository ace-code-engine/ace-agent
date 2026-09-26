# ACE 内置计算引擎（Rust）

> 参考件：`aitoolkit-main/`（Word 体系原版：`gateway.py` / `guardian.py` / `work.py` / `Archive.py` / `Nuwa.py` / `shiyun.py`）。
> 本目录是**上游那套 Python 实现的一个常驻、零依赖的算力内核** —— 不是重写整个 Word 体系。

## 它是什么：元处理内核

ACE 已经被 Go 执行器（`../executor/`）拿走了一件事：**边界**（Job Object、进程树回收、整树 kill）。
`engine/` 拿的是另一件正交的事：**元处理** —— 处理"关于这次运行自身"的东西：

| 元处理对象 | 今天散在哪 | 引擎提供 |
|---|---|---|
| **会话事件流**（`.ace_sessions/*.jsonl`） | `cli/ace_sessionlog.py`（写+重放）、`cli/ace_sessions.py`（派生视图）、`core/ace_todos.py`（重放） | ✅ **已实现**（下方切片①）：分类计数、体积账、seq 体检、工具成/败、时间线 |
| 快照元数据 | `core/guardian.py`（list/verify/prune/gc 各扫一遍目录） | 索引 + 校验 + 差异（"这轮改了什么"） |
| 会话 / 目标状态 | `tools/goal_tools.py`、`core/ace_todos.py` | 单一真源的状态机 + 重放 |
| 运行度量 | `core/nuwa.py`、`core/ace_cost.py` | 聚合（轮次/工具/失败/成本/上下文占用） |
| 分词/指纹/召回 | `core/archive.py` | 已实现，但**实测无收益**（见下方"实测"） |

## 切片①：会话事件流索引（已落地并接进 `/audit stats`）

把一坨 JSONL 变成可查询的元事实。**Python 侧一个 JSON 都不解** —— 原始行直接送过来，
解析与索引都在引擎里（那正是"扫一遍日志"最贵的部分）。

实测在真实日志（122 事件 / 132,350 B）上跑出来的东西：

```
/audit stats
  会话元信息（1790265440341.jsonl）
    122 事件 · 8 种类型 · 工具 20 次（失败 0）· 体积 129.2 KB（去重后 6.7 KB）· 来源 ace-engine
    assistant/message×20  permission/decision×20  request/snapshot×20  system/snapshot×20  tool/call×20
```

**这份日志 95% 是重复内容**（132,350 B → 去重后 6,871 B），主因是 `system/snapshot`
每轮把完整系统提示词写一遍（116,123 B，占 88%）。这条元事实此前**没有任何地方算过**。

> 顺带一个教训：这个"重复体积"第一版算的是**整行**哈希 —— 而行里带着唯一的 `seq`，
> 于是冗余恒为 0（真实数据上当场露馅）。改成按**内容**（除 seq/ts 外的字符串值）算，
> 并让 Rust 与 Python 两侧都只取字符串值，才能逐字节对上。


## 边界铁律（这个引擎的定位，也是它的限制）

引擎**只算不裁**：

- ❌ 不做权限判定、不看路径、不碰敏感目标 —— 裁决永远在执行层（`execution_layer.py`）；
- ❌ 不读不写任何文件（缓冲区全在内存），持久化格式的唯一真源仍是 Python 侧；
- ❌ 不联网。

所以它才能待在 ACE 的安全模型里：一个**可以被杀死、可以被替换、坏掉只会变慢而不会放宽任何闸门**
的纯计算旁路。这与 MCP / Go 执行器是同一条思路 —— 但方向相反：那两个把东西挪出去是为了**孤立**，
这个挪出去只是为了**快**。

## 兼容契约（改之前先读这段）

**对齐的是 ACE 当前实现（`../core/archive.py`），不是上游 `aitoolkit-main/Toolkit/核心代码/Archive.py`。**
两者已经分叉：

| | 上游原版 | ACE 现行（本引擎对齐） |
|---|---|---|
| 分词 | `jieba.cut` 或逐字符 | `w:` 拉丁词 · `c:` 中文整段 · `b:` 中文二元组 |
| 取哈希 | `int(md5hex, 16)`（128 位取低位） | `int.from_bytes(md5(tok)[:8], "big")`（前 8 字节大端） |
| 权重 | 词频 | 每 token ±1（重复 token 自然累加） |

走错任何一条，已落的 `.agent_memory.json` 指纹就全部失配 —— 那是**持久化数据**
（`MemoryEntry.simhash`），不是可重建的缓存。所以有两道守卫：

- `cargo test`：13 项，含由 Python 真实输出得到的 SimHash 已知向量；
- `python engine/tools/xcheck.py`：在**真实** `.agent_memory.json`（517 条）上对拍
  SimHash / 分词顺序 / 主题相似度 / **召回顺序与数值**，任何不一致即非零退出。

## 构建与验证

零依赖是有意的：与 ACE「安全核心零依赖」同一立场，也让离线构建成立
（`cargo build --offline` 不需要 crates.io，也不需要 C 工具链）。

```bash
cd engine
cargo test --offline                 # 单元测试
cargo build --release --offline      # 产出 target/release/ace-engine[.exe]
./target/release/ace-engine --selftest     # 自检（不依赖 Python），失败退出码 1
./target/release/ace-engine --version
```

Python 侧对拍 + 基准（需要 ACE 的解释器环境）：

```bash
python engine/tools/xcheck.py                    # 全量对拍 + 基准
python engine/tools/xcheck.py --repeat 200       # 加大重复次数
```

## 协议

NDJSON over stdio，形体与 `docs/ADR-002-executor-boundary.md` / `core/ace_serve.py` 一致：
`{"v":1,"type":"req","id":"1","method":"...","params":{...}}` →
`{"v":1,"type":"resp","id":"1","ok":true,"result":{...}}`，失败带
`error{code,message,http_like}`。默认模式（无参数）即 serve。

| 方法 | 参数 | 结果 |
|---|---|---|
| `initialize` | `protocol` | `protocol/name/version/features` |
| `fingerprint` | `text` | `hex`（16 位十六进制）、`bits` |
| `tokenize` | `text` | `tokens`（顺序即契约） |
| `similarity` | `a`、`b` | `text_similarity`、`simhash_similarity`、`hamming`、`a`、`b` |
| `index.build` | `entries[{id,text,weight,session}]`、`mode` | `count` |
| `recall` | `query`、`anchor_text`、`session`、`top_k`、`exclude_last` | `items[{id,index,similarity,score}]` |
| **`events.load`** | `lines`（**原始 JSONL 行**）、`mode` | `accepted/skipped/total` |
| **`events.stats`** | — | `events/bad_json/missing_fields/duplicate_lines/kinds/tools/bytes/seq/unknown_kinds` |
| **`events.timeline`** | `kind`（子串）、`tool`、`limit` | `items[{seq,kind,ts,tool,status,bytes}]` |
| **`events.verify`** | — | `ok/checked/problems[]` |
| `stats` / `index.clear` / `events.clear` / `shutdown` | — | — |

两处刻意的**不比 `ace_serve` 宽容**：

- **`v` 必填且必须是整数**。`ace_serve.parse_frame` 现在缺 `v` 也接受、`v="abc"` 会抛裸
  `ValueError` 穿出 `serve_forever`（后端评审 §2.1）——这里不重演。
- **指纹走十六进制字符串，不走 JSON 数字**：64 位整数超出 f64 精度，用数字会被静默截断。

## 实测（本机 Windows / Rust 1.98 / 517 条真实记忆 / 619 文件 42 MB）

记忆召回这一列取 `--repeat 400` 的稳定值（早先 `--repeat 60` 那轮方差内给过 1.2×，
**两轮合起来只能得出"没有收益"这个结论**，不要挑好看的那次引用）：

| 场景 | Python | 引擎 | 结论 |
|---|---|---|---|
| 记忆召回（517 条，端到端含 IPC） | 0.098 ms | 0.137 ms | **0.7× —— 引擎更慢，不该搬** |
| 记忆召回（纯算力，无 IPC） | — | 0.101 ms | **1.0× —— 打平** |
| 长文本指纹（406K 字符） | 438 ms | 39 ms | **11×** |
| 写前快照：遍历 + SHA256 全部文件 | 1646 ms | — | **这笔在热路径上，每次写都付** |

**这几行合起来是一个反直觉、但比"Rust 更快"有用得多的结论：**
不要按"哪个模块热"决定搬什么，要按"**哪笔计算在热路径上重复做同一件事**"决定。

- 记忆召回每轮都调，看着最热 —— 但 Python 侧已经用 `lru_cache` 把最贵的分词缓存住了，
  剩下的 517 次小集合求交在 CPython 里本来就是 C 代码（`set.intersection`）。
  实测**纯算力打平**，加上 IPC 反而更慢。搬它等于白干。
- 长文本指纹是**反缓存**的（每次文本都不同），且是逐字符紧循环 —— 11×。
- 写前快照那 1.65 秒是**每次写操作**重付的固定开销，而且**完全可缓存** —— 这才是真正该搬的。

所以第一个真该搬的是**文件索引与哈希**，不是记忆。

### 附：写前快照的代价结构（实测否决了"文件索引"那条路）

夹具规模对齐真实仓库（347 文件 / 11.7 MB），把 `guardian.snapshot()` 拆开计时：

| 阶段 | 耗时 | 说明 |
|---|---|---|
| ① 遍历 `_collect_files` | 4 ms | |
| ② 逐文件哈希**源** | 21 ms（真实会话）/ 8.5 s（刚建好的夹具） | 真实会话里源是**长期存在、已缓存**的 |
| ③ `shutil.copy2` | 147–159 ms | 复制根本不贵 |
| ④ **读回校验副本** | **8620 ms（夹具）/ 2162 ms（真仓库）** | 成本主体 |
| `prune` | 0 ms | |

第 ④ 项为什么贵：**不是 CPU**（单个 12 MB 大文件 SHA256 = 788 MB/s），是**新写入文件的
首次读取代价** —— 同一批副本顺序读 987 ms（2.84 ms/文件），**再读一遍只要 20 ms
（0.06 ms/文件，51× 落差）**；8 线程读回降到 210 ms（4.7×，逐文件结果一致）。

**结论**：该优化的是"读回校验"这一遍，而不是"缓存源文件的哈希"（后者只值 1%）。
而并行读回**不需要引擎**：它既不吃文件系统，也不是 CPU-bound，交给 Rust 只多一层 IPC。
已落在 `core/guardian.py`（`_sha256_many` + `ACE_HASH_WORKERS`，判定与顺序版逐字一致，
回归测试在 `test_all.py` 的 F1–F4）。

## 路线图（按"元处理"重排）

1. ✅ **会话事件流索引**（切片①，已落地并接进 `/audit stats`）：分类计数、体积账、seq 体检、
   工具成/败、时间线；Python 侧零解析，口径与 `core/ace_engine.py` 的降级实现逐字段对拍。
2. ~~**快照元数据索引**（持有 `(路径, mtime, size, 内容哈希)` 索引，跳过对未变更文件的
   重哈希）~~ —— **实测否决，不要做**。拆开 `core/guardian.py` 的 `snapshot()`：
   遍历 4 ms、**源哈希 21 ms（1%）**、复制 159 ms、**读回校验副本 2162 ms（92%）**。
   索引能省的只有那 1%，因为真实会话里源文件是长期存在、已被缓存的（21 ms）；
   贵的是**刚复制出来的副本的首次读取**（顺序 2.84 ms/文件 vs 同一批再读一遍 0.06 ms/文件，
   51× 落差），而那件事跟"有没有索引"无关。
   **真正付钱的做法是并行读回**（实测 4.7×，夹具端到端 8.7 s → 2.0 s），已直接落在
   `core/guardian.py` 里，**不需要引擎**：它不吃文件系统、也不算 CPU-bound（大文件
   SHA256 有 788 MB/s），把文件系统交给 Rust 只会多一层 IPC。
   详见下方「实测」。
3. **会话/目标状态**：把 `tools/goal_tools.py`（内存 CAS）与 `core/ace_todos.py`（重放）
   收敛成一份可重放的状态机 —— 评审实测它们今天会互相覆盖（子代理共用同一个文件）。
4. **运行度量聚合**：`core/nuwa.py` 的 POC 指标 + `core/ace_cost.py` 的成本，跨会话累积。
5. **仓库扫描**（`grep`/`glob` 的 Python 实现）：与文件索引共用同一份目录状态。
6. **守门批处理**（`gateway_v2/guard.py` 的 8 条规则）：搬之前先把 warn 遮蔽 block 那个洞
   钉死（本会话已修，测试在 `test_all.py` 的 D5）。

> 注意第 2 条与"记忆召回"的区别：记忆那条实测**没有收益**（0.7×），别照"哪个模块热"去搬。

## 还没做（不要当成已完成）

- **只接了元处理这一条线**：`/audit stats` 走 `core/ace_engine.py`（引擎不可用时降级为纯
  Python 同口径实现）；其余路径（`core/archive.py` 的记忆召回、`core/guardian.py` 的快照哈希、
  `grep`/`glob`）**仍然完全不使用引擎**。
- 没有进 CI / 没有进发布产物：`packaging/` 与 `release-exe.yml` 未改动，所以**打包产物里没有
  这个二进制** —— 冻结版上 `engine_path()` 找不到它就自动降级（功能在、只是慢）。
- 未做故障注入（引擎中途被杀、协议半帧、超时）。适配层对"引擎不可用"是降级，对"引擎中途死"
  靠异常兜底；这两种都还没有专门的测试。
- `guard` / `AST` / `snapshot` / `goal` 尚未移植（见路线图 2–6）。
