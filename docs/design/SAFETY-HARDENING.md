# 立项卡：安全边界加固 H-01 ~ H-26（W0 ~ W7 已实施）

> 状态：**W0 ~ W7 已实施**（H-01 ~ H-07、H-09 ~ H-26 完成并验收；**H-08 未做**，理由见 §9.4）。
> **只剩 H-08：精确回滚** —— 要把"整树还原"改成"只回滚本轮"，现有 5 条断言依赖旧语义，需独立工作包（见 §9.4）。
> 全量测试：**全绿、退出码 0、零失败项**，且不需要 `PYTHONUTF8=1` 这类环境变量。
> （**本卡头部不手抄断言总数** —— 那正是本次修掉的一类漂移：头部写 2240、实际已 2241。
> 精确条数以 `python test_all.py` 的输出为准，或在下面各节的验收快照里查。）
> 本卡 §2 保留原始规划口径，§9 ~ §17 是实施记录（含与卡片不一致之处）。
> 全部改动按**分层提交**入库 —— 每个工作包一个可独立回滚的提交；工作树干净。
> 编号：`H-` 是**新命名空间**，不与 `SEC-` / `Q-` / `R-` / `REL-` 共享编号空间（吸取 ADR-002 与独立 ADR 文件撞号的教训）。
> 来源：2026-09-25 三路独立只读审计（执行层安全 / agent 循环与协议 / 前端与扩展面），共 38 条；其中 20 余条经复核，1 条被推翻（见 §7）。
> 与 BACKLOG 的关系：`docs/BACKLOG.md` 的 SEC-/Q-/R-/REL- 全绿是**当时那一批**。本卡是**新一批**，不回填 BACKLOG、不改其状态。

---

## 0. 一句话诊断

38 条里**至少 12 条是同一个病**：

> 同一个判据在多处各写一份，其中一份忘了同步；或者判据本身是"列举禁止什么"的名单，而名单天生补不全。

实例（全部实测）：凭据清单 2 份（`tools/base.py:36/48` vs `core/guardian.py:37/39`）、权限集合 2 份（`execution_layer.READ_TOOLS` vs `ui/ace_cards.py:42`）、403 语义标记 2 份（`tools/base.py:73` vs `execution_layer.py:1416` 字面量副本）、拒绝清单共 11 份且零一致性校验、`..` 折叠只有一处做、SEC-06 只修了一半（`ace_execpolicy` 修了、`terminal_view` 没修）。

所以本卡不是"补 38 个洞"，而是**两条主线**：

- **主线 A（结构）**：把"单点判据"收敛成"单一来源 + 单一入口"。补名单补不完，换方向才补得完。
- **主线 B（承诺）**：把两处 fail-open 改成 fail-close。ACE 对沙箱档位（503 不降级）和审批（非交互一律拒）都是 fail-close，唯独**写前快照**和**审批绑定**是 fail-open —— 而这两条恰是"trust but verify"的承重墙。

---

## 1. 目标与非目标

### 目标（让 README 的三句承诺为真）

1. **"写前快照，`/undo` 可回滚"** —— 快照失败必须是一个用户可见的决策，不是一个被吞掉的异常。
2. **"审批只对你确认过的那一个对象有效"** —— 而不是"对这一个工具名有效"。
3. **"扩展面走同一条闸门"** —— MCP / hooks / skills 与注册表工具享受同一套权限、隔离、快照、审计。

### 非目标（明确不做，避免本卡膨胀）

- **四套 UI 合并 / "哪个栈才是产品"** —— 这是产品决策不是缺陷修复，见 §6。
- **成本硬预算、记忆 TTL/归属、上下文压缩不变式** —— 属新能力设计，二期。
- **不改公开契约**：`registry.py` 的 handler 名、`COMMANDS`/`COMMAND_HANDLERS` 的键、`INTERFACES.md` 里的对外约定都不动（沿用 `STRUCT-REFACTOR.md` §4 的纪律）。

---

## 2. 工作包

### W0 · 止血（零风险，先做）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-01 | 缓存/会话/汉化目录既没进 `.gitignore` 也没进 `EXCLUDE_DIRS` | 实测一次快照 = **1903 文件 / 34.5 MB**，其中 `.ace_sessions`(972) + `.ace-cc-zh`(636) 占 **71%** | `.gitignore` 补 `.ace/` `.ruff_cache/` `.pytest_cache/`；`EXCLUDE_DIRS` 补 `.ruff_cache` `.pytest_cache` `.ace_sessions` `.ace-cc-zh` |
| H-02 | 失败快照留下**永久孤儿目录**，`prune` 看不见 | `guardian.snapshot()` 把 `meta.json` **最后**写（`:155-159`），而 `list_snapshots()` 只认有 `meta.json` 的目录（`:273`）⇒ 中途失败无 `meta.json` ⇒ 永不被清理；只有"创建后自检失败"那一支有 `rmtree`（`:166`） | `snapshot()` 整段 `try/except` + 失败 `rmtree(dest_root)`；加 `guardian --gc` 清无 `meta.json` 的目录 |
| H-03 | 文档仍在报已关闭的旧账 | `INTERFACES.md:82`（说 `agent_runner --permission` 默认 `write`；实测 `agent_runner.py:838` = `readonly`，且 SEC-03 已 ✅）、`:127`（把 R-03 列为"已知缺口"，已 ✅）、`:172`（把 SEC-03/Q-08/Q-15/R-01~R-05 列为"仍开放"，全 ✅）、`ADR-002:506`（说 `code_execute` 没接执行器；实测 `code_tools.py` 已有 `use_go_executor` 分支 + `client.exec_python`）、`ARCH-TREE-CHECK.md:14`（说 Q-06 的 CI 校验未实现，实际 `[38]` 在跑）、`ARCHITECTURE.md` 树里 `ui/ace_keys.py` 列了**两次** | 逐处改成现码事实；权威树去重 |
| H-04 | 文档-BACKLOG 无闭环；`[38]` 查不出重复 | `test_all.py:6257` `_paths = set()` ⇒ 重复项塌陷；全仓库无任何断言把文档里的 BACKLOG 编号与 ✅ 状态关联 | `[38]` 改为 list 解析 + 断言无重复路径；新增守卫：文档以"仍开放/缺口/矛盾"措辞引用已 ✅ 的 ID ⇒ CI 红 |
| H-23 | **（卡片外新增，见 §9.3）** 测试残留只生不灭 | `test_all.py:49 mktemp()` 只建不收 ⇒ 每跑一轮沉淀一批；实测 `ai angent` 那份副本累积 **122 万文件 / 375 MB**，`ace` 12.4 万 / 2.3 GB。这是"文件数拖慢一切"（遍历/备份/杀毒/索引）的直接根因 | `mktemp()` 登记自建目录 + `atexit` 回收；`--keep-tmp` 保留失败现场 |

**W0 验收**：全量测试与基线逐项一致；`[38]` 全绿；新增两条断言（`EXCLUDE_DIRS` 与 `.gitignore` 的缓存项一致、树无重复路径）。

---

### W1 · 快照可信（P0）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-05 | **快照失败 = 静默 fail-open** | `execution_layer.py:1274-1282` `except Exception: ctx.snapshot_id = None`，随后 `:881` 的 `_stage_execute` **无条件执行**；`:1690` `if not (self.guardian and snapshot_id): return False` 静默；全仓库搜"快照失败"= **0 处**。`guardian.py:164-167` 专门写了"创建后自检，失败即 raise"——**那个 raise 被两帧之上的 except 丢掉了** | 阶段⑨失败 ⇒ 返回 `403 SNAPSHOT_UNAVAILABLE` 并**终止本轮**；提供显式豁免 `snapshot_required=false`（默认 true）；失败写进会话事件日志 |
| H-06 | 第二条**无异常的** fail-open | `guardian.py:129-130` `if not files: return None` —— 无可收集文件时返回 None，写入照常 | **实施时收窄**（见 §9.3）：只有"有文件、但每个都只因为像凭据而进不了快照"（`.env`/`*.pem`/`.npmrc`/`.git-credentials`…）才算"没有回滚点"→按 H-05 处理。目录被排除（运行时产物/缓存/会话）意味着**没有用户内容**，放行。判据落在 `guardian.count_credential_only_files()` |
| H-07 | 回滚失败只打 stderr，且 result 无法区分"没快照"与"已回滚" | `execution_layer.py:1366` 丢弃 `_rollback_current_snapshot` 的返回值 | 回滚失败走用户可见结果；`process_agent_output` 的返回 dict 增加明确的快照状态字段 |
| H-08 | "只回滚本轮"是假的：实际是**整树还原** | `guardian.py:230-240` `for src in self._collect_files(): src.unlink(missing_ok=True)` 再按 `meta["files"]` 全量还原 ⇒ 本轮之外的用户编辑、其他进程新建的文件一起被删/被回退。文档 `SECURITY-MODEL.md:36` 却写"只回滚本轮，不动无关修改" | 记录**本轮 touched paths**（工具层知道自己动过哪些路径），只还原那些；整树快照降级为人工恢复用的归档 |

**W1 验收（每条必须先看着它红）**：

- 把 `.guardian` 置为只读 → 断言写入被**拒绝**且用户看到消息（不是静默通过）；
- 注入 `shutil.copy2` 中途抛错 → 断言**无孤儿目录残留**；
- 用户在本轮编辑 `main.py` + 触发任意 L4 block 规则 → 断言**用户编辑仍在**；
- 关联条目：#1 #6 #9 #12 #36。

---

### W2 · 审批绑定到"对象"而不是"工具名"（P0）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-09 | 授权键是**工具名**，重试时两道闸门都被跳过 | `execution_layer.py:1116` `ctx.confirmed = tool_name in temp_grants or ...`；`:1174` 把项目外覆盖闸门（`:1176`）**和**外发闸门（`:1193`）一起包在 `if tool_name not in self.permission.temp_grants ...` 里；而被执行的重试是**模型重新生成**的（`agent_runner.py:609` `PROMPT_PERM_GRANTED` + `ai_code.py:5569-5588` 重新入模），`pending_permission` 只存 `{"tool","reason"[,"outside_path"]}` 没有参数摘要。注释 `:1190` 还写着"授权只对**这一个路径**有效" | 把 gated 参数摘要（canonical host / canonical 解析后路径）存进 `pending_permission`，重试必须匹配摘要否则重问；**或**前端在"y"时**逐字回放**被批准的那次调用而不是让模型重发（卡片里写清取舍，二选一） |

**W2 验收**：

