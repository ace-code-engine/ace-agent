<p align="center">
  <a href="https://github.com/ace-code-engine/ace-agent/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/ace-code-engine/ace-agent/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Safety core dependencies" src="https://img.shields.io/badge/safety%20core-zero--dep-orange">
  <img alt="Model API" src="https://img.shields.io/badge/model%20API-requires%20requests-blue">
  <a href="CHANGELOG.md"><img alt="Latest" src="https://img.shields.io/badge/latest-v3.42.0%20(2026--09--26)-brightgreen"></a>
</p>

<h1 align="center">ACE · AI Code Engine</h1>

<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">中文</a> · <a href="CHANGELOG.md">更新日志 · Changelog</a></p>

<p align="center">
  <strong>An AI coding agent that pushes safety <em>below</em> the model — into the execution layer.<br>
  The model proposes; permissions, isolation, snapshots and rollback are decided by code it cannot talk its way past.</strong>
</p>

### At a glance

| Property | What you get |
|---|---|
| **Local** | pure-stdlib **safety core** (execution layer · gateway · memory · CLI). Runs on your machine, no cloud in the loop, and the offline demo needs no API key. |
| **Model-agnostic** | **9 vendors · 10 endpoints** behind one `/provider` switch — Zhipu, DeepSeek, Moonshot, OpenAI, Anthropic, Qwen, SiliconFlow, OpenRouter, Ollama — over both the OpenAI **and** Anthropic wire formats. |
| **Pluggable** | every tool is declared once in `tools/registry.py`; **MCP servers** connect over stdio so their tools appear as `mcp__<server>__<tool>` with permission, approval and audit unchanged; skills are plain `SKILL.md` files. |

> Model calls need `requests`; the safety core does not. An MCP server runs outside ACE's sandbox.

---

## Why ACE?

### Safety that does not live in the prompt

Most agents put safety in the prompt: *"please don't delete files"*. ACE does not.

Every tool call passes through a **separate execution layer** that makes the permission decision, detects dangerous behaviour, and takes a physical snapshot before any write. When the prompt fails — jailbreak, injected web page, tampered tool output — that layer is still there.

> If you only want chat-style code help, you probably do not need ACE. If your agent really edits files, runs commands and reaches the network, and you do not want that to depend on the model's self-restraint, this is the target case.

### ACE vs. the usual prompt-guard agent

| | Typical prompt-guard agent | ACE |
|---|---|---|
| Where "am I allowed?" is decided | in the prompt | in the execution layer, per call (`execution_layer.py`) |
| After a prompt injection or jailbreak | whatever the model decides | permission gate, path boundary and sensitive-target blocks still apply |
| Running a shell command | the model just runs it | `terminal_exec` asks a human **every time** — its blacklist is bypassable, so the human *is* the boundary |
| Undoing a bad edit | hope for git | physical snapshot before every write, `/undo` to roll back |
| Data leaving the machine | whenever the model calls an API | egress gate: unknown destination ⇒ confirm; `egress_allowlist` ⇒ one-time authorization |
| Offline, no API key | usually needs a key | `python ai_code.py --mock` runs the whole loop offline |
| Isolation | prompt-level | three tiers: `off` / `job` / `docker` — if the boundary is unavailable it returns **503, never a silent fallback** |

### Design stance

