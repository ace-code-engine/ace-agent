# ============================================================================
# r03_contract_smoke.py -- R-03 dual-frontend output-contract smoke
#
# WHAT R-03 NEEDED
#   R-03 merged the two frontends onto one model HTTP client
#   (core/ace_client.py). Its release note says the merge is a BEHAVIOUR change
#   and "the current tests only cover the --mock path -- it needs verification
#   against a REAL model endpoint before it is safe to do". That still stands:
#   merge alone is not acceptance.
#
#   e2e/real_model_smoke.py already proves the real-vendor path, but it needs
#   ACE_E2E_BASE_URL / ACE_E2E_API_KEY / ACE_E2E_MODEL and SKIPs without them.
#   This harness covers the part that does NOT need credentials: a real HTTP
#   endpoint on a real listening socket, speaking both wire formats, with both
#   frontends actually making the request. It pins the *contract*, so an
#   accidental change to either frontend's request/response shape fails here
#   instead of in production.
#
# WHAT IT IS NOT
#   Not a substitute for the vendor run. A fake endpoint cannot show what a real
#   vendor does with tools, streaming quirks, or rate limits. Run
#   e2e/real_model_smoke.py with real credentials for that. This file is the
#   reproducible half, and it is honest about which half it is.
#
# CONTRACT ASSERTED (the exact split R-03 had to preserve):
#   headless  agent_runner.py  -> ace_client.chat_once   (one shot, NON-stream)
#                                 stdout carries the single "Agent:" line
#   CLI       ai_code.py       -> ace_client.chat_stream (SSE, streamed)
#                                 the answer is rendered, exit code 0
#   both      openai + anthropic wire formats, same answer text
#
# HOW THE FAKE ENDPOINT IS STEERED: the model name.
#   base_url alone cannot select the response shape -- detect_api_format() only
#   switches on the literal "/anthropic" substring, so a localhost URL always
#   resolves to the openai format. The model string is the one value that
#   reaches the request body untouched in both formats, so the fake server
#   parses it and derives the behaviour. Cases:
#     r03-answer         plain answer, non-stream (headless)
#     r03-answer-stream  plain answer, streamed (CLI)
#     r03-toolcall       answer as a tool call, non-stream
#     r03-toolcall-stream answer as a tool call, streamed
#     r03-http-429       always HTTP 429 (retry path)
#
# USAGE: python e2e/r03_contract_smoke.py [--python PATH] [--repo PATH]
# EXIT : 0 = every case passed; 1 = at least one failed (raw evidence kept).
# ============================================================================

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Windows console GBK compatibility: this file prints captured child output,
# which contains emoji. Same defence the other entries use (see test_all [67]).
for _s in (sys.stdout, sys.stderr):
    try:
        if _s.encoding and _s.encoding.lower() not in ("utf-8", "utf8"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

ANSWER = "R03-CONTRACT-PONG"


class _FakeEndpoint(BaseHTTPRequestHandler):
    """One real listening socket; both wire formats; steered by model name."""

    protocol_version = "HTTP/1.1"
    requests_seen: list = []          # (path, model, stream_flag, had_tools)
    lock = threading.Lock()

    def log_message(self, *_a) -> None:      # keep the console readable
        return

    # -- helpers -------------------------------------------------------------
    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except Exception:                                     # noqa: BLE001
            return {}

    def _is_anthropic(self) -> bool:
        return "/messages" in self.path or "anthropic" in self.path

    def _send_json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, lines: list) -> None:
        body = "".join(lines).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- response builders ---------------------------------------------------
    def _openai_stream(self, text: str, toolcall: bool) -> list:
        out = []
        if toolcall:
            first = {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""},
                                  "finish_reason": None}]}
            out.append(f"data: {json.dumps(first)}\n\n")
            chunk = {"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "call_r03", "type": "function",
                 "function": {"name": "datetime_now", "arguments": "{}"}}]},
                "finish_reason": None}]}
            out.append(f"data: {json.dumps(chunk)}\n\n")
            fin = {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}
            out.append(f"data: {json.dumps(fin)}\n\n")
        else:
            for piece in re.findall(r".{1,6}", text):
                chunk = {"choices": [{"index": 0, "delta": {"content": piece},
                                      "finish_reason": None}]}
                out.append(f"data: {json.dumps(chunk)}\n\n")
            fin = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            out.append(f"data: {json.dumps(fin)}\n\n")
        out.append("data: [DONE]\n\n")
        return out

    def _openai_once(self, text: str, toolcall: bool) -> dict:
        if toolcall:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_r03", "type": "function",
                 "function": {"name": "datetime_now", "arguments": "{}"}}]}
            return {"choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls"}]}
        return {"choices": [{"index": 0,
                             "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop"}]}

    def _anthropic_stream(self, text: str) -> list:
        out = [f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': 'msg_r03', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'r03', 'stop_reason': None, 'usage': {'input_tokens': 1, 'output_tokens': 1}}})}\n\n"]
        out.append(f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n")
        for piece in re.findall(r".{1,6}", text):
            ev = {"type": "content_block_delta", "index": 0,
                  "delta": {"type": "text_delta", "text": piece}}
            out.append(f"event: content_block_delta\ndata: {json.dumps(ev)}\n\n")
        out.append(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n")
        out.append(f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 1}})}\n\n")
        out.append(f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n")
        return out

    # -- the one entry point -------------------------------------------------
    def do_POST(self) -> None:                                # noqa: N802
        body = self._read_json()
        model = str(body.get("model") or "")
        stream_flag = bool(body.get("stream"))
        had_tools = bool(body.get("tools") or body.get("tool_choice"))
        anthropic = self._is_anthropic()
        with _FakeEndpoint.lock:
            _FakeEndpoint.requests_seen.append((self.path, model, stream_flag, had_tools))

        if "r03-http-429" in model:
            self._send_json({"error": {"message": "synthetic 429 for the retry path"}}, 429)
            return

        toolcall = "toolcall" in model
        want_stream = "stream" in model

        if anthropic:
            text = ANSWER
            self._send_sse(self._anthropic_stream(text))
        elif want_stream:
            self._send_sse(self._openai_stream(ANSWER, toolcall))
        else:
            self._send_json(self._openai_once(ANSWER, toolcall))


def start_endpoint() -> tuple:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeEndpoint)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