- 默认配置（无 `egress_allowlist`）：批准 `https://benign.example.com/` → 重试携带 `https://evil.tld/...` ⇒ **必须再问**；
- 批准覆盖 `Desktop\taxes.xlsx` → 重试改覆盖 `Desktop\other.xlsx` ⇒ **必须再问**；
- 关联条目：#2 #33。**注意**：这条与 H-16（MCP 权限）叠加时会互相放大，先做 H-09 更安全。

---

### W3 · 单一来源 + 单一入口（结构主线 A）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-10 | 敏感路径判定按**拼写**匹配，OS 解析别名即可绕过（**本机已复现**） | `tools/base.py:84-86` 纯字符串匹配。实测 `sensitive_target(".ssh/config")` → `'敏感目录: .ssh'`，而 `sensitive_target("SSH~1/config")` → **None**（OS 解析为同一个文件），`SSH~1` 在本机 `exists=True`；`.ssh.`（尾点）、`AWS~1`（8.3）同理 | 新增 `core/canonical.py`：`canonical_path()` = 解析到 OS 最终路径 + case fold + `..` 折叠 + 尾点/空格剥离 + 8.3 展开。**所有名单判定都在它之后** |
| H-11 | "哪些文件算凭据"有**两份互相漂移**的清单 | 实测：`tools/base.py` 30 个 basename vs `core/guardian.py` **3** 个。方向 A：25 个名字（`.npmrc` `.pypirc` `.pgpass` `.git-credentials` `.netrc` `.htpasswd` `.terraformrc` …）对工具是凭据、guardian 却会**明文复制进快照** —— 而 `guardian.py:35-36` 的注释写着"**绝不能**把用户凭据再复制一份进 `.guardian`"（SEC-04 记 ✅）。方向 B：`.env` / `.claude.json` / `client.ovpn` / `key.asc` guardian 不快照、工具却允许写 ⇒ **这些写入不可回滚** | 新增 `core/sensitive.py` 作**唯一来源**，`tools/base` 与 `core/guardian` 都 import 它；`test_all` 加断言：两个消费者对同一名字必须同判 |
| H-12 | 用户的 `deny` 规则可按原始字符串绕过 | `core/ace_rules.py:84-89` `_norm_path` 的 docstring 说"统一小写盘符"，**函数体从不小写、也从不折叠 `..`**；`:117-119` `_norm_path(path).startswith(_norm_path(pat))`，而匹配发生在 `execution_layer.py:1123`，用的是**模型原始 JSON**、解析之前。⇒ 规则 `pattern=".env"` 被 `path="tools/../.env"` 绕过 | `_norm_path` 折 case + 折叠 `..`（并让 docstring 与实现一致）；规则匹配移到 **canonical 之后**（用工具真正要动的那个 target） |
| H-13 | 破坏性目标集合漏项：`file_move` 的 `source` 从不被检查 | `execution_layer.py:1075-1077` 只取 `path`/`dest`；`ace_rules.py:117` 同样只读 `path`/`dest`/`target` ⇒ 项目外文件被静默移走、无法回滚（`SECURITY-MODEL.md:28` 承诺的"覆盖或删除项目外已存在文件要逐次确认"，`file_delete` 做到了、`file_move` 没有） | 新增 `core/targets.py`：`destructive_targets(tool, params)`（`file_move` 返回 `source` + 覆盖时的 `dest`），层与 handler **共用同一个函数** |

**W3 验收（关键：这张表要对每个消费者都跑一遍）**：

一张「混淆参数表」——`..`、大小写、尾点、8.3 短名、junction/symlink、UNC——参数化喂给**全部消费者**：`sensitive_target` / `rule_matches` / `_outside_destructive_reason` / `terminal_view._escapes_project` / `guardian._is_sensitive_file`，**必须同判**。这条断言就是主线 A 的收口物。

关联条目：#3 #4 #7 #22 #30 #31 #35。

---

### W4 · 路径类工具统一入口

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-14 | `open_file` / `edit_file` 是 `PERM_READ`（默认只读会话**免审批**）、却走一条**不做 confine/sensitive 判定**的旁路，并能启动任意程序 | `registry.py` 两者均 `PERM_READ`；`file_ops.py:718/768` 用 `_resolve_read_path`，该函数（`tools/base.py:343-348`）只做 `expanduser`+拼接+`resolve()`，**无 `_confined`、无 `sensitive_target`**；`:725/743/776/797` `os.startfile()`（ShellExecute，会**执行** `.exe`/`.bat`/`.lnk`）、`:790` `Popen(["code", ...])`。注册表描述写"生成可点击文件链接（用户点击后打开）"，但未登记的 `auto_open`（`:736`）让它**立刻打开**（默认仍是 `False`） | 所有吃路径的工具统一走一个 `resolve_target(read_only=)`（confine + sensitive + canonical）；`open_file` 降级为"只给链接"，自动打开改为需确认能力 |
| H-15 | `terminal_view` 的 `-` token 跳过（SEC-06 只修了一半） | `tools/terminal_view.py:22-24` `if token.startswith("-"): return False` ⇒ `--output=C:\...` 整个被豁免；`ace_execpolicy.py:336-345` 已经修了这同一件事，`terminal_view` 没跟上。`git log --output=<path>` 能从**只读工具**写出项目外文件，不快照、不弹审批 | 抽一个 tokenizer，`terminal_view` 与 `ace_execpolicy` **共用**；`-` 跳过仍须检查 `=value` 与贴写法 `-o<value>` |

**W4 验收**：readonly 会话下 `open_file` 无法启动进程（用哨兵文件 + 断言未产生子进程）；`terminal_view` 无法用 `git --output=` 写出项目外。关联：#5 #8 #32 #34。

---

### W5 · 扩展面走同一条闸门（P0）

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-16 | **MCP 服务器自己给自己定权限类**，且完全绕过外发闸门 | `core/ace_mcp.py:145-154` 只要服务器自报 `annotations.readOnlyHint: true` 就返回 `"read"`；而 `execution_layer._LEVEL_SOURCES["readonly"] = ("read",)` ⇒ **默认只读档免审批执行**一个 ACE 沙箱**之外**的子进程。注册处 `ace_mcp.py:523-524` 直接 `permission=s["permission"]`，且 `egress=` / `confirm=` **零命中** ⇒ SEC-03 的外发确认对所有 MCP 工具失效。文档 `COMMANDS.md:195` 却写"权限/审批/审计照旧" | 权限类由 **ACE 指定**、不信服务器自报（默认 `high_risk`，用户侧逐工具覆盖文件）；MCP spec 补 `egress=True`（或三态 `egress="unknown"`）并接入同一套隔离/快照/审计 |
| H-17 | 仓库自带的 `.ace/hooks.json` 在**启动时**以 `shell=True` 执行 | `ai_code.py:4996-4997` 项目 hooks 路径取自被打开的仓库；`core/ace_hooks.py:235-236` `subprocess.run(..., shell=True, env=env)`（**继承全量环境**，含模型 API key）；在 `ExecutionLayer.__init__` 加载（任何权限判定之前）；`.gitignore` **没有 `.ace/`** ⇒ 该文件可提交；`--approval-policy untrusted` 与 hooks 无任何关联。**当前仓库内不存在 `.ace/` 目录**，故这是**埋着的**通路，不是已发生的事 | 仓库级信任门（首次接触问一次，默认不信任）；未信任时**不执行**项目级 hooks；`untrusted` 档下明确禁用；不继承全量环境 |
| H-18 | skill 正文是唯一没走不可信包裹的外部内容 | `tools/skill_tools.py:131-132` 包成 `<skill_content …>` 并写"请**遵循**其中的规则"；对比 `agent_runner.py:569` 对所有其他外部内容用 `wrap_untrusted(body, source=...)` | skill 正文走 `wrap_untrusted` + 显式"这些是外部来的指令"标注 |

**W5 验收**：MCP 工具在默认只读档下**必须**弹审批（造一个自报只读的假 MCP server）；未信任仓库的 `.ace/hooks.json` 不执行；skill 正文在上下文里带不可信定界。关联：#2(审C) #3(审C) #13 #25 #38。

---

### W6 · 协议与循环

| ID | 事项 | 证据 | 改法形状 |
|---|---|---|---|
| H-19 | `finish_reason` / `stop_reason` **从不被读** ⇒ 截断被当成完整 | `ace_client.py` 里两者**零命中**；`max_tokens` 硬编码 8192（`:172/174/184`）。级联：长 `file_write` 撞上限 → 工具 JSON 未闭合 → `agent_runner.py:156-163` 退化成 `args={}` → 执行层 400 → `_note_tool_failure` 计数 → **3 轮后该工具整会话熔断**，且因每次回喂 prompt 变长，截断是确定性复现的 | 读入并传播 `finish_reason`/`stop_reason`；`length` 标为**非计数**错误（"输出被截断，请拆分重试"），绝不触发熔断；`max_tokens` 可配 |
| H-20 | 反幻觉闸门只在 CLI，headless 没有 | `agent_runner.py` 自己注释称这是"本项目见过的最有害的失败模式"，但 `run_conversation:805-807` 对 `FINAL_REPLY` 直接 `print` 后 `return`，闸门实际在 `ai_code.py:5596-5603` | 闸门下沉到 `_stage_final_reply`（或两前端共用的 `resolve_final_reply`）：表现层决定措辞，引擎决定"无工具证据的完成声明不得作为最终回复" |
| H-21 | 20 轮自愈循环：证据只给头部、无指纹去重、headless 无熔断 | `execution_layer.py:443-454` `head = agent_output[:120]`，而最常见失败（JSON 后有冗余、缺 `</EXTERNAL>`）在**尾部**；`agent_runner.py:612-613/819` 逐字重发同一个 `PROMPT_ERROR_RETRY`；熔断只在 CLI（`ai_code.py:111-112, 5393`） | 给尾部/失败偏移附近证据；按 `(status, 归一化错误, 输出指纹)` 去重并退避；熔断放进共用决策层 |
| H-24 | **✅ 已修（见 §9.8）** `--serve` 协议声明 UTF-8，读侧却跟随控制台代码页 | `ai_code.py:51` 只调 `ace_io.harden_streams()`，而它只加固 stdout/stderr（`ace_io.py:57`）；`ace_serve.py:267` 直接用 `sys.stdin` ⇒ Windows 下 cp936，中文帧解成孤立代理字符（`\udcae`）⇒ 序列化抛 `UnicodeEncodeError` ⇒ 前端只见一条 `E_INTERNAL` 而会话仍活着（挂死）。`ace.cmd` 的 `PYTHONUTF8=1` 一直掩盖它；`test_all.py` 直接拉子进程，于是本机固定红 4 条 | 与 `harden_streams()` 对称：新增 `ace_serve._force_utf8_stdin()`，只在用真实 stdin 时 reconfigure 成 UTF-8；注入的 reader（测试 StringIO）不动 |
| H-25 | **未修（需设计决定）** 一次审批发出**两条** `permission_request` | 两个独立发射点：`ai_code.py:5559`（CLI 轮次循环看到 `PERMISSION_REQUEST` 时发）与 `core/ace_serve.py:459`（serve 宿主的 `ask_permission` 发）。`--serve` 下两个都跑 ⇒ 前端会弹两次对话框；对第二条的应答落到非 `wait_for` 期间，被回 `E_UNKNOWN_METHOD`（噪音，或有前端会当成失败）。实测：file_write + str_replace 两次审批 = **4 条**事件（2×2） | 定"谁拥有这条事件"：CLI 不该在宿主已经会发的时候再发一遍（或宿主只发"提问"不重复发事件）。这是**设计取舍**，不是补丁 |

