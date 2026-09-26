# MCP Server 立项卡 —— 把执行层做成别人 agent 的"工具后端"

> 一句话：**ACE 不再只是"自己去干活的那个 agent"，而是任何 MCP host（Claude Code /
> Cursor / Codex / 自研）都能挂上的执行层** —— host 负责想，ACE 负责"这一下到底能不能动"。
>
> 状态：**M1–M7 已落地**（协议层 / 裁决 / 接线 / 台账 / `test_all [72]` / `e2e/mcp_probe.py` / 文档）；
> **M8 真 host 冒烟待做** —— 那一步只能由人在装了 host 的机器上点一次。本卡写明要做什么、
> 明确不做什么、以及"什么才算做完"。

## 一、为什么要做（不是"加一个协议"）

1. **它是那条一直转不起来的闭环的唯一出口。** RG-03/RG-04 的判据翻判卡在"要有真会话数据"，
   而项目按设计没有遥测：数据只能来自**有人真的拿 ACE 干活**。做成 MCP server 之后，
   别人的 agent 每天通过 ACE 落文件、跑命令 —— 归属与可逆性的数第一次有了**不是我自己造的**来源。
2. **授权令（RG-05a）在这里才第一次有了真实用户。** headless 的 MCP host 没有人可以问，
   逐次确认在那种场合等于"什么都干不了"。令（roots / 可逆性下限 / 不可逆额度 / TTL）正是为
   这种场景设计的：**一张任务一张令，弹窗从 O(步数) 收成 O(任务数)**。此前它看起来像
   "解决一个不存在的问题"，这里就是那个问题。
3. **护城河从"功能"变成"产品"。** ACE 的差异化从来不是工具本身（读文件、跑命令谁都有），
   而是**工具执行之前那一次裁决**。把裁决点摆在别人 agent 的工具链路上，才是它的自然位置。

## 二、明确不做（第一版）

| 不做 | 理由 |
|---|---|
| TCP / HTTP / SSE transport | stdio 已经给出"进程生死绑定 + 无需认证 + 无需端口"，与 `core/ace_serve.py`、`docs/ADR-002-executor-boundary.md` 同一套论证。多一个 transport 就多一套认证与回收 |
| MCP `resources` / `prompts` 能力 | ACE 的价值在**执行**。列资源、发提示词是 host 的事，做了只是把两边的活都干一半 |
| `elicitation`（服务端反向问用户） | 第一版靠"默认拒绝 + 令放行"就够了，且**不需要**假定 host 支持它。等真 host 冒烟后按需求加（反向请求 = 嵌套读帧，`ace_serve` 那套手法可复用） |
| 自己实现模型调用 | MCP 模式下 **ACE 不调模型**：一次 `tools/call` = 一次工具执行（`run_tool_direct`），host 的 agent 才是"想"的那一方。这条把成本与延迟都留在 host 侧，也让 ACE 的行为可预测 |
| 引入 MCP 官方 SDK | 协议形体仓库里已有一侧（`core/ace_mcp.py` 客户端），服务端是它的镜像；依赖纪律（离线 wheel）也不欢迎新包 |
| 暴露控制类工具 | 见下面的暴露面 |

## 三、暴露面（白名单，不是黑名单）

`tools/list` **只发白名单里的工具**。白名单写在 `core/ace_mcp_server.py` 里，代码里就是那张表：

- **发**：`file_read` / `file_write` / `file_delete` / `file_move` / `str_replace` / `edit_file` /
  `grep` / `glob` / `terminal_view` / `terminal_exec` / `code_execute` / `api_get` / `api_post` /
  `db_query` / `db_write` / `browser_open` / `browser_navigate` / `browser_click` / `browser_type` /
  `search` / `search_read` / `kb_search` / `kb_add` / `kb_list` / `skill_list` / `skill_load` /
  `parse_document` / `math_calc` / `datetime_now` / `notify_send`
- **不发**（各自有理由，写进代码注释）：
  - `request_permission` / `plan_propose` —— 它们是 ACE 自己那套**对话循环的控制面**，
    对 host 没有意义（host 没有 ACE 的授权往返可答）；
  - `subagent` / `goal_*` / `todo_write` —— host 自己有子代理与待办；经 ACE 再起一层
    等于把成本、并发与"谁的账"都搅在一起；
  - `image_generate` —— 会产生外部费用，且与"能不能动这个文件"这条主线无关。

**白名单而不是黑名单**的理由与仓库其它地方一致：将来注册表里新增工具，默认是**不暴露**，
要暴露得有人显式加一行 —— 而不是某天悄悄多出一个外部 agent 能调的工具。

