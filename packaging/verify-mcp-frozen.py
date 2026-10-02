#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""verify-mcp-frozen.py -- smoke gate for the self-contained HooH MCP executable.

WHY THIS EXISTS
    A frozen build fails in ways a source run never shows: a resource that was
    never bundled, a hidden import that only resolves at runtime, code that
    assumes sys.executable is an interpreter. The repo already holds this line
    for the terminal build (packaging/build_exe.ps1 refuses to pass without
    running the packaged ace.exe). The MCP executable gets the same treatment:
    shipping an exe nobody ran is how you find out from users.

WHAT IT ACTUALLY DOES
    Speaks just enough of the Model Context Protocol over stdio to prove the
    three things a host depends on:
      1. `initialize` gets a well-formed reply      -> the server boots
      2. `tools/list` returns the full tool set     -> the registry got bundled
      3. `tools/call` on a real tool returns content -> the engine actually runs

    It is deliberately NOT a mock: the tool call reads a real file through the
    real execution layer. A build that boots but lost `tools/registry.py`, or
    lost `locales/`, fails here.

USAGE
    python verify-mcp-frozen.py <path-to-executable> [--project-root DIR]
    exit 0 = verified; 1 = failed (reason on stderr)

ASCII-only on purpose: this file runs on Windows CI too, and the repo has been
burned by encoding assumptions more than once (CHANGELOG v3.40.2 / REL-03).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading


def read_line(proc, timeout_s):
    """Read one line from a pipe with a deadline (a hung server must FAIL, not hang CI)."""
    box = {}

    def rd():
        try:
            box["line"] = proc.stdout.readline()
        except Exception as exc:  # pragma: no cover - defensive
            box["err"] = repr(exc)

    t = threading.Thread(target=rd, daemon=True)
    t.start()
    t.join(timeout_s)
    return box.get("line")


def send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", help="path to the hooh-mcp executable")
    ap.add_argument("--project-root", default=None,
                    help="workspace to expose (default: a temp dir with a probe file)")
    ap.add_argument("--timeout", type=int, default=40)
    args = ap.parse_args()

    exe = os.path.abspath(args.exe)
    if not os.path.isfile(exe):
        return fail("not a file: " + exe)
    if os.name != "nt" and not os.access(exe, os.X_OK):
        return fail("not executable (chmod +x missing?): " + exe)

    tmp = None
    root = args.project_root
    if root is None:
        tmp = tempfile.TemporaryDirectory(prefix="hooh_mcp_verify_")
        root = tmp.name
        with open(os.path.join(root, "probe.txt"), "w", encoding="utf-8") as fh:
            fh.write("hooh-mcp frozen probe\n")

    proc = subprocess.Popen(
        [exe, "--project-root", root, "--permission", "readonly"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1)

    try:
        # 1. initialize
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "verify-mcp-frozen",
                                              "version": "1"}}})
        line = read_line(proc, args.timeout)
        if not line:
            return fail("no reply to initialize (server did not boot)")
        try:
            msg = json.loads(line)
        except Exception:
            return fail("initialize reply is not JSON: " + line[:200])
        if msg.get("id") != 1 or "result" not in msg:
            return fail("initialize reply is not a success result: " + line[:200])
        info = msg["result"].get("serverInfo", {})
        if not info.get("name"):
            return fail("initialize reply has no serverInfo.name")
        print("ok  initialize  serverInfo.name=%s version=%s"
              % (info.get("name"), info.get("version")))

        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized",
                    "params": {}})

        # 2. tools/list -- this is what fails when the registry was not bundled.
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        line = read_line(proc, args.timeout)
        if not line:
            return fail("no reply to tools/list")
        tool_names = []
        try:
            tool_names = [t["name"] for t in json.loads(line)["result"]["tools"]]
        except Exception as exc:
            return fail("tools/list reply unusable (%s): %s" % (exc, line[:200]))
        if len(tool_names) < 20:
            return fail("only %d tools listed -- the registry was probably not "
                        "bundled" % len(tool_names))
        print("ok  tools/list  %d tools" % len(tool_names))

        # 3. tools/call on a tool that always exists and touches the real engine.
        target = "file_read" if "file_read" in tool_names else tool_names[0]
        probe_rel = "probe.txt" if tmp is not None else None
        call_args = {"path": probe_rel} if probe_rel else {"path": "."}
        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": target, "arguments": call_args}})
        line = read_line(proc, args.timeout)
        if not line:
            return fail("no reply to tools/call " + target)
        try:
            res = json.loads(line)["result"]
        except Exception as exc:
            return fail("tools/call reply unusable (%s): %s" % (exc, line[:200]))
        if not res.get("content"):
            return fail("tools/call returned no content: " + line[:200])
        print("ok  tools/call  %s returned %d content block(s)"
              % (target, len(res["content"])))

        # The engine must not write anything but protocol messages to stdout.
        proc.stdin.close()
        leftover = proc.stdout.read()
        if leftover.strip():
            return fail("stdout had extra output after the replies (that corrupts "
                        "the protocol): " + leftover[:200])
        print("ok  stdout purity  no stray bytes on the protocol channel")
        return 0
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    sys.exit(main())