**W6 验收**：构造一个确定性截断 → 断言**不触发**工具熔断；headless 零工具调用的"已完成" ⇒ 被拦且 exit≠0；同一畸形输出重复出现 ⇒ 第 2 次即中止而非跑满轮数。关联：#9(审B) #10(审B) #17。

---

### W7 · 依赖契约（需 owner 拍板）

| ID | 事项 | 证据 | 选项 |
|---|---|---|---|
| H-22 | "零第三方依赖"已不成立，stdlib 出口是死代码 | 实测：`ace_client._requests()` 调用点 **0**、`ace_http.urlopen_json_with_retry` 生产调用点 **0**（仅 `test_all.py` 与定义）；真实调用走 `ace_http.py:171/210` 的 `import requests`。而三处仍在承诺：`README.md` 徽章 `core deps-zero`、`ADR-004`、`INTERFACES.md:126`。⇒ 无 `requests` 的机器上两个前端**根本连不上模型** | **(a)** 接回 stdlib 出口并补一次"无 requests 环境"的测试；**(b)** 删死代码并改 README 徽章 / ADR-004 / INTERFACES §8 / `requirements.txt`。**建议 (b)**：`requests` 已是事实依赖，而"零依赖"的价值主要在执行层/CLI，不在模型调用。但这是**产品口径**决策 |

---

## 3. 顺序与依赖

```
W0 ──▶ W1 ∥ W3 ──▶ W2 ──▶ W4 ──▶ W5 ──▶ W6 ──▶ W7
```

- **W0 先做**：零风险、纯止血，同时把 H-01 做掉能立刻砍 71% 快照体积。
- **W1 与 W3 可并行**（无文件交集）。
- **W2 依赖 W3**：审批摘要要有东西可摘要，得先有 canonical host / canonical path。
- **W4 依赖 W3**：`resolve_target` 就是 `canonical_path` 的调用方。
- **W5 独立**，但 H-09 未做时它更危险（MCP 不受审批约束，叠上"审批一放全放"会放大）。

---

## 4. 全局验收门（沿用本仓库既有约定）

1. 每个工作包动工前取基线 `python test_all.py`（**本机 9 项 Go 执行器环境性失败是基线**，别当新问题）。
2. 每包用 `--only N` 跑相关段；收口时整跑一次。
3. `ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811` 零命中。
4. `[38]` 结构守卫全绿；本卡新增的守卫（H-04 / H-11 / W3 混淆参数表）各自要在 `--only` 下可单跑。
5. **每条 P0 必须先看着它红** 再修 —— 这是 `STRUCT-REFACTOR.md` §5 的教训：*"两套守卫各自是绿的，合起来才第一次碰面"*。
6. 文档里的数字不硬编码（`[39]` 会抓）；PowerShell 脚本**纯 ASCII**（本仓库已被中文字符坑过三次）。
7. 本卡新增文件已登记进 `docs/ARCHITECTURE.md` 权威树（R3 规则）。

---

## 5. 工作量的粗略口径

| 包 | 主要文件 | 量 |
|---|---|---|
| W0 | `.gitignore` / `guardian.py` / 4 篇文档 / `test_all.py` | S |
| W1 | `guardian.py` + `execution_layer._stage_snapshot` / `_rollback_current_snapshot` | S–M |
| W2 | `execution_layer._stage_permission` + `pending_permission` 结构 + 前端回放 | M |
| W3 | 新增 `core/canonical.py` / `sensitive.py` / `targets.py`；改 5 个消费者 | M–L |
| W4 | `tools/base._resolve_read_path` 收敛 + `file_ops` + `terminal_view` | S–M |
| W5 | `ace_mcp.py` + `ace_hooks.py` + `ai_code.py` 启动路径 + `skill_tools.py` | M |
| W6 | `ace_client.py` + `execution_layer` 循环 + `agent_runner` | M |
| W7 | 文档 + 删码或接回 | S |

**建议先做 W0 + W1**：两条都落在 `guardian.py` + `_stage_snapshot` 那一小块，一次改动能同时收掉 H-01/H-02/H-05/H-06/H-07/H-08 —— 性价比最高，且直接护住核心卖点。

---

## 6. 明确不纳入本卡（各自需要单独决策或立项）

| 事项 | 为什么不纳入 | 建议 |
|---|---|---|
| 四套 UI 合并 / "哪个栈才是产品" | 是产品决策，不是缺陷。实测重复度：工具卡片 ×3、权限对话框 ×4、spinner ×3、补全菜单 ×3；差分测试约 2900 行。且声明的主前端**从未被人眼看过**、不在 CI、`model_delta`/`status` 两个事件在契约里却无发射方 | 单独立项。若要立，先决"主前端是谁"，否则合并没有终点 |
| 成本硬预算 / 子代理用量核算 | 属新能力（当前 `_cost` 只显示不拦截；子代理嵌套调用不计入） | 二期 |
| 记忆 TTL / 归属 / 去重 / 相似度下限 | 现有触发时机是"话题刚变"，与"旧记忆最不相关"重合；需重新设计召回策略 | 二期 |
| 上下文压缩的"近期工具结果存活"不变式 | 需先定"按什么保留"（角色/种类而非轮数），是设计问题 | 二期 |
| 会话日志"可重建模型所见" | 属审计能力建设，改动面大 | 二期 |
| 归档 `ai angent` / `ace-r03` / `ace-agent-main` | **需 owner 决定**（三份各含未提交改动） | 本卡不碰 |

---

## 7. 审计本身的可靠性说明（重要）

本卡的证据来自三路独立只读审计。**归档时逐条复核，发现 1 条明确错误、1 条需收窄**，如实记录：

- **【推翻】** 审计称项目内的 `.guardian/signing_key` 可被 `file_read` 在只读会话读到。**实测不成立**：`sensitive_target(<项目>/.guardian/signing_key)` 返回"Agent 安全状态目录…"，`_AGENT_STATE_DIRNAMES` 已挡住。原断言漏看了这一层。
  但**同条的后半仍成立且更值得注意**：`SECURITY-AUDIT.md:78/:80` 声称"密钥解析集中在 `guardian.resolve_signing_key()`（配置 > `ACE_SIGNING_KEY` > …）"、"密钥必须在项目目录之外、落在项目内时直接拒绝启用" —— **`resolve_signing_key` 与 `ACE_SIGNING_KEY` 在代码里零命中、文档 2 处**，密钥实际位于 `<项目>\.guardian\signing_key`。即：审计记录里那条"已修复"的记忆是假的，只是恰好被另一个机制兜住。**建议把这一条并入 W1**（密钥位置 + 文档与实现对齐）。
- **【收窄】** 审计称 `open_file`"描述与实际不符"（H-14），代码确实在 `auto_open=true` 时立刻打开，但**默认是 `False`**（只给链接）。风险成立、措辞需按此校准。
- **审计过程中的机器影响**：审计为验证 8.3 短名绕过，在本机执行了 `os.listdir` 列出 `.ssh` 的**文件名**（只读、未改动任何内容）。H-10 的复现已用**不列举目录内容**的方式独立重做，结论一致。

**结论**：本卡的 `file:line` 引用总体可靠，可作为定位起点；但**开工前请对要动的那一处先看一眼代码**，不要仅凭本卡直接改。

---

## 8. 交接口径（给新会话）

- 本卡**自包含**：每条含「证据（文件:行）/ 改法形状 / 验收」。新会话可直接从 W0 开始，无需回溯审计原文。
- 纪律引用 `docs/design/STRUCT-REFACTOR.md` §4；验收口径引用本卡 §4。
- 编号 `H-` 独占命名空间。实现提交的 message 建议带 `H-NN`，便于日后 `git log --grep`。
- 若发现本卡与现码冲突，**以代码为准并更新本卡**（沿用 `INTERFACES.md` 开篇的取态）。

---

## 9. 实施记录：W0 + W1（2026-09-25）

### 9.1 改了什么

| 文件 | 项 | 变化 |
|---|---|---|
| `core/guardian.py` | H-01 H-02 H-06 | `EXCLUDE_DIRS` 补 6 项（含此前漏掉的 `.ace_env` 虚拟环境目录）；`snapshot()` 改为 `try/finally` —— 任何失败都清掉半成品目录再抛；新增 `gc_orphans()` 与 `guardian --gc`；新增 `count_credential_only_files()` |
| `execution_layer.py` | H-05 H-06 H-07 | `_stage_snapshot()` 改为返回 `Optional[dict]`（fail-close 时终止本轮）；新增 `_snapshot_unavailable()`；新增配置 `snapshot_required`（默认 `True`）；`_rollback_current_snapshot()` **返回契约由 `bool` 改为 `(bool, str)`**；`_stage_output_guard` 把回滚结果写进结果；`_stage_result` 两个返回分支都带 `snapshot_state`；`RoundCtx` 加 `snapshot_state` |
| `cli/ace_sessionlog.py` | H-05 | 新事件种类 `K_SNAPSHOT_FAIL = "snapshot/unavailable"` |
| `.gitignore` | H-01 | 补 `.ruff_cache/` `.pytest_cache/` `.mypy_cache/`、`.ace/hooks.json`、`.ace/permissions*.json`（**并修复了文件本身的混合编码，见 §9.2**） |
| `test_all.py` | H-01~H-07 H-23 | 新增 `[70]` 段（27 条断言）；`mktemp()` 登记 + `atexit` 回收 + `--keep-tmp`；`[38]` 新增 2 条守卫并重构 `_arch_tree_paths` 为列表保留 |
| `docs/INTERFACES.md` | H-03 | §5 去掉过时的 `--permission` 默认值警告（改为实测事实）；§10 把已闭环的 R-03 从"已知缺口"改为"✅ 已闭环"；删掉 §10 末尾那份"仍开放项"清单 |
| `docs/ADR-002-executor-boundary.md` | H-03 | "还没做的"里 `code_execute` 未接线的说法已过时（实测已有 `use_go_executor` 分支） |
| `docs/ARCHITECTURE.md` | H-03 | 权威树里 `ui/ace_keys.py` 重复登记的第二条（旧描述）删除；`design/` 下登记本卡 |
| `docs/design/ARCH-TREE-CHECK.md` | H-03 | 按"历史记录不动"的纪律**不改 §1 引文**，只在顶部导流说明补一句 Q-06 两半已闭环 |