## 四、审批矩阵（不发明新政策）

裁决点仍然只有一个：`execution_layer`。MCP 只做**翻译**，把它的四种结果翻成 MCP 的应答：

| 执行层结果 | 触发条件 | MCP 应答 |
|---|---|---|
| 放行 | 权限档允许、非项目外、非 CONFIRM_TOOLS | 正常 `content` |
| **令覆盖 → 静默放行** | 有令且覆盖（roots / 可逆性 / 额度都够） | 正常 `content`，事件里记 `mandate_allowed` |
| **默认拒绝** | 会问人的那几处（项目外对象 / 逐次确认 / 外发 / 权限不足） | `isError: true` + **可执行的**理由（"要写请让用户把权限档调到 write"／"这类动作需要一张覆盖它的令"） |
| 硬拒绝 | 敏感目标 / 规则 deny / 未注册 MCP 工具 / 无边界 | `isError: true`，理由同执行层原文 |

三个旋钮的分工（与 CLI 完全一致，**MCP 不新增任何一个**）：

1. **权限档**（`--permission` / 配置 `permission`）决定*哪些工具够得着* —— 默认 `readonly`。
2. **授权令**（配置 `mandate`）决定*哪些确认会收拢*。
3. **沙箱档**（`--sandbox`）决定*跑起来之后还有没有第二道边界*。

**默认拒绝不是"降级"**：headless 下没有人可问，问不到就问不到 —— 这正是执行层既有的
fail-close 口径；令是**用户事先给出的**授权，所以它不是绕过审批，而是审批的另一种形态。

## 五、与现有三个前端的关系

```
CLI 主循环 ─┐
Textual 界面 ─┼─→ AgentCLI / ExecutionLayer（唯一裁决点）─→ 工具执行 + 快照 + 台账
--serve ─────┤
--mcp ───────┘   ← 本卡新增的第四个前端
```

- 接线照抄 `--serve`（`ai_code.py::_run_mcp`）：**处理函数只做翻译**，引擎侧一行不改。
- **但一次调用接的不是 `run_tool_direct`，而是一个新入口 `ExecutionLayer.run_tool_external`。**
  这是立项过程中被实测改掉的一处设计，值得留痕：`run_tool_direct` 服务的是"**人自己敲的**命令"，
  它**刻意跳过整个 `_stage_permission`**（逐次确认闸门 / 项目外已存在对象 / 外发 / 持久规则 /
  授权令都在那一阶段）。接它的第一个版本，`e2e/mcp_probe.py` 当场拍到 write 档下
  `terminal_exec` **直接执行**（`echo hi` → returncode 0）、项目外**已存在**的文件也能改
  —— 全都不问人。对人自己敲的命令这是对的（人用"亲手敲"表达了意图）；对"另一个 agent
  说的一句话"，那等于**把第三方指令提升成用户命令**。新入口把裁决补回来；
  `run_tool_direct` 的行为一个字没动（CLI 的 `!命令` 与 `/review` 回填继续走它）。
  `test_all [72]` 有一条**对照断言**钉住这个差别：同一个调用走 `run_tool_direct` 不问人
  —— 谁把接线改回去，那条会红。
- 仍**不**包含模型回路专属的几段：控制工具熔断 / 诱饵校验 / L4 输出守门 / 给模型的错误话术
  —— 它们管的是"模型会不会被自己骗"，不是"这一下能不能动"。工具载荷本身的 L4/L5 检查照跑
  （在执行器里）。
- MCP 的帧必须是 JSON-RPC 2.0（`{"jsonrpc":"2.0",...}`），而 `ace_serve` 的帧是刻意不引
  JSON-RPC 的 `{"v":1,"type":"req",...}`。两者共用的是**引擎与体检手法**，不是传输层。

## 六、台账与测量（这条是"顺带把洞补上"）

- 每次 `tools/call` 落一条事件，`source="mcp"`，并写进会话日志的 MAC 链（RG-02）。
- **归属**（RG-03）：MCP 调用记成**非用户来源** —— 没有人对这句话负责，host 的指令不是
  用户的原话。这正是 G1 想量的那一类："外部 agent 要求动一个用户从没提过的路径"。
- **可逆性**（RG-04）：与 CLI 同一套分类，同一个测量口径 —— 于是 `/status` 那行会开始
  出现**别人产生的**数。
- **令的使用**（RG-05a）：`record_use()` 记额度消耗；令被拒/过期同样记事件，不做静默。

