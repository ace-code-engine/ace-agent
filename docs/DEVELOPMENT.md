# 开发者标准化流程(改代码从哪开始,到哪算完)

> 适用:任何人(含 AI 助手)往 ace 仓库提交代码。目标:**提交前在本地完成 CI 能做的全部校验**,让 main 永远可发布。
> 配套文档:`INTERFACES.md`(接口契约)、`BACKLOG.md`(待办)、`CONTRIBUTING.md`(环境)。

## 0. 唯一真相源(Single Source of Truth)——先读这些,别改它们的“影子”

| 事实 | 唯一真相源 | 禁止另起炉灶 |
|---|---|---|
| 工具有哪些 / 权限 / schema / 示例 | `tools/registry.py` 的 `TOOL_SPECS` | ❌ 手写 function schema、权限集合、提示词工具清单 |
| 会话与格式协议 | `docs/INTERFACES.md` + `execution_layer.py` | ❌ 私自发明第二套输出格式 |
| 设计取舍 | `docs/ADR.md` | ❌ 无记录地推翻既有决策 |
| 版本事实 | `CHANGELOG.md` 首条 + README 徽章 | ❌ 双份手抄、只改一边 |

> ✅ 数字纪律(已闭环 v3.8):版本号单源 `core/version.py`(Q-12);文档口径数字由 `test_all.py [39]` 自动校验(Q-04)——凡触及数字一律写"以源码为准"或与 `PROVIDERS`/`TOOL_SPECS` 一致的实测值,不许再写死,也不许手抄断言总数。
> ✅ 提示词工具清单(已闭环 v3.8,Q-07):`prompts/` 三个运行时提示词里的工具清单必须覆盖全部暴露工具,由 test_all 的同名断言拦住漂移;提示词里"某工具尚未实现"这类可用性表述也要按现码核对。

## 1. 标准提交流程

```text
① 读: docs/BACKLOG.md 认领条目(或提 Issue) → CONTRIBUTING.md → 相关 docs/ADR
② 基线: python test_all.py(确认改动前绿/或已知环境跳过项) 
③ 实现: 遵守 INTERFACES.md 契约;小步提交,不要一个巨型 diff
④ 测试: 为新行为加断言(test_all.py 对应 [N] 段,不要只改不测)
⑤ 本地验证(全绿才推):
     python test_all.py                       # 全量,退出码非 0 即失败
     python benchmarks/bench_core.py --quick  # 基准健康;功能 check 失败即红
     ruff check . --select E9,F63,F7,F82      # 硬错误集(计划扩 F401/F841)
     python demo/record_demo.py --check       # 改了用户可见输出才需要
⑥ 文档: 动了行为/数字 → 同步 CHANGELOG(新增条目)、README(如涉及)、docstring
⑦ 提交: 信息 = 中文一句主题(前缀 feat/fix/docs/style/refactor)+ 要点列表(参考 git log)
⑧ 推送: push → GitHub Actions 核对 8 个 job 全绿(Python 3.10/3.11/3.12、Go×2、ruff、bench、e2e)
```

分支命名 `feat/xxx` / `fix/xxx`;改行为时把断言旧行为的用例一起改,不许只加新用例。

## 2. 新增一个工具:八步清单(唯一入口 = registry)

1. 在 `tools/registry.py` 的 `TOOL_SPECS` 加一条 `ToolSpec`(字段契约见 INTERFACES §7)。
2. 决定 `permission`:只读 `PERM_READ` / 写 `PERM_WRITE` / 高危 `PERM_HIGH_RISK`;
   会写盘、会出网、会截图、会执行的一律**不许只读**。
3. 实现 handler:`tools/<域>_tools.py` 里 `ToolExecutor` 的方法;
   普通签名 `(params)`;需要工具名时 `pass_tool_name=True` 用 `(tool_name, params)`。
4. 需要人确认才安全的设 `confirm=True`(如执行任意命令)。**默认不要设**。
5. 读/检索类工具:必须过与 `file_read` 同口径的路径 confinement + 敏感目标判定
   (当前 `parse_document` 越界是已知 P0 缺陷 SEC-02,新增工具不许再犯)。
6. 执行代码/命令的工具:不许只靠 AST 精确名拦截(见 P0 SEC-01),必须叠
   Go 执行器/job/docker 边界或引用级白名单。
7. 补断言(test_all 相应段):可用性 / 权限档位 / 错误语义(400 参数 / 403 权限 / 404 不存在 / 409 歧义)/
   熔断与守门;涉及出网工具补 SSRF/白名单用例。