### 9.2 过程中发现的**既有破损**（不是本卡规划的，但阻挡了验收）

**`.gitignore` 是混合编码，整套测试崩在中途。** `test_all.py:9604` 以 UTF-8 读 `.gitignore` 并断言含 `.ace_env/`，而工作区那份文件的第 59 行是 **GBK** 编码（`# 本地汉化产出（Claude Code 泄漏源码中文版）…`）→ `UnicodeDecodeError` → **基线跑不完**。

- 证据：`HEAD:.gitignore` 是合法 UTF-8（1506 字节）；工作区 1646 字节、第 59 行严格 UTF-8 解码失败、按 GBK 干净解码。
- 修复：逐行 UTF-8 解码 + 失败回退 GBK，整体重写为 UTF-8；**CRLF 55 处、行数 61、内容逐字不变**（原件备份在仓库外）。
- 防复发：`[70]` 新增一条断言盯 `.gitignore` 的 UTF-8 合法性 —— 这类"用 ANSI 工具追加一行"的编辑，本仓库已被坑过三次。

### 9.3 与卡片的**偏离**（都按"以代码为准并更新本卡"处理）

1. **H-01 的 `.ace/` 收窄为两个文件**。卡片写的是 ignore 整个 `.ace/`，但现码显示该目录既有该共享的（`commands/`、`plugins/`）也有本机私有的（`hooks.json`、`permissions*.json`）。忽略整个目录会挡住有意共享的项目命令。改为只忽略私有那两份，并注明"团队要共享请 `git add -f`"。
2. **H-06 收窄为"凭据形态文件"**（见 §2 表格内说明）。初版写成"任何被排除的文件都算内容"，**当场把既有的空项目写入断言全打红**（`[5]`/`[7]` 段）。根因：测试里复用的 sandbox 目录在跑到写工具时已含 `.poc_reports/` 等 ACE 自身产物，被误判成"用户内容"。修正后的判据只统计**命中凭据名单**的文件 —— 那才是"有内容却没有回滚点"。
3. **新增 H-23**（卡片外）。它是本次事故（`ai angent` 那份副本累积 **122 万文件 / 375 MB**）的直接根因：`mktemp()` 只建不收。十几行、带 `--keep-tmp` 逃生门，故一并做掉；若认为超范围可单独回退。

### 9.4 **H-08 未做**（精确回滚）

`guardian.rollback()` 现在是**整树还原**：删掉当前树里所有可收集文件、再按 `meta["files"]` 全量写回。这会连**本轮之外**的用户编辑一起回退（文档 `SECURITY-MODEL.md:36` 却写"只回滚本轮，不动无关修改"）。

没做的理由：改它要动 `rollback()` 的核心语义，而**现有 5 条断言依赖整树还原的行为**（`[3]` 的回滚恢复/新增文件清理、`[5]` 的"违规自动回滚"、`[10]` 的 `/undo` 等）。这属于"单独一个工作包 + 自己的先红测试"，塞进 W1 会同时动 snapshot 与 rollback 两条语义，验收时分不清是哪一条出的问题。**建议作为独立的 W1b 立项**。

### 9.5 验收证据（全量实测）

| 项目 | 结果 |
|---|---|
| 全量测试（最终） | **2183 / 2183 全绿 · 0 失败项 · 退出码 0**（不需要任何环境变量） |
| 改动前基线 | **2145 / 2149** —— 4 条 `--serve` 失败，**根因即 §9.8 的 H-24**，现已修 |
| 净增 | +38 条通过断言，**0 条新增失败** |
| `[38]` 结构守卫 | 13 / 13 全绿（含新增的"树无重复路径"与"文档不报旧账"） |
| `ruff` | `E9,F63,F7,F82,F401,F841,E711,F811` **All checks passed** |
| 新守卫的非空性 | 用 `git show HEAD:docs/INTERFACES.md` 验证：新守卫在**修改前**的文本上命中 2 行 / 6 个编号引用，在**当前**文本上 0 命中 —— 不是空守卫 |
| H-23 实战 | 清空后跑全量 → `.test_tmp` 顶层项 **0 → 0**（对照：修复前累积到 758 个目录 / 2368 文件 / 43.5 MB） |

### 9.6 公开契约变更（引用者需同步）

- **`ExecutionLayer._rollback_current_snapshot()` 返回值**：`bool` → `Tuple[bool, str]`。唯一调用点（`_stage_output_guard`）已同步；`test_all` 里两条既有断言已按新契约改写（其中一条**加强**为"失败必须带出原因"）。
- **新配置键**：`snapshot_required`（默认 `true`）。为 `false` 时快照不可用不再拒写，但**仍记事件日志 + 结果带 `snapshot_state="unavailable"`**。
- **`process_agent_output()` 返回 dict 新增字段**：`snapshot_state` ∈ {`created`, `empty_project`, `unavailable`, `rolled_back`, `rollback_failed`, `""`}。
- **新会话事件种类**：`snapshot/unavailable`。

### 9.7 遗留

- H-08（见 §9.4）、H-09 ~ H-22 未启动。
- 4 条既有 `--serve` 审批往返失败仍在（与本卡 W0/W1 无关，但属 §2 W6/W2 的邻域，值得在 W2 之前先查明）。
- `[70]` 段的 27 条断言目前**没有独立的 `_SECTION_DEPS` 声明**，因此 `--only 70` 会连带跑它之前的全部段（默认 `"*"`）。

### 9.8 追加：H-24 —— `--serve` 读侧编码（原"4 条既有失败"的根因）

**起因**：上次验收里那 4 条 `--serve` 审批往返失败，被当作"既有基线"记下了。查下去发现它们不是环境噪音，而是一条真缺陷。

**定位过程**（每步都有实测，不是读代码猜的）：

1. 独立复现子进程（`ai_code.py --serve --mock --permission readonly`）—— 逐帧打印后看到 `user.message` 的应答是
   `E_INTERNAL: UnicodeEncodeError: 'utf-8' codec can't encode character '\udcae' ... surrogates not allowed`，随后**会话不再有任何事件**，直到看门狗 120s 把它杀掉。
2. 同一复现里，第 1 轮（"现在几点"）能跑完，但引擎收到的 `user_message` 文本是 **`'鐜板湪鍑犵偣'`** —— 我发的是 `'现在几点'`。UTF-8 字节被按 GBK 解了一遍。
3. 根因：`core/ace_serve.py` 直接用 `sys.stdin`（`:267`），而 `ai_code.py:51` 的 `ace_io.harden_streams()` **只加固 stdout/stderr**（`ace_io.py:57` 的循环里没有 stdin）。Windows 下管道 stdin 跟随 ANSI 代码页 ⇒ 本机 cp936。
4. 为什么一直没被发现：`ace.cmd` 里 `set PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`（`ace.cmd` 第 10–11 行）把正常启动路径保护住了；而 `test_all.py` 是**直接**拉 `sys.executable ai_code.py --serve`，不带这两个变量。`docs/HANDOFF-FRONTEND.md:46` 也确实写着"跑测试要带 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`，否则中文输出变乱码" —— 即这条要求是**已知的**，只是靠人工纪律在兜。

**修复**：新增 `core/ace_serve._force_utf8_stdin()`，与 `ace_io.harden_streams()` 对称（那边管写、这边管协议帧的读），只在 `reader is None`（即真用 `sys.stdin`）时 reconfigure；注入的 reader（测试的 StringIO）不动。

**验收证据**：

| 项目 | 结果 |
|---|---|
| 修复前（不带变量） | 4 条失败 + 每条等满 120s 看门狗；`user_message` 文本为 `'鐜板湪鍑犵偣'` |
| 修复后（不带变量） | **2182 / 2182 全绿，退出码 0**；同一复现里文本为 `'现在几点'`，`permission_request` → 授权 → `final` → `session_end` 全部正常，不挂死 |
| 修复前（带变量） | 2181 / 2181 —— 这解释了为什么"本机基线的 9 项环境性失败"里没有它们 |
| 机制级证明 | 管道下子进程：`before=gbk` → `_force_utf8_stdin()` `changed=True` → `after=utf-8`，`中文往返` 解码码点与期望**逐字节相同**（`0x4e2d,0x6587,0x5f80,0x8fd4`） |
| 回归守卫 | `[70]` 新增 2 条断言：**故意清掉** `PYTHONUTF8`/`PYTHONIOENCODING` 拉子进程，断言 `user.message` 应答 `ok=True` 且中文原样往返 |

**为什么值得修而不是继续靠环境变量**：这条不修，每个 Windows 贡献者、以及任何直接 `python ai_code.py --serve` 起前端的人，都会遇到"中文一输就挂死、前端无任何提示"。而本仓库自己的原则（R-02 的教训原话）是"守卫该跟着代码走，而不是靠人工纪律"。

### 9.9 追加：H-25 —— 一次审批发两条 `permission_request`（**未修**）

上面修复后的复现输出里露出来的第二个问题：一次审批会发出**两条** `permission_request` 事件。

- 两个独立发射点：`ai_code.py:5559`（CLI 轮次循环看到 `PERMISSION_REQUEST` 状态时发）与 `core/ace_serve.py:459`（serve 宿主的 `ask_permission` 发）。
- 实测：`file_write` + `str_replace` 两次审批 = **4 条** `permission_request`（2×2）。
- 后果：前端会弹两次对话框；对第二条的应答落在 `wait_for()` 之外，被正常派发路径回 `E_UNKNOWN_METHOD: 不认识的方法: permission.answer`（噪音；若前端把它当失败，就会误报）。
- **没修的理由**：这要先决定"谁拥有这条事件" —— 是 CLI 不该在宿主已经会发的时候再发一遍，还是宿主只负责提问、不重复发事件。属**设计取舍**，不该由我替作者定。而且 `core/ace_serve.py` 与 `frontend/` 都是**未提交的在建工作**（`git status` 里是 `??`），`docs/HANDOFF-FRONTEND.md` 是它的交接说明。

### 9.10 本次调查的附带结论