## 七、什么才算做完（验收）

**协议层（我能自证）**：对着**脚本 host** 走全路径 —— `initialize` 握手（含 protocolVersion
不匹配）、`notifications/initialized`、`tools/list`（每条的 `inputSchema` 是合法 JSON Schema）、
`tools/call` 正常路径（临时项目里真的落一个文件）、`isError` 语义（工具失败走 `content`+`isError`
而不是 JSON-RPC error）、未知工具 / 坏参数 / 超大行 / EOF 各有明确应答、未握手就发业务请求被拒。
固化为 `test_all` 新段 + `e2e/mcp_probe.py`（可当脚本 host 用，也可当排障工具）。

**真实性（只有你能给）**：**在某台机器上，某个真实 MCP host 通过 ACE 写了一个文件**，
并且能在 `/audit stats` 里看到这条事件、在 `ace doctor` 里看到锚是好的。这一条没做到，
就不算"有人用过" —— 本卡不把"协议测试全绿"当成它。

**真 host 冒烟清单**（三种 host 任选其一，配置片段见 `docs/MCP-SERVER.md`）：

1. 装好 host，把 ACE 写进它的 MCP 配置（`command` + `args` + `env`）；
2. host 里让它"读一下 README 的第一行"（只读，不需要令）；
3. 让它"把某文件改一行"（需要 `--permission write` 或写配置；**先不配令**，
   预期：被拒，且理由里写明"需要令或提权"）；
4. 签一张令（`python -m cli.ace_mandate issue ...`）填进配置，重来第 3 步，预期：成功；
5. `python -m ace_audit`（或 `/audit stats`）确认事件与令的使用都在。

## 八、里程碑

| # | 内容 | 完成判据 |
|---|---|---|
| M1 | `core/ace_mcp_server.py`：JSON-RPC 帧 + `initialize` / `tools/list` / `tools/call` / `ping` | 脚本 host 能拿到工具清单 |
| M2 | 审批翻译：`PERMISSION_REQUEST` → `isError` + 可执行理由；令覆盖 → 放行 | 无令被拒 / 有令放行，两条都有断言 |
| M3 | `ace --mcp` 接线（项目根 / 权限档 / 无边界即拒） | 真进程起得来、EOF 干净退出 |
| M4 | 台账接线（`source="mcp"` + 归属 + 令记账） | `/audit stats` 看得到外部来源 |
| M5 | `test_all` 新段 + `e2e/mcp_probe.py` | 全绿，且探针可独立跑 |
| M6 | `docs/MCP-SERVER.md`（三种 host 的配置片段）+ 权威树 / CHANGELOG | 文档守卫过 |
| M7 | 全量 + ruff + 演示图一致性 | 2370+ 全绿 |
| M8 | 真 host 冒烟（你点一次） | 第七节那张清单走完 |

**M1–M7 的完成证据**（都是实测，不是"应该"）：

- `test_all [72]`：**32 条**断言全绿（暴露面 4 · 协议层 13 · 行长与 id 3 · 真实裁决 5 ·
  翻译 3 · 授权令 3 · 对照差异 1）。全量 2370 → **2405**：其中 +32 是本段，
  另 +3 不是新增断言，而是 Job Object 能力探测**这次没被跳过**（上一轮宿主令牌不允许
  `PROCESS_SUSPEND_RESUME` 时它们走 SKIPPED 通道）。其中三组值得单说：
  - **真实裁决**用的是真 `ExecutionLayer`（不是假引擎）：write 档项目内真落盘、项目外
    **已存在**对象返回 `PERMISSION_REQUEST` 且文件内容一字未变、`terminal_exec` 返回
    `PERMISSION_REQUEST`、readonly 档写工具 `PERMISSION_REQUEST`。
  - **授权令的两半都验了**：没令（或令不覆盖这个路径 / 没点名这个工具）→ 照旧
    `PERMISSION_REQUEST`；**令覆盖 → 静默放行**（项目外已存在文件被真的改掉）。第二半是
    这件事的全部意义所在，而它在第一轮里是缺的 —— 只有"拒绝"被断言过。
  - **行长与 id**：MCP 把 `arguments` 整包放进一行，所以"文件内容"这种参数天然撑长行。
    第一版搬了 `ace_serve` 的 1 MiB 上限，探针实测**2 MiB 的合法写入被协议层拒**；
    而且超限时回的 `id: null` 让客户端**死等**（探针第一次跑就超时 600 s）。
    现在上限 8 MiB，超限/坏 JSON 都尽力把 id 抠回来（只看开头 4 KiB）。
