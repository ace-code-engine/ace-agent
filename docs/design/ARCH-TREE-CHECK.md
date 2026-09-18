# 立项卡：权威目录树一致性校验（Q-06）

> 状态：**已执行**（S1-S4 完成；验收与负向证据见 §7）
> 来源：`docs/BACKLOG.md` P1 · Q-06「CI 结构一致性校验」；触发于第二轮文档重构后——权威目录树已从 README 迁至本文档（`docs/ARCHITECTURE.md`），成为唯一事实源。
> 预期产出：一条自动校验，让"树 ↔ 仓库实际文件"的漂移在 CI 与本地都被拦住，而不是靠人工纪律。
> **后续（R-07）**：本文写于根目录扁平时期，下文示例里的 `version.py` / `i18n.py` / `ace_doctor.py` / `ace_chatscroll.py` 等根级模块，现已下沉到 `ui/` `cli/` `core/`（见 `docs/design/STRUCT-REFACTOR.md` R-07）。**R1-R4 四条规则一个字都没变**，只是被校验的路径换了前缀；示例文字保留原样作为当时的记录。另追加一条 **R5**（包化当天补的）：`compileall` 的参数必须覆盖**全部** `.py`（文件或包目录），且列出的每个路径都真实存在 —— 它上线时当场揪出 `demo/record_demo.py` 与 `docker/download_model.py` 两个从来没进过编译检查的脚本。

---

## 1. 背景

第二轮重构把权威目录树放进 `docs/ARCHITECTURE.md`（README 只留架构级短树，CONTRIBUTING 指向这里）。树里那句话是自认的软肋：

> 维护纪律：树里出现的每个路径应真实存在；新增文件后同步本树（BACKLOG Q-06 曾提 CI 自动校验，未实现前靠人工）。

人工纪律已经漂过一次（Q-06 记载的漏项就是这么来的）。同时 `docs/BACKLOG.md` Q-06 还有另一半没做：**ci.yml 的 compileall 漏根级模块**。

## 2. 目标

1. 树中的每条路径 → 必须真实存在（防幽灵条目）。
2. 仓库真实内容 → 该进树的必须进树（防漏登记）。
3. `ci.yml` 的 compileall 参数 → 覆盖全部根级 `.py`（防语法错误绕过 CI 编译检查）。
4. 校验必须**能在 CI 与本地同时跑**，且零新增第三方依赖。

## 3. 非目标

- 不做 Q-04（README/CI 里"40 工具""readonly 16"这类**数字**的单一来源）——那是数字动态化，机制不同。
- 不为 README 的架构级短树做校验（README 已刻意只画层级，权威在 ARCHITECTURE.md）。
- 不新增独立 CI job（见 D1）。
- 不改任何业务代码。

## 4. 现状锚点（本机实测，非文档转述）

审计脚本：`ace/.test_tmp/audit_tree{,2,3,4}.py`（一次性草稿，未入库；规则已固化进 `test_all.py [38]`，本机可随时 `python test_all.py` 复现）。

| 项 | 实测结果 |
|---|---|
| `docs/ARCHITECTURE.md` 树条目 | **72 条**，全部解析成功 |
| 树中不存在于仓库的路径 | **0 条**（正向干净） |
| 仓库跟踪文件总数 | 112（`git ls-files`） |
| **R2 根级缺口** | **9 项**：`README.md`、`CONTRIBUTING.md`、`version.py`、`requirements.txt`、`ace.cmd`、`Dockerfile`、`docker-compose.yml`、`.gitignore`、`.dockerignore`（`.github/` 因树里已有 `.github/workflows/` 而视为已覆盖） |
| **R3 展开目录集** | 6 个：`.github`、`assets`、`docs`、`docs/design`、`docs/history`、`tools`（"展开" = 树里出现了该目录的至少一个直接子条目） |
| **R3 缺口** | **4 项**：`.github/ISSUE_TEMPLATE`、`.github/pull_request_template.md`、`tools/__init__.py`、`tools/status.py` |
| 目录级列举（不触发 R3） | `executor/`、`docker/`、`locales/`、`prompts/`、`gateway_v2/`、`demo/`、`benchmarks/`、`e2e/`、`docs/history/prompt-engineering/`、`.github/workflows/` |
| **S1 合计需补** | **13 条**（9 + 4） |
| ci.yml compileall 漏根级 `.py` | **4 个**：`ace_chatscroll.py`、`ace_doctor.py`、`test_all.py`、`version.py`（ci.yml:38） |
| test_all.py 先例 | 末尾已有 `[35]`（SEC-01/02）、`[36]`（Q-10 守卫）、`[37]`（chatscroll 纯逻辑）三个"BACKLOG 项专用小节" |
| CI 现状 | `test` job 在 Python 3.10/3.11/3.12 三档跑 `python test_all.py`（ci.yml:15-41） |