- 那 4 条此前被我记为"既有基线"的失败，**实际是 H-24 的症状**，不是环境噪音。教训：把"跑不过"归因为环境之前，先确认它是不是在说真话 —— 这次它在说。
- `core/ace_serve.py` + `frontend/` + `docs/HANDOFF-FRONTEND.md` 均为**未提交**状态；H-24 的修复落在未提交文件上，因此本卡记录的验收只对当前工作树有效。

---

## 10. W2 实施记录：H-09（审批绑定到对象）

### 10.1 问题复述（实测）

`temp_grants` 是一个**工具名**的集合。一旦某个工具进了集合，`_stage_permission` 里那句

```python
if (tool_name not in self.permission.temp_grants
        and tool_name in self.permission.allowed_tools(self.permission.level)):
    _outside = self._outside_destructive_reason(...)   # 项目外覆盖闸门
    ...
    _egress_reason = self._egress_confirm_reason(...)  # 外发闸门
```

就**把两道闸门整体跳过**，直接落到 `can_execute()` 消费授权 → 带着**任意参数**执行。而被授权的重试是模型**重新生成**的一次调用（`PROMPT_PERM_GRANTED` → 重新出 JSON），参数可以完全不同。

`_outside_destructive_reason` 的 docstring 早就写着"并按**路径**授权：用户点的是这一个文件，不是这个工具以后随便写" —— 意图是对的，实现没跟上（与 H-05 同一类型）。

默认配置（无 `egress_allowlist`）下，外发闸门本就是唯一防线；readonly 档下更宽：`api_post` 不在 `allowed_tools("readonly")` 里，连闸门都进不去，用户的"同意"直接等于"这个工具随便用"。

### 10.2 修复

| 改动 | 说明 |
|---|---|
| 新增 `ExecutionLayer._gated_identity(tool_name, tool_call)` | 把"这次调用被闸门盯上的**对象**"算成可比较的身份：项目外覆盖 → `path:<解析后路径>`（`os.path.normcase` 兼容 Windows 大小写不敏感）；外发 → `host:<规范化主机>`（复用 `core.ace_net.url_host` / `normalize_host`）；`terminal_exec` → `cmd:<空白归一后的命令>`。返回空串 = 这次没有被闸门盯上的对象 |
| `_stage_permission` 顶部加校验 | 授权在 `temp_grants` 里**且**闸门确实记录过对象时，若本次身份与记录的不一致 ⇒ **作废这次授权**（`temp_grants.discard` + 清记录）并留痕 `grant_identity_mismatch`，随后重走闸门（会重新问人） |
| 四个"问人出口"都记身份 | 项目外闸门、外发闸门、`CONFIRM_TOOLS` 闸门、以及**权限不足**那条出口（readonly 下唯一会走的那条） |

**不误伤**：只有"闸门真正问过人并记下对象"之后才校验。来自持久规则（`allowed_by_rule`）、前缀白名单、或测试直接 `grant_temp` 的授权没有记录 ⇒ 沿用旧的按工具行为。

### 10.3 验收（`[70]` 新增 10 条）

| 断言 | 结果 |
|---|---|
| 覆盖项目外已存在文件 → 先问人；问人时记下 `path:` 身份 | ✅ |
| **★批准 x.txt 后改去覆盖 y.txt → 必须再问** | ✅ |
| 挪用被挡后陈旧授权已作废；被挡的那次没落到盘上 | ✅ |
| 同一对象重试 → 授权成立（这才是"只对这一个路径有效"） | ✅ |
| **★批准 benign.example.com 后改发 evil.tld → 必须再问** | ✅ |
| **★批准一条 `terminal_exec` 命令后改发另一条 → 必须再问** | ✅ |
| 直接 grant（无对象记录）不误伤 —— 项目内写不受影响 | ✅ |

**这一改当场把 4 条既有测试打红**（`terminal_exec 拦 rm -rf /` 等），根因值得记一笔：测试助手 `run_confirmed()` 的语义是"模拟用户已确认**这一次**调用"，但它只 `grant_temp(工具名)`、不带对象 —— **它正好踩着 H-09 那个洞**（先问 `echo hi`、再 `run_confirmed` 跑 `rm -rf /`）。所以修的是**助手**：现在它用 `_gated_identity()` 把对象一起模拟。产品一行没为测试让步。

### 10.4 H-25：一次审批两条 `permission_request`（已修）

- 两个发射点：`ai_code.py` 的 `json_mode` 分支 与 界面宿主的 `ServeUIHost.ask_permission`（`core/ace_serve.py`）。
- 触发条件：`self.json_mode = bool(cfg.get("json") or cfg.get("serve"))` —— **`--serve` 会把 `json_mode` 也置真**，于是两者必然同时命中。
- 实测：`file_write` + `str_replace` 两次审批 = **4 条**事件（2×2）；前端会弹两次对话框，而对第二条的应答落在 `wait_for()` 之外、被回 `E_UNKNOWN_METHOD: 不认识的方法: permission.answer`。
- **所有权判定**（从代码推出来的，不是我拍的）：宿主那一发在**真正问人**的那一刻、并就地阻塞等答案，位置更准，且 `[46]` 的"四类提问各发了对应的事件"正是断言它；CLI 那一发只在**没有宿主**（纯 `--json`）时才需要。
- 改动：`if self.json_mode and getattr(self, "_ui", None) is None:` —— 一行条件。
- 回归断言（`[70]` 新增 2 条）：判据取"**每个 `permission.answer` 都落在 `wait_for()` 里**"，即整场交换没有任何 `E_UNKNOWN_METHOD` 的 permission.answer 应答。比数事件条数稳，不依赖 mock 台词。

### 10.5 H-26：测试把会话写进仓库自己的 `.ace_sessions/`（**当时未修**，已量化 —— 后来已修，见 §16）

- 现象：`[69]` 等子进程测试用 `cwd=str(FOLDER)` 拉 `ai_code.py --serve`，而 `--serve` 的 `project_root` 取 cwd ⇒ 测试会话被写进**仓库自己的** `.ace_sessions/`。
- 量化：**每跑一次全量 +8 个文件**（实测 1164 → 1172）。本轮会话内该目录从 **972 涨到 1172**。
- 影响：该目录是**用户真实会话历史**（`/sessions`、`@session N` 都读它）。测试垃圾与真实记录混在一起，且无上限增长。它与 H-23 是同一类问题（只生不灭），只是长在了另一个目录。
- **我只修了自己新增的那两处**（H-24/H-25 的子进程改成在 `mktemp()` 目录里跑，`ai_code.py` 用绝对路径调用，`sys.path` 自解析不受 cwd 影响）。**剩下的 8 个/轮来自既有测试，未动** —— 那需要改 `[69]`/`[67]`/`[68]` 等多处 `cwd=str(FOLDER)`，属独立工作包。
- **与那次偶发失败的疑似关联**：全量跑出现过一次 `@session 越界编号如实报错（不静默什么都不做）` 失败（该测试造一条会话后断言 `@session 99` 找不到），三次相同跑里出现一次。`@session` 的编号解析若与那份目录的规模有关，就会随污染增长而漂移。**未证实**，如实记为"疑似"。

### 10.6 本轮验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2196 / 2196 全绿 · 0 失败项 · 退出码 0**（连续三次跑，其中两次全绿、一次出现上述偶发的 `@session` 失败） |
| 上一轮 | 2183 / 2183 |
| `ruff` | `E9,F63,F7,F82,F401,F841,E711,F811` **All checks passed** |
| `.test_tmp` | 跑前 0 → 跑后 **0**（H-23 持续生效） |
| `.ace_sessions` | +8 / 轮（H-26，既有测试所致） |

**改动文件（W2）**：`execution_layer.py`（身份函数 + 四处出口记录 + 顶部校验）、`test_all.py`（`run_confirmed` 助手修正 + `[70]` 新增 12 条断言）、`ai_code.py`（H-25 一行条件）。
**仍未 commit**：全工作树等你决定提交时机。

---

## 11. W5 实施记录：扩展面走同一条闸门（H-16 / H-17 / H-18）

### 11.1 H-16 · MCP：权限类改由 ACE 指定

| 项 | 此前 | 现在 |
|---|---|---|
| 权限类 | 服务器自报 `annotations.readOnlyHint: true` → 映射成 `read` | **一律 `high_risk`**；`readOnlyHint` 只作描述。要放宽必须在配置 `mcp_permissions` 里显式写（`{"<server>": {"<tool>": "read", "*": "write"}}`） |
| 外发闸门 | `register_into` 只传 name/permission/description/parameters/handler，**`egress` 从来没设过** ⇒ 整条 SEC-03 对 MCP 失效 | `tool_spec` 加 `egress: True`，`register_into` 透传 |
| 闸门能否识别目的地 | `_egress_confirm_reason` 认不出目的地时 `return None`（**不问**） | 新增分支：`mcp__` 前缀且认不出目的地 ⇒ **问人**（"目的地无法判定"）。认不出恰恰是最该问的情形 |
| 授信粒度 | 一次批准 = 这个工具以后随便调 | `_gated_identity` 新增第 ④ 类：MCP 工具绑**参数摘要**（`mcp:<sha256[:16]>`），换参数即换对象 |
| 注册失败 | `except Exception: continue` —— 静默 | 记进 `register_errors`（一个拼错的 kwargs 就能让整批 MCP 工具凭空消失，此前没人知道） |

**为什么 `read` 桶等于"免审批"**：`_LEVEL_SOURCES["readonly"] == ("read",)` —— 默认只读档允许全部 `READ_TOOLS`。所以"服务器自报只读"实际换来的是"**默认放行**一个跑在 ACE 沙箱之外的子进程"。

**又是"测试编码了漏洞"**：既有断言把旧行为钉死了两处 ——
`check("权限默认从严：没写 readOnlyHint 就按写处理", … tool_permission({…readOnlyHint: True}) == "read" …)` 与
`check("readonly 下 readOnlyHint 的 MCP 工具直接可用", _r43["status"] == "SUCCESS")`。
**第二条就是那个漏洞的白纸黑字**。已改写为新契约（并保留 ★ 前缀让它在输出里显眼）。Section 43 里那些"写档下调 MCP 工具期望 SUCCESS"的调用改成 `run_confirmed(...)` —— 现在它们要授权，测试必须模拟用户点头。

### 11.2 H-17 · 仓库自带的 hooks 默认不加载

- **问题**：`.ace/hooks.json` 与 `.ace/plugins/*/hooks.json` 来自**被打开的那份仓库**，却在 `ExecutionLayer.__init__` 里以 `shell=True` 执行（`core/ace_hooks.run_hook`）—— 时机是任何权限判定之前，并且继承整个环境。即 `git clone <陌生仓库> && ace` = 执行它的 shell 命令。
- **信任门（默认不信任）**：新增 `ExecutionLayer._project_hooks_trusted()`。要跑必须显式点头，二选一：
  `trust_project_hooks: true`，或把项目根写进 `trusted_workspaces: [<路径>]`。
  比较用 `resolve()` 后的**规范路径**（大小写/短名/`..` 都归一），不是字符串前缀 —— 后者正是 H-10 那类绕过的来源。
