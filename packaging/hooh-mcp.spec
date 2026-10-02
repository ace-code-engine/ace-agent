# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec -- self-contained HooH MCP server (packaging/hooh-mcp.spec).

Builds `dist/hooh-mcp/hooh-mcp.exe` (+ the runtime next to it) from
`packaging/hooh_mcp.py`. The point of this artifact: an MCP host (Cline / Cursor /
Claude Desktop / anything speaking Model Context Protocol) can point at ONE
executable, with no Python, no pip, no venv on the target machine.

Why a second spec instead of reusing ace.spec
---------------------------------------------
ace.spec builds the terminal agent: its entry is `ai_code.py`, which parses the
full CLI surface and can open a REPL, a Textual fullscreen UI, or the landing
menu. The MCP server needs none of that, and shipping the REPL to a host that
only speaks JSON-RPC is a surface nobody asked for.

What this spec shares with ace.spec, on purpose:
  * **one-dir, not one-file.** One-file unpacks the whole bundle into a temp dir
    on every cold start; a host spawns this server per session, so that cost
    would land on every attach. One-dir unpacks once and is inspectable.
  * the same `datas` (prompts/ locales/ assets/ vendor/) -- `locales/` is NOT
    optional here: the ready-line goes through `t()`.
  * the same `hiddenimports` / `excludes` rationale. Read ace.spec for the long
    version of both; the reasoning has not changed.

Frozen-only caveats, identical to the terminal build (see docs/PACKAGING-EXE.md):
  * `code_execute` cannot work frozen (it shells out to `sys.executable`, which
    is this exe) -- it reports 501 honestly. Over MCP that surfaces as an error
    content block, not a crash.
  * `executor/` (the Go job-object helper) is bundled when present at build time.

ASCII-only on purpose: spec files are read on Windows and this repo has been
burned twice by "BOM-less UTF-8 read as ANSI" (CHANGELOG v3.40.2 / REL-03).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent

# ---- runtime data ----------------------------------------------------------
datas = [
    (str(ROOT / "prompts"), "prompts"),
    (str(ROOT / "locales"), "locales"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "vendor"), "vendor"),
]
# License/notice files travel with the artifact: this pack redistributes the
# wheels in vendor/ (MPL-2.0 certifi, Apache-2.0 requests, ...), so the
# attribution has to be in the box, not only on the website.
for _doc in ("README.md", "SECURITY.md", "LICENSE", "THIRD-PARTY-NOTICES.md"):
    if (ROOT / _doc).is_file():
        datas.append((str(ROOT / _doc), "."))
if (ROOT / "executor").is_dir():
    datas.append((str(ROOT / "executor"), "executor"))

# ---- hidden imports --------------------------------------------------------
# Same rationale as ace.spec: several modules are only reached by name at
# runtime (registry handler tables, MCP tool assembly, engine backends), so
# static analysis alone would drop them.
hiddenimports = []
for pkg in ("core", "tools", "ui", "cli", "gateway_v2"):
    if (ROOT / pkg).is_dir():
        hiddenimports += collect_submodules(pkg)

# Optional deps: present -> capability, absent -> an honest 501/503 at runtime.
for opt in ("requests", "markdown_it", "mdit_py_plugins", "linkify_it",
            "pygments", "wcwidth"):
    hiddenimports.append(opt)

# The MCP door never renders a terminal UI. `tui` (Textual) and `prompt_toolkit`
# are pulled in by `ui/` and `ai_code`, but nothing on this path instantiates
# them -- excluding them here trims the bundle and makes the "this server has no
# UI" claim structural rather than a promise.
excludes = [
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "IPython", "notebook",
    "pytest", "sphinx", "setuptools", "pip", "wheel", "distutils",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "textual", "prompt_toolkit", "playwright", "PIL",
]

a = Analysis(
    [str(ROOT / "packaging" / "hooh_mcp.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hooh-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX gets flagged by AV on Windows; not worth the size
    console=True,         # stdio transport: the console channel IS the protocol
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "ace.ico") if (ROOT / "assets" / "ace.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="hooh-mcp",
)