## 5. 设计决策

| # | 决策 | 理由 |
|---|---|---|
| **D1** | 校验落在 **`test_all.py` 新增 `[38]` 节**，而不是新增 CI job | Q-06 原文写"补 job"，但 CI 的 `test` job 已在 **3 个 Python 版本**跑 test_all——加 job 只是第三份重复，还要再装解释器；放进 test_all 则**本地 `python test_all.py` 同样拦截**。与 `[36]`（Q-10）的既有做法一致。若你坚持独立 job，仅需把同一函数抽成 `scripts/` 脚本 + 一个 3 行 job，S2 可平移。 |
| **D2** | 四条判定规则，全部可判定、无人工解释 | R1 正向存在性；R2 根级全覆盖；R3 展开目录的直接子项必须列全；R4 compileall ⊇ 根级 `.py`。**（R-07 追加 R5：compileall ⊇ 全部 `.py`（文件或包目录），且列出的路径都存在）** |
| **D3** | 仓库真相用 **`git ls-files`**，git 不可用则 `skip()` | 文件系统扫描会把未跟踪生成物（`.test_tmp/`、`.guardian/`、`benchmarks/results/`）误判成漂移；`git ls-files` 天然只返回"仓库真实内容"。沿用既有的 `SKIPPED` / `--strict` 通道（Q-03 的纪律：不许假绿）。 |
| **D4** | **先清零，再上线**：S1 先补齐树里 13 条缺口与 compileall 4 项，S2 才加检查 | 否则检查一合并 CI 立刻红。 |
| **D5** | 白名单**写进文档**（`.gitignore`/`.dockerignore`/`.github/` 等 dot 项**入树**而非豁免） | 白名单藏在代码里就是下一个漂移源。倾向全部入树（它们本来就在仓库里），白名单留空。 |

**R3 的边界**（避免误伤）：只有当某目录在树中被**展开**（即出现了它的至少一个直接子条目）时，才要求其**全部直接子项**（文件与子目录各一行）都在树中。仅按目录列一行的（如 `docker/`、`locales/`、`executor/`）不触发。实测展开集 6 个，其中当前已合规：`assets`、`docs`、`docs/design`、`docs/history`；有缺口：`.github`、`tools`。

**防"假全绿"**：解析器若解析到的条目数 < 40（远低于实测 72），直接判失败——避免树被改坏导致"解析不出条目 = 全部通过"。

## 6. 分步执行

| 步 | 内容 | 回归 |
|---|---|---|
| **S1** | 文档与 CI 参数对齐：`docs/ARCHITECTURE.md` 树补 **13 条**（R2 的 9 项根级含 `README/CONTRIBUTING/version.py/requirements.txt/ace.cmd/Dockerfile/docker-compose.yml/.gitignore/.dockerignore`；R3 的 `.github/ISSUE_TEMPLATE/`、`.github/pull_request_template.md`、`tools/__init__.py`、`tools/status.py`）；末尾"维护纪律"句改写为"由 test_all [38] 自动校验"；`.github/workflows/ci.yml:38` compileall 补 4 个模块（`ace_chatscroll.py` `ace_doctor.py` `test_all.py` `version.py`） | 复跑 `audit_tree4.py`：R1/R2/R3 缺口归零；YAML 结构复核 |
| **S2** | `test_all.py` 末尾新增 `[38] 文档/仓库结构一致性（Q-06）`，约 60-80 行纯 stdlib：解析树 → `git ls-files` → R1/R2/R3/R4 各若干 `check()`（R-07 后为 R1-R5，七条 `check()`） | `python test_all.py` |
| **S3** | 文档同步：`docs/BACKLOG.md` Q-06 标 ✅ + 证据句；`docs/TESTING.md` 补一行 [38]；`CHANGELOG.md` v3.7 补一条 | — |
| **S4** | 验证与快照：全量 test_all、**负向注入验证**（见验收）、ruff、compileall；按既有习惯每步一个快照 | 见 §7 |