- 未受信任时：项目 hook 文件**连解析都不做**；插件照旧加载（命令是 markdown，不是命令执行），但**插件钩子被跳过**，且 `hook_ignored` 里写明原因；`project_hooks_note` 给出可操作的两条路。**不静默**。
- **环境**：`core/ace_hooks.run_hook` 改为先摘掉 `_HOOK_ENV_DENY`（ACE 自己的 `AGENT_API_KEY`/`ACE_*_API_KEY` + 常见厂商 key）再传。**并如实说明这只是"少给一点"、不是边界** —— 真正的边界是上面的信任门，因为环境变量全集无法穷举（这个教训 H-06/H-11 已经给过一次）。
- **用户自己的 `config["hooks"]` 不受影响** —— 那是他自己写的代码。既有 hooks 测试正是走这条，所以全部保持绿色。

### 11.3 H-18 · 技能包封可伪造（**偏离卡片**）

卡片原文要求"skill 正文走 `wrap_untrusted`"。**我改成了另一件事，理由如下**：

`wrap_untrusted` 的收尾语义是"这些是**数据**、不要当指令"；而技能正文**天生就是给模型遵循的规程** —— 套上去等于把这个功能废掉。文件/网页/终端输出是真正的数据，所以它们走 `wrap_untrusted` 是对的；技能不是那一类。

技能这一处**真正可修**的硬缺陷是**包封可伪造**：

| 注入点 | 此前 |
|---|---|
| 技能名直接插进标签 | `f"<skill_content name={skill['name']}>"` —— 一个叫 `x></skill_content>…` 的技能就能提前闭合边界 |
| 正文自带结束标签 | `body` 原样插入 ⇒ 正文里的 `</skill_content>` 同样能提前闭合 |

技能目录正是**第三方技能包**的落点（`--skills <dir>`），两条都够得着。现在：名字经 `re.sub(r"[^\w\-.]", "_", …)` 清洗、正文里的 `</skill_content>` 被替换、并在包封后明写**出处**与"越界要先问用户"的兜底。

### 11.4 W5 验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2208 / 2208 全绿 · 0 失败项 · 退出码 0** |
| 上一轮 | 2196 / 2196 |
| `ruff` | `E9,F63,F7,F82,F401,F841,E711,F811` **All checks passed** |
| 新断言 | H-16 ×5、H-17 ×7、H-18 ×3（其中 3 条是既有断言按新契约改写） |
| `[70]` 段头出现次数 | 1（确认没有重复插入） |

**改动文件（W5）**：`core/ace_mcp.py`、`core/ace_hooks.py`、`execution_layer.py`、`tools/skill_tools.py`、`test_all.py`。
**仍未 commit**。

---

## 12. W3 实施记录：单一来源 + 单一入口（结构主线 A）

这一包是**治本**的那一包：H-01/H-06/H-11/H-16/H-18 之所以会"两边各写一份然后漂"，根子在这里。

### 12.1 两个新模块 + 一个搬家的模块

| 新文件 | 作用 |
|---|---|
| `core/canonical.py`（46 行） | `canonical_path()` / `canonical_text()` / `same_file()` —— 把"拼写"归一到"OS 实际认出的那个东西" |
| `core/sensitive.py`（139 行） | 敏感名单的**唯一来源**：`sensitive_target()`（① agent 能不能碰）+ `is_credential_file()`（② 内容是不是秘密）+ 全部目录/启动项/Agent 状态常量 |
| `core/targets.py`（48 行） | `destructive_targets(tool, params)` —— "这次会动哪些路径"的**唯一入口** |

### 12.2 H-10 · 别名绕过（本机可复现的真实漏洞）

`Path.resolve()` 在 Windows 上走 `GetFinalPathNameByHandle`，实测**一并解决** 8.3 短名、尾点/尾空格、大小写与 `..`。修复只有一句话：**名单判定在规范路径上做一遍，再在原串上做一遍**（原串那遍是超集兜底 —— 终端命令里的 `%USERPROFILE%` 展开不了，只能按原串看）。两遍都判只会**多**命中，不会少。

| 传入 | 修复前 | 修复后 |
|---|---|---|
| `C:/Users/<me>/.ssh/config` | `'敏感目录: .ssh'` | 同（不变） |
| `C:/Users/<me>/SSH~1/config` | **`None`（放行）** | `'敏感目录: .ssh'` |
| `C:/Users/<me>/.ai_code.json.` | **`None`（放行）** | 命中 |

> 8.3 短名 `SSH~1` 在本机**真实存在**（探针实测），所以这不是理论问题。

### 12.3 H-11 · 两份凭据名单双向漂移

**先说一个设计上的关键判断**：两个消费者问的是**不同的问题** ——

- ① 「agent 能不能碰这个路径？」（文件工具 / 终端 / 命令执行）
- ② 「这个文件的内容是不是秘密？」（guardian：要不要把它**明文复制**进快照）

**硬合成一份是错的**。最大的差集是 `.env`：项目内 `.env` 是正常开发对象（"帮我建个 .env"必须能用），① 不能拦；但快照是明文副本，② 必须排除。所以正确做法是**同源 + 把差异显式写出来**（`TOOL_BLOCKED_BASENAMES = CREDENTIAL_BASENAMES - {".env"}`，连理由一起写在旁边）。

修复效果（实测）：

- **方向 A（安全）关闭**：25 个凭据名（`.npmrc` `.pypirc` `.pgpass` `.git-credentials` `.netrc` `.htpasswd` `.terraformrc` `.dockercfg` `.my.cnf` …）此前**被明文复制进 `.guardian/snapshots/**/files/`**，而 `guardian.py` 的注释正写着"绝不能"。现在两边同判。
- **方向 B（可用性）收掉 3 个**：`.claude.json` / `client.ovpn` / `key.asc` 此前 guardian 不快照、工具却允许写 ⇒ **写入不可回滚**；现在 ① 也拦（它们本就是凭据/证书材料）。
- **残余（已知取舍，非漏项）**：`.env` / `.env.local` 仍是"① 允许写、② 不快照"⇒ 这类写入**不可回滚**。卡里显式记着；要收紧的正确做法是"写凭据形态目标时额外确认"，而不是把它塞回 ① 里一拒了之。
- `tools/file_ops.py` 改为**直取** `core.sensitive`（不再经 guardian 转出）—— 转出层就是下一份会漂的名单。

### 12.4 H-12 · `deny` 规则被 `..` 绕过 + 一个"一物两用"的坑

`_norm_path` 的 docstring 写着"统一小写盘符"，**而函数体从不小写、也从不折叠 `..`**。于是用户写 `{"tool":"file_write","pattern":".env","action":"deny"}`（"这个仓库里别碰 .env" 正是规则的设计用例），模型调 `file_write(path="tools/../.env")` ⇒ `"tools/../.env".startswith(".env")` 是 False ⇒ **deny 不命中，工具解析后真的写了 `<root>/.env`**。deny 是用户当墙用的那条，静默不命中比没有更糟。

修完发现它还有**第二种用途**，这值得单独记一笔：

| 用途 | 折大小写？ |
|---|---|
| `rule_matches`（**比较**） | 该折 —— Windows 路径大小写不敏感 |
| `suggest_rule`（**生成给用户看的规则文本**） | **不该折** —— 折了就把 `README.md` 变成 `readme.md`，用户拿到一条他没想要的规则 |

第一次改动把 `suggest_rule` 打红了（`建议模式：文件类取所在目录`）。修法是给 `_norm_path` 加显式开关 `fold_case`，**把差异写在签名上**而不是靠两处各记一份 —— 正是这一包的主题。

细节：目录模式（结尾带 `/`）保留结尾斜杠，否则 `pattern="docs/"` 会连带命中 `docs2/`。

### 12.5 H-13 · 三处一起漏了同一项

`file_move(source=…, dest=…)` 的 **`source`** 此前对**三个**消费者都不可见 ——

| 消费者 | 后果 |
|---|---|
| `_outside_destructive_reason` | 把项目外**已存在**的文件"移走"= 删除它，**不问人** |
| `ace_rules.rule_matches` | 用户的 deny 规则**看不见**它 |
| `_gated_identity` | 授权绑不到源那一半（换了源也算同一个对象） |

三处都只读 `path`/`dest`/`target`。而 `SECURITY-MODEL.md` 承诺过"覆盖或删除项目外已经在那儿的文件会逐次确认"—— `file_delete` 做到了、`file_move` 没有；项目外也没有快照可回滚 ⇒ 一次调用永久丢一个文件。

修法：**唯一入口** `destructive_targets()`（`file_move` 返回 `[source, dest]`，源在前），三处都改成问它。

### 12.6 W3 收口物：一张「混淆参数表」

同一个判据散在多处就会各自漂。`[70]` 里加了这张表：把"别名 / 大小写 / 尾点 / `..`"一次性摊开喂给**每个**消费者，全会给同一个答案。**新增消费者必须加进这张表** —— 这是防它再次漂的唯一机械手段。

### 12.7 W3 验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2220 / 2220 全绿 · 0 失败项 · 退出码 0** |
| 上一轮 | 2208 / 2208 |
| `ruff` | `E9,F63,F7,F82,F401,F841,E711,F811` **All checks passed** |
| 新断言 | H-10 ×3、H-11 ×2、H-12 ×3、H-13 ×4 = 12 条 |
| 过程中打红的既有断言 | 1 条（`建议模式：文件类取所在目录`）—— 根因是"一物两用"，已按主题修正 |

**改动文件（W3）**：新增 `core/canonical.py` / `core/sensitive.py` / `core/targets.py`；改 `tools/base.py`、`tools/file_ops.py`、`core/guardian.py`、`core/ace_rules.py`、`execution_layer.py`、`test_all.py`。
**仍未 commit**。

---

## 13. W4 实施记录：路径类工具统一入口（H-14 / H-15）

### 13.1 H-14 · `open_file` / `edit_file`：从只读路径启动进程

问题由三部分组成（都不是"某个参数没校验"那么小）：

| # | 事实 | 后果 |
|---|---|---|
| 1 | 两个工具都是 `PERM_READ` ⇒ **默认只读会话下免审批** | 不需要任何授权就能走到 |
| 2 | 路径经 `_resolve_read_path`（只做 `expanduser` + 拼接 + `resolve`）—— **没有 `_confined`、没有 `sensitive_target`** | 模型给的任意路径直达 `os.startfile` |
| 3 | `os.startfile` 走 ShellExecute 的默认动作 | 对 `.exe`/`.bat`/`.lnk` 就是**运行**它 |

