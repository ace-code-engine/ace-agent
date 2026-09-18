# 测试（Testing）

> 本文档由 README「开发与测试」节拆分而来（docs/design/README-RESTRUCTURE.md，v3.7），集中测试、CI、基准与冒烟细节。README 只留"怎么跑"两行。

## 1. 怎么跑

```bash
python test_all.py                          # 全量测试，退出码非 0 即失败
python test_all.py --strict                 # 把"能力不足跳过"当失败（CI / 严格复现）
ruff check . --select E9,F63,F7,F82,F401,F841,E711,F811   # CI 同款；F401/F841 用 ruff --fix
python -m compileall -q <改动的模块>          # 编译检查
python benchmarks/bench_core.py             # 实测基准 → benchmarks/results/bench_report.md
python benchmarks/bench_core.py --quick     # 样本减半的基准健康门（CI 用）
python e2e/real_model_smoke.py              # 真实模型端到端（需 ACE_E2E_* env，缺省自动跳过）
python ace_doctor.py                        # 环境自检（Python/依赖/Go 执行器/Docker/配置）
python demo/record_demo.py [--check]        # 重录 / 校验 README 顶部演示动画
```

## 2. 测试框架与断言

- **单文件、纯 stdlib、无框架**的端到端断言：`check(名称, 条件, 详情)` 逐条打印，任何一条失败即退出码非 0。
- **用例总数随平台浮动**（Windows 上比 Linux 多十余项，差额是 Windows 专有的路径/编码用例）——看退出码与失败列表，不写死数字。
- **临时目录统一落 `.test_tmp/`**（gitignore），避免受限环境系统临时区只读导致整脚本崩溃。
- **受限环境 SKIPPED 通道**：无 requests / 无 Go Job Object / 无联网时相关用例优雅跳过并如实标注（`⏭` 计数），不许假绿、不许整脚本 traceback；`--strict` 把跳过当失败。
- 改了行为就把断言旧行为的用例一起改掉——不要只加新用例。
- **`[38]`/`[39]`/`[40]` 三条"文档与安全承诺"守卫**（Q-06 / Q-04 / 审计对账）：
  - `[38]` **结构一致性**：`docs/ARCHITECTURE.md` 权威树 ↔ `git ls-files`——R1 树中路径必须存在；R2 仓库根级条目必须登记（自身或作为前缀）；R3 已展开目录的直接子项必须全登记；R4 `ci.yml` 的 compileall 覆盖全部根级 `.py`。**加/删/改文件名要同步树与 compileall，否则变红。** 规则见 `docs/design/ARCH-TREE-CHECK.md`。
  - `[39]` **文档口径数字**：文档里"家厂商 · 入口"/"家提供商"/"个工具"必须与 `PROVIDERS` / `TOOL_SPECS` 实测一致；README/CONTRIBUTING/CHANGELOG 头部禁止出现写死的用例/断言总数。
  - `[40]` **安全审计 payload 回归**：把 `docs/SECURITY-AUDIT.md` 对账表里可自动化的原始 payload 钉成断言（SEC-003 引用级拦截 / SEC-005 open_file 只给链接 / SEC-006 内容限项目内但目录可越界 / SEC-007+018 越界路径非 allow / SEC-010 签名默认开 / SEC-014 密钥不进快照 / SEC-019 安全 403 不进熔断）；Windows 专有命令在非 Windows 上走 SKIPPED。
  - 三条都随 CI 的 `test job` 在 Python 3.10/3.11/3.12 顺带执行；`[38]` 在 git 不可用时整节跳过（`--strict` 按失败处理）。

## 3. CI 矩阵（.github/workflows/ci.yml）

| Job | 内容 |
|---|---|
| `test` | Python 3.10 / 3.11 / 3.12 × compileall + 全量 test_all（ubuntu）；Python 3.12 额外跑 `demo/record_demo.py --check`（README 首屏动画必须与当前 CLI 输出一致） |
| `go-test` | Go executor：ubuntu + windows 原生 vet / build / test；race 仅 ubuntu（Windows runner 无 C 编译器） |
| `lint` | ruff 硬错误子集 + 死导入/未用变量 |
| `bench` | `bench_core.py --quick` 健康门 + 报告摘要 |
| `e2e-real-model` | 真实模型冒烟，`ACE_E2E_*` secrets 配好才真正执行，否则自检跳过不红 |

另有 `release-executor.yml`（手动 dispatch）：交叉编译 5 平台执行器产物 + windows/ubuntu/macos-14 原生 `--version` 冒烟 + GitHub Release 发布（见 `docs/design/EXECUTOR-RELEASE.md`）。

真实模型 e2e 启用：GitHub → Settings → Secrets → Actions 配 `ACE_E2E_BASE_URL` / `ACE_E2E_API_KEY` / `ACE_E2E_MODEL` 即自动启用。

## 4. 环境提示（Windows / 可选依赖）

- 控制台 GBK 已做 UTF-8 兜底，但建议全局设 `PYTHONUTF8=1`。
- 文档解析增强依赖（python-docx / openpyxl / pdfplumber / pymupdf / pytesseract）按需装，见 `requirements.txt`；旧版 Office 格式（.doc/.xls/.ppt/.wps/.et）回退依赖系统级 LibreOffice 或 antiword。
- 真实模型对话需要 `requests`（可选增强），`/` 补全需要 `prompt_toolkit`（`ace --install-ui` 一键装）。