8. 提示词工具清单与 function schema 由 registry **生成或由 CI diff 守卫**(BACKLOG Q-07 落地前,手动同步并注明)。

## 3. 代码风格与命名

- 类型注解:参数/返回值/dataclass 字段**全注解**;`from __future__ import annotations` 全仓统一(见 BACKLOG Q-10)。
- 错误策略:内部逻辑用异常;对外边界统一 `ExecutionResult`(字段见 INTERFACES §6)。
- 文案:用户可见输出经 `i18n`(`locales/*.json`)或至少不与错误语义耦合;
  **禁止用中文 message 子串当 error_code**(现状已记 BACKLOG)。
- 日志:内部诊断 `logging.getLogger("ace")`;**禁止宽 except + pass 吞掉 L5/会话日志写入失败**。
- 新模块命名 `ace_` 前缀小写下划线;`core/archive.py` / `core/nuwa.py` 等旧名不再新增同类。
- 目录归属:`ui/`(终端表现,不许做裁决)、`cli/`(操作者工具)、`core/`(引擎支撑);根级只留 `ai_code.py` / `agent_runner.py` / `execution_layer.py` / `test_all.py`。新文件放错包会被 `[38]` 结构守卫与评审同时拦下。

## 4. 安全红线(写代码时默认遵守)

- 路径:文件内容读取**一律限项目内**;绝对路径写只对“明确意图”放行;敏感目标(`~/.ssh`、`.pem/.key`、`.guardian`)任何档位都不给。
- 外发:默认按 `egress_allowlist` 判定;出站工具都要过 `safe_request`(SSRF pin-IP/逐跳)。
- 非 tty:一切授权/计划审批 fail-close。
- 快照:写工具由执行层自动快照;不得让 Agent 可写 `.guardian/`。
- 越权假设:不要假设“模型不会…”;安全以执行层与沙箱为界,不靠提示词。

## 5. 验证命令速查

```bash
python test_all.py                          # 全量测试
python test_all.py --strict                   # 把“能力不足跳过”当失败(严格复现)(≤2 分钟)
python benchmarks/bench_core.py --quick     # 基准健康
ruff check . --select E9,F63,F7,F82         # 硬错误(计划扩 F401/F841)
python -m compileall -q <改动的文件>         # 编译检查
python e2e/real_model_smoke.py              # 真实模型冒烟(需 ACE_E2E_* env,缺省跳过)
python demo/record_demo.py --check          # 演示动画一致性
```

受限环境(无 Go Job Object/禁联网/系统临时区只读)下的测试应走 SKIPPED 通道如实标注(BACKLOG Q-03),不许假绿、不许整脚本崩。

### 改了界面输出,演示图要一起重录

`demo/record_demo.py --check` 会把**重新录制的结果**与提交的 SVG 逐行比对（数字归一化成 `#` 后比骨架，
版本号另有一条断言对 `core/version.py`），所以任何进入演示剧本的输出变化（典型：`/status`、主页、
聊天卡片、版本号）都会让那几张图过期，CI 的演示一致性那一步会一直红到重录为止。**四张图都在这条闸门里**：

```bash
python demo/record_demo.py --session happy      # demo/demo.svg
python demo/record_demo.py --session blocked    # demo/demo_blocked.svg
python demo/record_demo.py --session diff       # demo/demo_diff.svg
python demo/record_demo.py --session landing    # demo/demo_landing.svg
python demo/record_demo.py --check              # 判据：四张全绿
```

**在哪台机器上录都行 —— 这一条被修过。** 本文件此前写的是"重录**必须在与 CI 同源的环境**做"，
理由是当时在开发机上重录后，失败"转移到了下一个没重录的文件"。**那个归因是错的**：真正的原因
不是"列宽补白不同源"，而是录制脚本把临时目录的绝对路径**直接换成了一个 `…`**，于是路径长度以
补白的形式留在了 SVG 里 —— 本机 work 路径 50 列、CI 69 列，`--check` 在 CI 上必然对不上；
顺带还让面板里那一行比同框其它行短掉一截，**发布出去的图里那个框本来就是缺一角的**
（实测已提交的 `demo.svg`：其余行 96 列，`目录` 那行只有 28 列）。

现在 `capture_session` 折叠路径时分两种口径（`_fold_path` 的 docstring 里有理由与实测数字）：
**框内行保宽**（否则框缺角）、**自由行折成一列**（否则行宽仍随路径长度变）。于是录制结果与
"在哪录"无关 —— 实测把临时目录加长 17 列，四套剧本录出的骨架逐字节一致；`test_all [61]`
有一条断言钉住这个不变量。**所以本机重录是安全的，不必再去找同源的机器。**