而且 `open_file` 还读一个**未登记在 schema 里**的 `auto_open`（`params.get("auto_open")`）—— 模型照样能传，传了就立刻打开。审计那句话是准的：这是"单一边界"声称不存在的那条旁路，因为它**完全绕开 `ace_execpolicy`**。

**修复思路的取舍**（这一步我改过一次判断，值得记）：最初给两个工具都加 `confirm=True`，但立刻意识到那会打断 6+ 条既有断言（连"空路径报 400"都要先过人），**而且解决的不是真正危险的那件事**。重新问"到底什么危险"：

- `os.startfile(<目录>)` → 打开资源管理器 —— 不是代码执行
- `os.startfile(<文件>)` —— **运行关联程序**，而后缀黑名单**天生补不全**（`.py` 被关联到 python.exe 就是执行）
- `Popen(["code", …])` → 打开编辑器

所以正确切法是**按"该工具是否以启动进程为本职"分开**：

| 工具 | 处理 | 理由 |
|---|---|---|
| `open_file` | **文件一律只给链接**（`opened=False` + `file:///` URI）；**目录仍直接打开**；`auto_open` 从 schema 与实现里**移除** | 用户**点击链接**才打开 —— 这一步由人做，不由模型做。目录那一条是资源管理器，不是代码执行 |
| `edit_file` | `confirm=True`（每次调用都要人点头） | 它的**本职就是**把文件递给编辑器，降级成链接就等于删掉这个功能 |

另有**不该有机会被确认**的硬拦截（`ToolExecutorBase._os_handoff_guard`）：凭据/密钥/自启动入口、以及可执行/脚本后缀 ⇒ 直接 403。这也让 `SECURITY-AUDIT.md` 里那句"可执行扩展名拒绝清单已生效"**第一次成为真的**（此前代码里并不存在）。

### 13.2 H-15 · `terminal_view` 的 `-` token 跳过

```python
if token.startswith("-"):
    return False          # ← 整个 token 被豁免，包括 `--output=C:\...\leak.txt`
```

`git log --output=<路径>` 能从**只读工具**写出项目外文件（不问人、不快照）。而 `ace_execpolicy` 早在 **SEC-06** 就修过这同一件事（`= 右边再查一次路径`）—— `terminal_view` 没跟上。**同一个洞的两半，修了一半。**

修复：取"值部分"再看 —— `--opt=<路径>` 取等号右边，`-o<路径>` 取开关字母之后。判"像不像路径"用**显式判据**而不是 `os.path.isabs`：后者在 Windows 上不认 POSIX 绝对路径（`-o/tmp/x` 会漏），而这条工具两端都要站得住。

token 表实测（新增断言盯着）：

| token | escapes |
|---|---|
| `--output=C:/Users/x/leak.txt` | **True** |
| `-o/tmp/leak.txt` | **True** |
| `--target-directory=/tmp/x` | **True** |
| `--exclude=*.py` | False（不误伤 glob） |
| `-la` / `--oneline` / `-rf` | False（纯开关） |
| `src/main.py` / `docs/a.md` | False（项目内） |

端到端：`terminal_view` 跑 `git log --output=<项目外>` ⇒ **403 且泄漏文件未创建**；正常 `git log --oneline -1` 仍 SUCCESS。

### 13.3 W4 验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2230 / 2230 全绿 · 0 失败项 · 退出码 0** |
| 上一轮 | 2220 / 2220 |
| `ruff` | `E9,F63,F7,F82,F401,F841,E711,F811` **All checks passed** |
| 新断言 | H-14 ×9、H-15 ×2 = 11 条 |
| 按新契约改写的既有断言 | 4 条（`edit_file` 404 与记事本回退走 `run_confirmed`；`open_file auto_open` 从"回退记事本"改成 ★"不再启动任何进程"） |

**改动文件（W4）**：`tools/base.py`、`tools/file_ops.py`、`tools/registry.py`、`tools/terminal_view.py`、`test_all.py`。
**仍未 commit**。

---

## 14. W6 实施记录：协议与循环（H-19 / H-20 / H-21）

### 14.1 H-19 · `finish_reason` 从不被读 ⇒ 截断被当完整

**先说清它为什么危险**（级联，每一环都核对过代码位置）：

长 `file_write` 撞上输出上限 ⇒ 工具调用 JSON 未闭合 ⇒ `tool_calls_to_protocol` 的
两条 JSON 修复路都失败 ⇒ `args` 退化成 `{}` ⇒ 那次工具调用必然报 `400` ⇒
执行层的"同工具同错误连续失败"计数 +1 ⇒ **3 次后该工具被整会话熔断**
（"工具 file_write 已连续失败 3 次，已被熔断"）。而每次回喂的 prompt 都在变长，
所以截断是**确定性复现**的 —— 模型永远修不好，工具永远被禁。

**关键定位**：这条级联是 **`agent_runner` 特有**的路径。CLI 的流式截断会走
`FORMAT_ERROR`（不是工具执行错误），**不会**计进那个熔断计数 —— 那条由 H-21 覆盖。

**修复**：`agent_runner` 的两个生成函数（`_generate_tools` / `_generate_text`）在拿到
响应体后**先看 `finish_reason`**，为 `length` 就抛新的 `TruncatedOutput` ——
既不产出 `args = {}`、也不报 400、更不计进熔断。`ai_code._model_error_hint` 为它
加了精确提示（新增 i18n 键 `model_truncated_hint`，三语各 +1 键，总数 765）。

`run_conversation` 已有的通用 `except` 会**直接 return**，所以 headless 也是
"如实报错并停"，不是"回喂一个假的参数错误"。

### 14.2 H-20 · 反幻觉闸门只在 CLI

`claims_completed_action()` 存在于 `agent_runner`，但**只有 CLI 用了它**
（`ai_code.py`），而 `run_conversation`（headless / CI / SDK）对 `FINAL_REPLY`
直接 `print` 然后 `return` —— **退出码 0**。而 headless 恰好是"没人在看"的那个模式。

**修复**：闸门**下沉到执行层的 `_stage_final_reply`**（两个前端都经过这里）。判据用
`tools_ran_this_task`（本次任务内成功执行过的工具数，在 `_stage_new_task` 里按
"一次用户请求"重置 —— 与 CLI 原先的 `_tool_ran_in_request` 同口径）。两次机会：
第一次回喂 `PROMPT_UNVERIFIED_CLAIM`，第二次返回 `GUARD_VIOLATION`
（`rule=unverified_claim`）—— 两个前端都会按失败处理，**不会打绿 ✓、headless 不再退 0**。

判据与文案搬进新的 `core/ace_claims.py`：`execution_layer` 不能 import
`agent_runner`（会成环），而 `agent_runner` 必须保留同名入口（`test_all` 从那里取它）。
`agent_runner` 保留**转发**（与 `tools/base.sensitive_target` 同一手法 —— 显式转发
而不是 `# noqa: F401` 重导出，因为本仓库 `[38]` 有一条自己的 F401 守卫，不认 noqa）。

### 14.3 H-21 · 自愈循环

| 问题 | 修复 |
|---|---|
| 证据只给头部 `[:120]`，而最常见畸形（`answer.` 后有冗余 JSON、缺结尾 `</EXTERNAL>`）**在尾部** | 首尾各给一段：短输出整段给，长输出 `头120 + …（中间省略 N 字符）… + 尾120`。只给头部时模型看到的是一段完全正常的开头，"对照它自查"是空话 |
| 逐字重发同一个 `PROMPT_ERROR_RETRY` | 新增 `_retry_fingerprint(status, reason, 输出原文)`；同一指纹第二次出现 ⇒ 结果带 `abort: True`。用**输出原文**而不是提示词做指纹 —— 提示词是我们拼的，长度/编号一变就判成不同失败 |
| 熔断只在 CLI（`_fail_streak`，且 headless 连 20 轮上限都没有） | `abort` 由**执行层**判定，两个前端各自honor：CLI 复用既有 `stall_abort` 文案后 `return`；`run_conversation` 打印并 `return` |

### 14.4 W6 验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2240 / 2240 全绿 · 0 失败项 · 退出码 0** |
| 上一轮 | 2230 / 2230 |
| `ruff` | `E9,F63,F7,F82,F401,F841,E711,F811` **All checks passed** |
| 新断言 | H-19 ×2、H-20 ×3、H-21 ×5 = 10 条 |
| i18n | 新增 `model_truncated_hint` ×3 语言（总数 765，三语键集一致断言仍绿） |

**改动文件（W6）**：新增 `core/ace_claims.py`；改 `agent_runner.py`、`execution_layer.py`、`ai_code.py`、`locales/{zh,en,ja}.json`、`test_all.py`。
**仍未 commit**。

---

## 15. 收口：还剩什么

| 项 | 状态 | 说明 |
|---|---|---|
| **H-08** 精确回滚 | **未做** | 需独立工作包（现有 5 条断言依赖整树还原语义），见 §9.4 |
| **H-22** 依赖契约 | **✅ 已实施 (b)** | 删死码（`_requests()` + `urlopen_json_with_retry` + 3 条用例）、`requirements.txt` 与 `setup_env.REQUIRED` 改成事实、12 份活跃文档口径修正、7 条守卫。**唯一行为改动**：启动器开始装 `requests`。见 §17 |
| **H-26** 测试污染 `.ace_sessions` | **✅ 已修** | 见 §16 |
| 那 4 条 `--serve` 失败 | **已修** | 根因是 H-24，不是环境噪音，见 §9.8 |

**验收总账**：全量 **2245 / 2245 全绿 · 退出码 0 · 零环境变量要求**；`ruff` 全过；
`[38]` 结构守卫全绿。

---

## 16. H-26 实施记录：测试往仓库自己的 `.ace_sessions/` 写会话

### 16.1 为什么是"用户真实数据被污染"

`ai_code.py` 把会话事件日志定在 `<project_root>/.ace_sessions/`，而 `project_root` 默认取 cwd。
测试里那些 `ai_code.py` 子进程只给了 `cwd=str(FOLDER)`、**没给 `--project-root`** ——
于是测试会话直接写进了**仓库自己的** `.ace_sessions/`，而那正是 `/sessions`、`@session N`
读的目录。**测试垃圾与用户真实记录混在一起，且无上限增长。**

**量化**（修之前）：每跑一次全量 **+8 个文件**。本会话期间该目录从 972 涨到 1254。

### 16.2 修复

