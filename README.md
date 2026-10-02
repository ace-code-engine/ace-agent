<p align="center">
  <a href="https://github.com/ace-code-engine/hooh-agent/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/ace-code-engine/hooh-agent/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Release" src="https://img.shields.io/badge/release-v1.0.0%20Public%20Beta-brightgreen">
  <img alt="Safety core" src="https://img.shields.io/badge/safety%20core-zero--dep-orange">
  <img alt="Model API" src="https://img.shields.io/badge/model%20API-requires%20requests-blue">
  <a href="CHANGELOG.md"><img alt="Latest" src="https://img.shields.io/badge/latest-v1.0.0%20(2026--10--01)-brightgreen"></a>
</p>

<h1 align="center">HooH · 互</h1>

<p align="center">
  English · <a href="README.zh-CN.md">简体中文</a> · <a href="CHANGELOG.md">Changelog</a> · <a href="docs/README.md">Docs</a>
</p>

<p align="center">
  <strong>An execution layer that places the safety boundary below the model.<br>
  The model proposes; permission, isolation, snapshots and rollback are decided by code it cannot argue with.</strong>
</p>

---

ACE is an **execution layer for coding agents**. Every tool call — files, commands, network, MCP —
passes through a single decision point: a permission gate, a path & sensitive-target boundary, a
write-ahead snapshot, and an HMAC-chained audit record. The safety core is **pure standard library**;
the boundary holds when the prompt does not (jailbreak, injected content, tampered tool output).

> **Not** the ACE editor / ACE framework / ACE-Step / Adobe-ACE — [which "ACE" this is](docs/WHY.md).

## What makes it different

- **Safety below the model, not in the prompt.** Permissions, paths, sandbox and rollback are harness code.
- **Read-only by default.** Elevation is a human action (`/permission write`).
- **Snapshot + `/undo`** on every write, HMAC-signed, not writable by the agent.
- **Self-driven.** Persistent goals, subagents, and one command to switch among **9 vendors · 10 endpoints**.

## Get it

Four artefacts per release — alternatives, not layers:

| Form | Artefact | Choose it when |
|---|---|---|
| **① HooH as your agent** | `hooh-<ver>-windows-amd64.msi` · `.zip` | You want a terminal agent to work in |
| **② HooH as an MCP server** | `hooh-mcp-<ver>-<platform>.zip` | You already use Cline / Claude Desktop / Cursor and want the boundary without changing it. **Self-contained: no Python needed** |
| **③ MCP pack (source)** | `hooh-mcp-server-<ver>.zip` | Same as ② but you want to read/patch the source; needs Python 3.10+ |
| **④ MCP + sandbox base** | `hooh-sandbox-bundle-<ver>.zip` | You want the execution boundary too (KVM microVM) |

## Quickstart

```bash
python ai_code.py --mock    # offline demo — no key, no network
python ai_code.py           # real model (setup wizard)
```

From a checkout you can also use the launcher, which finds a usable Python for you:
`hooh.cmd --mock` (Windows) — `ace.cmd` is kept as an alias for the same entry point.

Windows without Python: grab the zip from [Releases](https://github.com/ace-code-engine/hooh-agent/releases)
and run `ace\ace.exe --mock`. Install & build: [docs/PACKAGING-EXE.md](docs/PACKAGING-EXE.md).

<p align="center">
  <img src="demo/demo.svg" alt="A recorded offline HooH session" width="820">
</p>

## Documentation

| What you want | Go here |
|---|---|
| 5-minute start · the ten traps | [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) |
| What ACE stops / does not | [docs/security/SECURITY-FAQ.md](docs/security/SECURITY-FAQ.md) |
| Layers · directory tree · ADR | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Every command & flag | [docs/COMMANDS.md](docs/COMMANDS.md) |
| Every config key | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Why ACE · vs prompt-guard agents | [docs/WHY.md](docs/WHY.md) |
| Capability checklist | [docs/CAPABILITIES.md](docs/CAPABILITIES.md) |
| Testing · CI · promise guards | [docs/TESTING.md](docs/TESTING.md) |
| Engineering debt · hand-off | [docs/HANDOFF.md](docs/HANDOFF.md) |
| Everything, indexed | [docs/README.md](docs/README.md) |

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) → [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) (standard flow,
add-a-tool, add-a-feature) → [docs/BACKLOG.md](docs/BACKLOG.md).

## Name & attribution

The name **HooH (互)** is a **tribute**, not an asset claim. 互 — *mutual* — is what this
project is shaped like: the model proposes, code decides; a snapshot is written, only then
can `/undo` mean anything. Every action gets a reciprocal, reversible answer.

The project **contains no miHoYo material**. The icon ([`assets/logo.svg`](assets/logo.svg))
is original geometry in this repo's own visual language — two interlocking strokes crossed by
one spine, the 互 glyph, drawn from scratch. Nothing is traced, copied, or extracted from any game.

> The author is a long-time miHoYo player, and the name is a nod to the Aeon of
> Equilibrium in *Honkai: Star Rail*. If miHoYo (or anyone else) considers this naming
> inappropriate, **open an issue and it will be changed** — no argument, no delay.

## License

[MIT](LICENSE) © 2026 jincheng3870682453-hash
