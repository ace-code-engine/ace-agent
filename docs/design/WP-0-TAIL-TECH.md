# WP-0 / ACC 尾活 · 技术难点与解法（切片 C + benchmarks 校验器）

> 状态：**设计已定，代码随后落**。
> 上级：`WP-0` 卡 §2 W0-C（切片 C）· `ACC-GATES.md` §7.5 / §8.6（benchmarks 落点 ①）。

---

## 一、切片 C · 终端权限提示统一渲染 `tool`/`reason`

### 难点（先说清"现在到底哪里不对"）

- `agent_runner.ask_grant` 只拿到一行 `perm_approve_q`（`locales/zh.json:90`，**没有 `{tool}`/`{reason}`
  占位符**），于是"请求什么工具、为什么"靠**调用方**另行打印；
- 而实际有**两条终端路径，口径还不一样**：
  1. `agent_runner` 自主循环（`:830-838`）**打印了** `🔑 …工具… / 原因…` 再问；
  2. `ai_code._ask_permission`（`:3957-3976`）**不打印**，直接把 `perm_approve_q` 丢给 `ask_grant`
     —— 用户看到一条"是否授权？"却**不知道要授权什么**（工具/理由被丢在 `_ask_permission` 里）。
- 这正是 P-01"最弱分两轴"里**表达能力最弱**的那一档，且两条路径不一致 —— 同一个软件问同一件事，
  两种长相、还漏信息。

### 解法（两步，各自可独立提交）

1. **`ask_grant` 自己渲染**：签名加 `tool: str = ""` / `reason: str = ""`（可选，向后兼容）。
   有 `tool` 时，提示行改用带占位符的 `perm_approve_q`（`{tool}`/`{reason}`）；
   没有时保持现状（`ask_grant` 还被别处复用，不能一刀切）。
   i18n：`perm_approve_q` 三语各加占位符（沿用 H-33"三语齐全"的纪律）。
2. **两个调用点统一**：`ai_code._ask_permission` 把 `tool_name`/`reason` 传进去；
   `agent_runner` 循环**删掉**自己那两行 `🔑/原因` 打印，改由 `ask_grant` 渲染。
   删掉后 `agent_runner` 不再需要 `result.get('tool')`/`result.get('reason')` 那两行 ——
   这正是"同一件事别打两遍"。

### 关键风险（已排查，不是猜）

- **demo SVG 不受影响**：`demo/*.svg` 里 `🔑`/`授权`/`是否授权` **零命中** ——
  demo 的 `diff` 场景跑在 `--permission write`（写文件不放行请求），所以改 `ask_grant` 的输出
  **不会动 demo**，`[68]`/`record_demo.py --check` 不会因此红。
- **i18n 三语**：`perm_approve_q` 加占位符要在 `zh/en/ja` 三份一起改，否则 `[73]` 的机械链接红。

---

## 二、benchmarks 接校验器 · 没有真实数据时怎么接（不假装）

### 难点

- ACC-02 落点 ① 是 `benchmarks/results/`（WP-10 要"下沉前/后可复核数据"），但 **WP-10 未开工** ⇒
  没有真实 before/after token 数据可校验；
- 若"接校验器"只是写一个**没人调用的函数**，就是**假接**（ACC-04 的 `attempted → judged` 偷换）。

### 解法（诚实：合成自检 + 形状校验器，不假装真实）

1. **形状校验器** `validate_bench_report(payload)`：校验 `bench_report.json` 的结构 ——
   `sysinfo`（含 `python`/`platform`）、`checks`（含 `passed == total`）、`metrics` 非空。
   坏报告当场红。落点：`core/ace_contracts.py`（与 token 判据同处）。
2. **合成 token-accounting 自检段**：`bench_core.py` 加一节 `[token]`，用**固定的可复现 fixture**
   （一组 `estimated/measured` 在阈值内、一组**超阈值**）跑 `usage_token_verdict`，
   把判决写进报告 + 计入退出码，明确标注**「合成偏差数据，非真实会话」**。
   这一步让 ACC-01 ③ 的"标红"在基准报告里**真的被消费**（超阈值那一组 → 报告里出现 `flag`），
   而不是悬空的一个纯函数。
3. **真实数据**：WP-10 落地时把合成段换成真实 before/after —— 校验器与判决函数**不用改**，
   `[token]` 段的 fixture 换成从 `benchmarks/results/` 读真实会话。

> 一句话：**校验器的"接上" = 它被基准报告真实消费 + 报告结构可校验；真实数据是 WP-10 的输入，不是本步的前提。**

---

## 三、验证口径（两个难点共用）

- 每步**先红后绿**：先写断言看着它红，再改到绿；
- 全量四道门：`python test_all.py` / `ruff` / `demo --check` / 前端 `tsc + vitest`；
- 各按工作包单独提交。