执行记录（快照）：立项卡 `0f0ed09` · S1 `e648817` · S2 `7953343` · S3 `7929965` · S4 本卡验收勾选存档。全部为文档/测试改动，零业务代码。

## 7. 验收清单（执行后按实测勾选）

- [x] 树中 0 条幽灵路径（R1）—— 注入幽灵条目 `ghost_probe_file.py` 后实测变红并点名该路径
- [x] 根级跟踪条目 100% 出现在树中（R2）—— 删除树中 `version.py` 行后实测变红并点名 `version.py`；白名单为空，无需豁免
- [x] 展开目录（6 个）的直接子项零漏项（R3）—— 检查上线首跑即抓到漏登记的 `docs/design/ARCH-TREE-CHECK.md`（本卡自身）；删 `tools/result.py` 行后再次变红
- [x] ci.yml compileall 覆盖全部根级 `.py`（R4）—— 从 compileall 行移出 `version.py` 后实测变红
- [x] **负向注入变红**（两次注入运行，均 `exit 1`）：① R1 幽灵 + R2 漏登记；② R3 漏登记 + R4 未覆盖
- [x] **R5（R-07 包化当天追加）**：compileall ⊇ 全部 `.py`（文件或包目录）+ 列出的路径都存在 —— 上线首跑当场点名 `demo/record_demo.py` 与 `docker/download_model.py`（两个从来没进过编译检查的脚本，补进 `compileall` 行后归零）；负向注入新目录 `tmp_r5_probe/probe.py` 后实测变红（`未覆盖: ['tmp_r5_probe/probe.py']`），删掉即恢复 7/7
- [x] `git ls-files` 不可用时报 `SKIPPED`（`--strict` 按失败处理），不假绿 —— 代码走 `skip()` 通道（本机 git 可用，未触发）
- [x] 全量 `python test_all.py`：**997 / 1006**（新增 5 条用例全绿）；9 项失败与基线逐项同名（Go Job Object 受进程沙箱限制），零新回归
- [x] 无新增 CI job、无新依赖、无业务代码改动；ruff（CI 同款选择集）零命中；快照 `0f0ed09` `e648817` `7953343` `7929965` 可逐条 revert

## 8. 风险与残余

| 风险 | 评估 / 缓解 |
|---|---|
| 贡献摩擦上升：新增根级文件必须同步文档 | 这正是目的；强制面仅"根级 + 展开目录的直接子项"，**未展开**目录（`docker/`、`executor/`、`docs/history/prompt-engineering/` 等）内部仍可自由增删 |
| 假红：本地未跟踪生成物被当成漏项 | D3：走 `git ls-files`，天然排除 `.test_tmp/`、`.guardian/`、`benchmarks/results/` |
| 树解析脆弱（`#` 注释、`│` 前缀、`i18n.py + locales/` 复合条目、`universal_document_parser.py# …` 无空格） | 解析器按"marker 前导字符数 ÷ 4 + 1"定深度；复合条目按 ` + ` 拆分；条目数下限自检（§5） |
| 跨平台路径分隔差异 | 一律按 posix 相对路径（`/`）比对，不用 `os.sep` |
| 与 R-05（test_all.py 拆分）冲突 | R-05 落地时 `[38]` 随小节迁移即可，不阻塞 |
| 树需要维护"哪些目录已展开"的隐含状态 | 规则由**树自身形态**推导（有子条目即触发），不额外维护清单 |

## 9. 刻意不做

- 独立 CI job（D1 已说明理由，且保留平移方案）。
- 白名单机制的最小化——倾向 **白名单留空**，dot 项一并入树。
- Q-04 数字单一来源、README 短树校验、R-05 拆分：各有归属，不在本卡范围。
- 历史归档目录的**内部**逐文件入树：`docs/design/` 与 `docs/history/` 本身已展开（故其直接子文档在 R3 覆盖内，且当前合规），但 `docs/history/prompt-engineering/` 保持**不展开**——历史文档不背维护负担。