- **Safety is an execution-layer property, not a prompt property.** The model never decides its own permissions.
- **Read-only by default.** Elevation is a human action (`/permission write`), not something the model can grant itself.
- **Say what the boundary can and cannot stop.** No "fully secure" claims anywhere in this repo — see [Security boundary](#security-boundary).

---

## Run it in 30 seconds

### From source, no API key

```bash
git clone https://github.com/ace-code-engine/ace-agent.git && cd ace-agent
python test_all.py         # end-to-end test suite, pure stdlib — should be all green
python ai_code.py --mock   # offline demo: the full model ↔ execution-layer loop
```

### Point it at a real model

```bash
python ai_code.py          # menu 2 runs the setup wizard, then 1 enters chat
```

- Or switch in one line inside chat: `/provider deepseek <key>`.
- On Windows the repo ships `ace.cmd` — add it to `PATH` and type `ace`.

### Prebuilt Windows build, no Python needed

Download `ace-<version>-windows-amd64.zip` from the [Releases page](https://github.com/ace-code-engine/ace-agent/releases), unzip it anywhere, and run `ace\ace.exe`. It is a self-contained bundle, so `python` is **not** required on the machine.

```powershell
# offline: prove the bundle is intact without any account or key
.\ace\ace.exe --mock

# or point it at a real model from the landing screen
.\ace\ace.exe
```

Two things to know before you run it:

- **Windows SmartScreen will warn you.** The build is not code-signed, so a fresh download shows "Windows protected your PC". Choose *More info* → *Run anyway*, or verify the zip yourself first. This is what an unsigned binary looks like, not a sign that something is wrong with it.
- **It is a folder, not a single file.** Keep `ace.exe` next to its `_internal\` directory; copying the exe out on its own will not work.

Not everything works in the frozen build, and the exe says so instead of failing quietly:

| Capability | In the prebuilt exe | Why |
|---|---|---|
| Chat, tools, files, terminal, permissions, snapshots | ✅ | pure-stdlib safety core, resources are bundled |
| `code_execute` | ❌ returns **501**, stated plainly | it runs Python via `sys.executable`, which is `ace.exe` itself when frozen. Use the source build if you need it. |
| `--install-ui` / `--setup` | ❌ meaningless | the bundle already contains its interpreter and UI deps |
| `--install-executor` | ✅ only if the bundle shipped the Go binary | otherwise it downloads it, which needs network |

The build is produced by `packaging/build_exe.ps1`, which **will not report success without smoke-testing the packaged exe** — the bundle is run through `--version`, `--preview`, a mock tool round trip and the `code_execute` 501 path before anything is published.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build_exe.ps1
```

### See it run

[Demo & screenshots](docs/SHOWCASE.md) — the landing screen, a real recorded session, the diff card, and the execution layer refusing an SSH key.

**Further reading** — 5-minute path plus the three-axis matrix (`permission` / `sandbox` / `approval_policy`) and the ten classic traps: `docs/GETTING-STARTED.md`. Hands-on scenarios: `examples/`.

---

## Core capabilities

### Execution safety

| Capability | One-line hook |
|---|---|
| Three permission levels | `readonly` / `write` / `full`. The tool list is trimmed per level, declared once in `tools/registry.py`, so the model only chooses among tools it can actually see. |
| Three sandbox tiers | `off` (in-process policy) / `job` (Windows Job Object: process tree, memory cap, restricted token) / `docker` (one-shot container, `network none`, `cap-drop ALL`). Unreachable boundary → 503, never a silent fallback. |
| Pre-write snapshots | every write takes a physical snapshot first, and `/undo` rolls back. HMAC-signed, and the snapshot directory is not writable by the agent itself. |
| Egress gate | data headed for a **model-chosen** destination is confirmed per call unless the destination is allowlisted; `egress_allowlist` means one-time authorization. |
| Security triage | security blocks (path escape, allowlist, sandbox) are counted apart from ordinary argument errors, and a run of them raises a user-facing alert — that usually means something is injecting instructions through a file or a page. |
| Go executor | dangerous tools are delegated to a separate Go process over NDJSON, with whole-tree reaping via Job Object plus a second policy check. Official prebuilt binary via `ace --install-executor`. |

### Agent

| Capability | One-line hook |
|---|---|
| Persistent goals | `goal_create`, then it re-drives round after round until done, paused, blocked or out of budget. `blocked` needs a machine code, and `/goal resume` continues after a restart. |
| Subagents | `subagent` spawn (fresh context) or fork (inherit the parent session), each with its own tool loop; the result is handed back to the parent. |
| Key-free web search | `search` with a two-engine fallback (Bing RSS → DuckDuckGo) plus `search_read` to fetch top result bodies in one step. All egress goes through SSRF checks and the allowlist. |

### Optional and experimental

- **Optional** — custom knowledge base (`kb_search` / `kb_add` / `kb_list`), session event log and restart recovery (`/audit`), Plan Mode, approval-fatigue relief, browser automation, document parsing (Word / Excel / PPT / PDF / OCR), SimHash memory, `AGENTS.md` project instructions, context compaction, network backoff, i18n (zh / en / ja).
- **Experimental** — the built-in chat scroll engine. Implemented, real-terminal wiring pending; see `docs/history/UI-CHAT-SCROLL.md`.

---

## Architecture

One line per layer: `ai_code.py` (terminal: landing, REPL, slash commands) → `agent_runner.py` (the model ↔ execution-layer loop, up to 20 rounds) → **`execution_layer.py`** (parse → permission ruling → safety gates → pre-write snapshot → execute; a 14-stage state machine and **the only place safety is actually enforced**) → `tools/registry.py` (single-point tool declaration) → `core/` (snapshots, memory, meta-processing).

Gateway (L1 / L2 / L4 / L5) is a policy layer **called inside each round** by the execution layer — not a second, independent security pipeline.

**Diagram (Mermaid, rendered by GitHub), the per-layer table and the authoritative directory tree** → **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**.

---

## Common commands

### Getting around

Landing page: **↑/↓** to move, digits to jump, **Enter** to confirm, **Esc/q** to quit. Inside chat, `exit` returns to the landing page.

### Everyday slash commands

```bash
/provider                    # list 9 vendors · 10 endpoints (the current one ticked)
/provider zhipu              # switch to Zhipu in one command
/permission write            # elevate (read-only by default)
/undo                        # roll back to the pre-write snapshot
```

- **Slash commands** — `/help` `/clear` `/status` `/snapshots` `/rollback <id>` `/model <name>` `/mock` `/open <path>` `/edit <path>` `/search <term>` `/memory` `/report` `/expand` `/history [keyword]`
- **`@` shortcuts** — `@lang` (zh/en/ja) · `@skill` · `@file` · `@folder` · `@refs`
- The `/` menu and `/help` group commands into Session / Security / Model / Tools.

### Input and output

- **Input** — `Enter` sends, `Alt+Enter` or `Ctrl+J` inserts a newline, `Ctrl+R` walks history backwards, and `/history dsk` fuzzy-finds it.
- **Long tool output** is folded into the card; `/expand` reprints the full output, up to 4000 characters per call, and says so when truncated.
- **Write-tool cards** show a colourised diff and an `exit N` code; ↑/↓ and `Ctrl+R` search `~/.ace_history` across sessions (`ACE_NO_HISTORY=1` keeps history in-process only).

**Further reading** — full command table, every `/provider` example and all startup flags: `docs/COMMANDS.md`.

---

## Security boundary

### Four layers, enabled to different degrees

| Layer | What ACE does |
|---|---|
| Prompt | guides the model only — **promises nothing** |
| Application (default) | execution-layer policy: three permission levels, AST behaviour checks, pre-write snapshot and rollback, path boundaries, SSRF and allowlist egress checks, and egress-destination confirmation (including "overwrite or delete something outside the project" ⇒ ask) |
| OS (optional, Windows) | `--sandbox job`: Job Object process and memory caps plus a restricted token |
| Container (optional) | `--sandbox docker`: one-shot container, `network none`, `cap-drop ALL`, `read-only` root, `--init`, only the workspace mounted |

The sandbox image is built once locally from `docker/Dockerfile.sandbox`; a registry-hosted image can be pulled with `ACE_SANDBOX_PULL=1`.

### Honest limits

**Without the OS or container tier**, everything above is in-process policy — the AST blacklist and AST evaluation cannot be closed, and `terminal_exec`'s verdict layer is only a tourniquet. That is **not OS-level isolation**.

The `job` tier is a Windows-only primitive. Docker containers share the kernel, so an escape is still an escape. When a boundary is unavailable, `job` and `docker` return 503 and **never silently fall back to the host**.

### Scope of the egress gate

The gate governs **model-chosen destinations**. Built-in endpoints — search engines, the image service — are not confirmed per call, and `image_generate` sends its prompt to a third-party service in clear text.

`terminal_exec` can still delete the audit log inside the project, but that step is confirmed by a human every time. Both facts are written down rather than hidden.

**Further reading** — full security model and production notes: `docs/SECURITY-MODEL.md`. Vulnerability reports: `SECURITY.md`.

---

## Configuration

### The config file

```python
# ~/.ai_code.json  (CLI flags > this file > ~/.claude/settings.json > environment)
config = {
    "permission": "readonly",   # readonly / write / full
    "sandbox": "off",           # off / job / docker
    "max_snapshots": 20,        # hard cap, oldest pruned automatically
}
```

**Further reading** — every key, plus the mechanisms behind egress allowlists, search boundaries, `str_replace` encoding and read-only `db_query`: `docs/CONFIGURATION.md`.

---

## Testing

### Run the suite

```bash
python test_all.py                      # full suite (pure stdlib, non-zero exit = failure)
python test_all.py --only 40            # run one section (declared dependencies are pulled in)
python test_all.py --list               # list sections and their dependencies
ruff check . --select E9,F63,F7,F82     # the hard-error subset CI uses
```

### Promise guards

Three sections exist purely to keep **promises** honest: `[38]` the authoritative directory tree ↔ real files, `[39]` documented numbers ↔ `PROVIDERS` / `TOOL_SPECS`, and `[40]` the raw payloads from the security audit.

They exist because "the docs say it asks the human" once turned out to mean "the code never asked".

### Done and still unverified

Both halves are here on purpose: the README used to say "not done" about things that are now finished, and a stale admission is its own kind of lie. **Read the second half as the actual warning** — do not read it as "probably fine".

**Recently closed** (recorded so the older text does not linger):

- **R-03 engine merge: done.** `core/ace_client.py` is the single model HTTP client — one `ace_http` egress point, one place that builds `/chat/completions`; the two frontends keep only their own contract.
    - Credential-free half: `python e2e/r03_contract_smoke.py` stands up a real listening socket, answers both wire formats and drives both frontends through it.
    - Vendor half: `python e2e/real_model_smoke.py` with `ACE_E2E_*` set, run green against DeepSeek — exit 0, the single `🤖 Agent:` line contract held, and the model called `datetime_now` before answering from the real result.
- **REL-03 native smoke: walked through on Windows.** `ace.cmd` → interpreter self-resolution → a real console conversation, offline `--mock`, exit 0, Chinese and emoji both intact. `e2e/rel03_native_smoke.ps1` reproduces it in three scenarios.
- **Found by that smoke and fixed:** `_generate_text` (the no-`--tools` fallback) used to hand the model's plain text straight to the execution layer, which expects protocol text — so `agent_runner.py --base-url …` never reached a final reply. It is now wrapped like `_generate_tools`, with assertions in `[8]`.

**Still unverified:**

- The **Textual full-screen UI under a real TTY** (those sections skip without `textual` installed), and any **non-Windows console**.
- The **darwin/amd64 executor artifact has no native smoke test** — it cross-compiles, but no Intel Mac has ever run it.

**Further reading** — framework, CI matrix, benchmarks and e2e details: `docs/TESTING.md`.

---

## Documentation

### Docs map

| What you want | Where to go |
|---|---|
| **Start here** — 5-minute path, three-axis matrix, ten traps | `docs/GETTING-STARTED.md` |
| **Demo and screenshots** | `docs/SHOWCASE.md` |
| **Hands-on scenarios** — security lab / document parsing / multi-turn agent | `examples/` |
| Layers, full directory tree, ADR index | `docs/ARCHITECTURE.md` |
| Security model / audit / reporting | `docs/SECURITY-MODEL.md` · `docs/SECURITY-AUDIT.md` · `SECURITY.md` |
| Every configuration key | `docs/CONFIGURATION.md` |
| Commands and startup flags | `docs/COMMANDS.md` |
| Tests and CI | `docs/TESTING.md` |
| Packaging and the Windows build | `docs/PACKAGING-EXE.md` · `docs/PACKAGING.md` |
| Development / contracts / backlog | `docs/DEVELOPMENT.md` · `docs/INTERFACES.md` · `docs/BACKLOG.md` |
| Version history | `CHANGELOG.md` |
| Design cards / session notes / research | `docs/design/` · `docs/history/` |

### Contributing

Read `CONTRIBUTING.md` first. The standard workflow lives in `docs/DEVELOPMENT.md`, interface contracts in `docs/INTERFACES.md`, and the backlog in `docs/BACKLOG.md`.

### License

[MIT](LICENSE) © 2026 jincheng3870682453-hash

### Design references

Architecture decisions align with the following work — **let the model only "understand, choose, output", and push permissions, safety, rollback and memory down into the execution layer**:

- [Agent Harness engineering best practices](https://github.com/Delphoa/study-awesome-harness-engineering) — tools / permissions / memory / sandbox / observability
- [DeepSeek Harness design analysis](https://developer.aliyun.com/article/1756780) — internal research in `docs/history/dsh_research.md`
- [20-chapter Chinese AI agent architecture course](https://github.com/ryzqi/learn-agent)