| 位置 | 处理 |
|---|---|
| `[45]` `_run_json45`（headless 事件流，2 个调用点） | 助手内部统一注入 `--project-root <mktemp()>` |
| `[67]` 三个入口里的两个 `ai_code.py`（`--preview` / `--input`） | 加 `--project-root <mktemp()>` |
| `[69]` 两个 `--serve` 子进程 | 加 `--project-root <mktemp()>` |
| `[70]` 我新增的两处（H-24/H-25） | 上一轮已改成临时 cwd |

**为什么用 `--project-root` 而不是改 cwd**：`[67]` 那几条断言依赖 cwd 下的横幅/目录显示，
改 cwd 会动到别的东西。而 `--project-root` 只改会话日志与工具的项目边界 ——
且实测**没有任何断言依赖子进程 `project_root` 的取值**（grep 过）。

### 16.3 防回归：一条**行为级**守卫

放在整跑末尾（增长只有跑完才看得出来）：

```python
_sn = len(list(_SESS_DIR.glob("*.jsonl")))
check("H-26 测试没有往仓库自己的 .ace_sessions/ 写会话", _sn <= _SESS_BASELINE, ...)
```

基线在导入时记录。谁再给 `ai_code.py` 子进程漏了 `--project-root`，它当场红。
**为什么不是源码级断言**：源码级只能盯已知调用点，而漏的往往是新加的那一处。

### 16.4 存量清理（**移走，不删**）

判据：`session/start` 那行里有 `"model":"mock"` —— **真实的用户会话不会用 mock**。

| 类别 | 数量 | 处理 |
|---|---|---|
| `"model":"mock"` | **992**（12 MB） | **移到仓库外** `Desktop\_ace_sessions_mock_backup\`，可随时还原 |
| 非 mock（有 `session/start`，08-29 ~ 09-25） | 53 | **不动**（大概率是真实会话） |
| 没有 `session/start`（残缺） | 209 | **不动**（无法判定） |

结果：`.ace_sessions` **1254 → 262**。

### 16.5 H-26 验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2241 / 2241 全绿 · 退出码 0** |
| `.ace_sessions` 增量 | **8 → 0**（跑前 1254 → 跑后 1254，第二次跑也 0） |
| `ruff` | All checks passed |

**改动文件**：`test_all.py`（4 处 spawn 注入 `--project-root` + 末尾守卫）、本卡。

---

## 17. H-22 实施记录：依赖契约 —— 删死码 + 把口径改成事实

**选择**：你拍板 **(b)** —— `requests` 是事实依赖，删掉没人走的 stdlib 出口，并把文档口径改成事实（不选 (a) 接回 stdlib）。

### 17.1 先量再改：三处事实

探针做法：`sys.meta_path` 前置一个对 `requests` 抛 `ImportError` 的 finder，再跑真实代码路径。

| 检查 | 实测 | 含义 |
|---|---|---|
| `from core import ace_client, ace_http` | **OK** | 模块级不硬 import `requests`；"没有 requests 也能 import" 这句**是真的** |
| `ace_client._run(...)`（真发一次请求） | 抛 `builtins.ImportError: No module named 'requests'` | 模型调用**没有回退**，而且报的是裸 `ImportError`，不是可操作的提示 |
| `ace_http.classify_requests_exception(ValueError("x"))` | `"other"` | 纯判定部分确实不依赖 `requests`，所以无 requests 的机器仍能跑这部分测试 |
| `setup_env.REQUIRED` | `('prompt_toolkit', 'textual', 'rich')` | **启动器不装 `requests`** —— 干净机器上装完界面依赖照样连不上模型 |

调用点计数（全仓 `grep`）：`ace_client._requests()` **0**、`ace_http.urlopen_json_with_retry` **0**（只有定义与 `test_all.py`）。真实出网唯一走 `ace_client._run` → `ace_http.request_with_retry`。

⇒ **"核心零依赖"在模型调用这一格是假的，而且假得有代价**：一条没人走的第二份实现撑着那句话，同时启动器偏偏没装真正需要的那个包。

### 17.2 删掉的死码

| 位置 | 处理 | 为什么是删而不是留 |
|---|---|---|
| `core/ace_client.py` `_requests()` | 删（无调用点） | 它看着像"没 requests 也有救"，真发请求时 `request_with_retry` 直接 ImportError —— **一个会骗人的兜底比没有兜底更糟** |
| `core/ace_http.py` `urlopen_json_with_retry()` | 删（生产调用点 0） | R-03 把两个前端合并进 `ace_client` 之后就没人走了；它同时是"纯 stdlib 也能调模型"这句话的唯一载体 |
| 同一文件的 `import json` / `urllib.error` / `urllib.request` / `typing.Dict` | 随之删 | 只被上面那个函数用；**是 `ruff` 的 `F401` 当场抓出来的**，不是靠眼睛找 |
| `test_all.py` 的 3 条 urllib 用例 | 删，原地换成 2 条 H-22 守卫 | 被删函数的用例不该留着；换成"这条路不许回来"的断言 |

### 17.3 依赖契约改成事实

| 文件 | 改动 |
|---|---|
| `requirements.txt` | `requests` 从"**可选**：接入真实模型 API（ai_code / agent_runner）"改为"**必需**：模型调用与联网工具"；顺手修掉失效的 `agent_runner` 指针（R-03 之后模型客户端只剩 `core/ace_client.py`） |
| `setup_env.py` | `REQUIRED` 加 `requests` —— **这是本次唯一的行为改动**：`ace --setup` / `ace --install-ui` / `ace.cmd` 此后会把它一起装上。不装才是 bug：文档说"模型调用需要 requests"而启动器不装它，等于把失败留给用户 |

**`REQUIRED` 的连带效应（已处理）**：`REQUIRED` 同时喂给三处 —— pip 安装清单、`probe()` 的
"这个环境可用吗"判据、`--vendor` 的下载清单。所以加了 `requests` 之后，**离线那条路变成全有或全无**：
`setup_env.py` 装完本地 wheel 会真的 `import` 一遍 `REQUIRED` 的每一项，缺一项就整段退回在线安装 ——
只备了 `prompt_toolkit` 的时代过去了。为此把 `vendor/README.md` 的离线段落改成用
`python setup_env.py --vendor`（它按 `REQUIRED` 下全套），并写明必须连 `requests` 的传递依赖
（urllib3 / certifi / idna / charset-normalizer）一起备齐。**本机的 `vendor/*.whl` 是旧的
（没有 requests），没有替你重下** —— 那是一次联网写入，留给你决定；`--vendor` 一条命令即可补齐。
（`vendor/*.whl` 本就不进 git，新克隆只有那份说明。）

### 17.4 口径修正（活跃文档全覆盖）

| 文件 | 原口径 → 现口径 |
|---|---|
| `README.md` | 徽章 `core deps-zero` → **双徽章** `safety core-zero--dep` + `model API-requires requests`；"pure-stdlib core" → "pure-stdlib **safety core**（执行层 · 网关 · 记忆 · CLI）… Model calls need `requests`"；打包表同步 |
| `README.zh-CN.md` | 同上（两个徽章都换 —— 中英不许只有一个是对的） |
| `docs/ADR.md` ADR-004 | 标题"核心"→"**安全核心**"；补上**被否决的选项 (a) 与实测理由**、以及口径修正记录 |
| `docs/ADR-002-executor-boundary.md` | 41/58 两处的"零第三方依赖"限定为"**安全边界**"，并注明模型调用依赖 `requests` |
| `docs/INTERFACES.md` §8 | `urlopen_json_with_retry` → `request_with_retry`。**原文与同节第 128 行"唯一 `ace_http.request_with_retry` 调用点"自相矛盾**，现在一致 |
| `docs/ARCHITECTURE.md` | 树的 `requirements.txt` 注释："可选增强依赖清单（核心零依赖）" → "安全核心零依赖，模型调用需 requests" |
| `docs/PACKAGING-EXE.md` | 冻结包能力表"纯 stdlib 核心" → "纯 stdlib 安全核心（`requests` 也在包内）" |
| `docs/TESTING.md` | `requests`"（可选增强）" → "（**必需**，不是可选增强）" |
| `CONTRIBUTING.md` | 原文**已经如实**（第 10 行单列"真实模型对话需要 `requests`"）—— 这正说明文档层内部早有分歧；只把第 9 行的"核心"收紧成"**安全核心**" |
| `docs/COMMANDS.md` | `--install-ui` 说明补上"装 `requests`（模型调用必需）" |
| `vendor/README.md` | 依赖分"必需 / 可选"两栏；`setup_env.py --ensure` 的注释不再只写 prompt_toolkit |
| `core/ace_client.py` 模块 docstring | 设计取态第 4 条重写：**模块级零依赖 ≠ 调用零依赖** |

**不动的（按仓库纪律，历史记录不重写）**：`CHANGELOG.md`、`docs/RELEASE-NOTES-*.md`、`docs/history/**`、`.github/RELEASE-ANNOUNCEMENT-v3.41.0.md`。

**仍然是真话的（特意没改）**：`benchmarks/`、`cli/ace_doctor.py`、`ui/*`、`tui/*`、`tools/docker_sandbox.py`、`packaging/make_icon.py`、`test_all.py` 自身，以及执行层 / 网关 / 记忆 —— 这些确实零第三方依赖。所以"**安全核心**零依赖"不是空话；原来那句话的问题只是把模型客户端也算进了"核心"。

### 17.5 防漂回守卫（净 +4 条）

| 段 | 断言 |
|---|---|
| `[21]` | ★无 requests 的 stdlib 出网路径已删除 · ★唯一出网实现仍是 `request_with_retry` · ★`ace_client` 里无调用点的 requests 探针已删除 |
| `[70]` | ★`requirements.txt` 把 requests 列为必需 · ★`setup_env.REQUIRED` 含 requests · ★两个 README 都不再挂 `core deps-zero` · ★两个 README 都有如实的双徽章 |

删 3 条（urllib 用例）+ 加 7 条 = 净 +4。

### 17.6 验收

| 项目 | 结果 |
|---|---|
| 全量测试 | **2245 / 2245 全绿 · 退出码 0** |
| 上一轮 | 2241 / 2241 |
| `ruff`（CI 口径） | **All checks passed** —— 且它真的起了作用：删函数后靠 `F401` 抓出 4 个变成未用的导入 |
| 7 条 H-22 守卫 | 全部 ✅；另做了一次独立复核，确认谓词确实在量该量的东西（`requirements.txt` 未注释行、`REQUIRED` 元组、两个 README 的徽章字符串与 BOM） |
| `.ace_sessions` | 262 → 262（H-26 未回退） |
| 行为改动 | **只有一处**：`setup_env.REQUIRED` 多了 `requests`（启动器多装一个包） |