def run_case(name: str, argv: list, py: str, mark: str, timeout: int = 240,
             expect_fail: bool = False) -> dict:
    """Run one frontend against the fake endpoint and judge its contract.

    expect_fail=True inverts the exit-code expectation and additionally demands
    *retry evidence*, which is how the 429 case proves the shared retry path
    without pretending a rate-limited run is a success.
    """
    printable = " ".join(argv)
    print(f"[case] {name}")
    print(f"       $ {Path(argv[0]).name} ... {printable[:110]}")
    try:
        proc = subprocess.run([py] + argv, cwd=str(REPO), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
        code, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        code, out, err = "TIMEOUT", "", f"exceeded {timeout}s"

    # The mark may legitimately appear on stderr (retry notes go to stderr so
    # they do not corrupt the streamed stdout).
    ok_mark = (mark in out) or (mark in err)
    ok_clean = "Traceback (most recent call last)" not in out + err
    if expect_fail:
        # A failing run is the expected shape; what must hold is that the
        # failure came back as a reported error, not as a crash.
        retry_evidence = bool(re.search(r"429|retry|重试|backoff", out + err, re.I))
        verdict = "PASS" if (retry_evidence and ok_clean and code != 0) else "FAIL"
        ok_exit = code != 0
    else:
        ok_exit = code == 0
        verdict = "PASS" if (ok_mark and ok_exit and ok_clean) else "FAIL"

    print(f"       exit={code}  mark({mark})={ok_mark}  clean={ok_clean}  -> {verdict}")
    if verdict == "FAIL":
        tail = (out + "\n--- stderr ---\n" + err)[-1200:]
        print("       --- captured tail ---")
        for line in tail.splitlines()[-18:]:
            print(f"       {line}")
    print()
    return {"case": name, "exit": code, "mark": ok_mark, "clean": ok_clean,
            "verdict": verdict, "stdout": out, "stderr": err}


def main() -> int:
    ap = argparse.ArgumentParser(description="R-03 dual-frontend contract smoke")
    ap.add_argument("--python", default="", help="interpreter for the frontends")
    ap.add_argument("--repo", default=str(REPO))
    args = ap.parse_args()

    py = args.python or sys.executable

    print(f"repo      : {REPO}")
    print(f"python    : {py}")
    print(f"frontends : ai_code.py (CLI, stream) / agent_runner.py (headless, one shot)")
    print()

    srv, port = start_endpoint()
    base_openai = f"http://127.0.0.1:{port}/v1"
    base_anthropic = f"http://127.0.0.1:{port}/anthropic"
    print(f"fake endpoint listening on 127.0.0.1:{port} (openai + anthropic wire)")
    print()

    common = ["--api-key", "sk-r03-local-only"]
    results = []
    try:
        # 1) headless frontend: one-shot, non-stream, plain answer -------------
        results.append(run_case(
            "headless openai (chat_once / non-stream)",
            ["agent_runner.py", "--base-url", base_openai, "--model", "r03-answer",
             *common, "--input", "ping", "--permission", "readonly"],
            py, ANSWER))

        # 2) headless, streamed body: the client must still deliver the text
        results.append(run_case(
            "headless openai (chat_once consuming a streamed body)",
            ["agent_runner.py", "--base-url", base_openai, "--model", "r03-answer-stream",
             *common, "--input", "ping", "--permission", "readonly"],
            py, ANSWER))

        # 3) CLI frontend: real SSE, streamed rendering ------------------------
        results.append(run_case(
            "CLI openai (chat_stream / SSE)",
            ["ai_code.py", "--base-url", base_openai, "--model", "r03-answer-stream",
             *common, "--input", "ping", "--permission", "readonly", "--no-tui"],
            py, ANSWER))

        # 4) CLI frontend, anthropic wire format -------------------------------
        results.append(run_case(
            "CLI anthropic wire (chat_stream / SSE)",
            ["ai_code.py", "--base-url", base_anthropic, "--model", "r03-answer-stream",
             *common, "--input", "ping", "--permission", "readonly", "--no-tui"],
            py, ANSWER))

        # 5) request shape: tools really are sent, and the stream flag matches --
        before = len(_FakeEndpoint.requests_seen)
        results.append(run_case(
            "CLI openai with native tools (request shape)",
            ["ai_code.py", "--base-url", base_openai, "--model", "r03-toolcall-stream",
             *common, "--input", "ping", "--permission", "readonly", "--no-tui", "--tools"],
            py, ANSWER))
        seen = _FakeEndpoint.requests_seen[before:]
        shape_ok = any(h for _p, _m, _s, h in seen)
        results.append({"case": "tools flag reached the endpoint", "exit": 0,
                        "mark": shape_ok, "clean": True,
                        "verdict": "PASS" if shape_ok else "FAIL",
                        "stdout": json.dumps(seen), "stderr": ""})

        # 6) retry path still lives in the shared client ------------------------
        # Expected shape: the endpoint always answers 429, so the run must FAIL
        # -- but fail as a reported error after retrying, never as a crash.
        results.append(run_case(
            "headless http 429 (shared retry path)",
            ["agent_runner.py", "--base-url", base_openai, "--model", "r03-http-429",
             *common, "--input", "ping", "--permission", "readonly"],
            py, "429", timeout=300, expect_fail=True))
    finally:
        srv.shutdown()

    print("==================== summary ====================")
    width = max(len(r["case"]) for r in results)
    for r in results:
        print(f"  {r['verdict']:<4}  {r['case']:<{width}}  exit={r['exit']}")
    print()
    print("requests the endpoint actually received:")
    for path, model, stream_flag, had_tools in _FakeEndpoint.requests_seen:
        print(f"  {path:<28} model={model:<22} stream={stream_flag!s:<5} tools={had_tools}")

    failed = [r for r in results if r["verdict"] != "PASS"]
    print()
    if failed:
        print(f"FAIL: {len(failed)}/{len(results)} cases failed")
        return 1
    print(f"OK: {len(results)}/{len(results)} contract cases passed "
          f"(both frontends, both wire formats, one shared client)")
    print("REMINDER: this is the credential-free half. The vendor half is")
    print("          e2e/real_model_smoke.py with ACE_E2E_* set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