- `e2e/mcp_probe.py`：起**真的** `ace --mcp` 子进程，用 stdio 说 JSON-RPC —— **39 条全过**。
  它额外证明五件单测证不了的事：**stdout 一行杂音都没有**（引擎几百处 print 全被换到
  stderr）、host 断开（EOF）子进程干净收工（退出码 0）、会话台账里留下 `source=mcp` 与
  那次"要问人"的拒绝（`confirm`）且每条带 MAC、**配置里的令真的会生效**（写一份带 `mandate`
  的 `~/.ai_code.json`，`terminal_exec` 从被拒变成放行 —— 单测是把令直接塞给构造函数，
  那条路**没经过配置读取**，键名打错照样全绿）、以及 **2 MiB 的写入真的落盘且字节数正确**。

## 九、已知风险与未验证

- **外部 agent 能落文件，这是设计意图，不是副作用** —— 但它意味着 host 的提示词注入
  = 对这台机器的一次写入请求。防线是执行层那三道（权限档 / 敏感目标 / 令的边界），
  以及"写前快照 + 台账"留下的可回滚痕迹。**没验证的是**：真实 host 的提示词注入场景下，
  这套防线在实践中的表现（协议层测试证明不了这个）。
- **一条被探针拍下来、但我们**没有**在 MCP 上另立规矩的政策**：**项目外「新建」文件不问人**
  （只有"项目外**覆盖已存在**"才问）—— 这是 ACE 既有政策，CLI 与模型路径同口径
  （原话是"往桌面丢个文件要顺手"）。MCP 沿用它，`e2e/mcp_probe.py` 里那条断言就是钉住
  这个事实。**如果 MCP 场景下要更严（外部 agent 不得在项目外新建），那是一条独立决定**：
  改它会同时改掉 CLI 与模型路径的行为，不该顺手做。
- 未验证：Windows 与 Linux 上 stdio 的编码/换行差异（第一版显式强制 UTF-8 与 `\n` 分帧，
  但只有 Windows 本机跑过）；真实 host 对 `inputSchema` 的挑剔程度（有的 host 校验更严）；
  `elicitation`（服务端反向问用户）没做 —— 第一版靠"默认拒绝 + 令放行"，不假定 host 支持它。

## 十、是否并入 v3.44.0：评估（2026-09-26）

**做完了什么**：代码 / 回归（`test_all [72]` 32 条 + 探针 39 条）/ 文档 / 权威树登记全部落地，
全量 2402 / 2402、ruff 零命中、CI 在 3.10/3.11/3.12 × Linux + Windows 上 **10/10 绿**
（`41e0749`、`a28abfa`）。**没做完的是 M8**：一次真 host 冒烟（那只能由人在装了 host 的机器上做）。

**两条路，我的建议是第二条**：

| 选项 | 意味着 | 代价 / 风险 |
|---|---|---|
| A. 现在发 3.44.0 | Release 会把 `ace --mcp` 当作新能力介绍出去，而它**没在任何真 host 上跑过** | 与 3.43.0 的取态不冲突（那一版也写了"已知未验证"），但发布说明得写明这一条；用户第一次试的时候，任何 host 侧的配置差异都会算在 ACE 头上 |
| **B. 先冒烟，再发（建议）** | 五步清单（`docs/MCP-SERVER.md` 第五节）走完，把"某台机器上某个真 host 通过 ACE 写了一个文件"作为发布说明里的**实测句** | 多等一次人工；但这一版的主题正是"ACE 开始被别人用"，用一次真实使用作为发布依据最贴题 |

**发布要做的四件事（我可以在你点完冒烟后一次做完）**：
1. `core/version.py` → 3.44.0 + 两份 README 徽章（守卫 `[68]` 会盯着三者一致）；
2. **重录四张演示图**（图里印着版本号，不重录 `[68]` 当场红 —— 这正是上一版 CI 红的那一处）；
3. `CHANGELOG.md` v3.44.0 段 + `docs/RELEASE-NOTES-v3.44.0.md` + `.github/RELEASE-ANNOUNCEMENT-v3.44.0.md`；
4. tag `v3.44.0` → 派发 `release-executor` / `release-exe`（两次手动派发，见 `REL-08`）。

**我不打算自己决定的事**：写不写、什么时候写"某个真 host 验证过"。那句话得由**真跑过的人**
说 —— 在它发生之前，这一版就停在 main 上，不贴 tag。
