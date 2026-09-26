#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xcheck —— Rust 引擎 ↔ Python `core/archive.py` 对拍 + 基准（纯 stdlib）。

两件事，都是"事实"而不是"感觉"：

1. **兼容性**：引擎必须逐位复现 Python 的 SimHash / 分词 / 主题相似度 / 召回顺序。
   任何一条不一致 → 非零退出（可以当 CI 守卫用，风格同 `test_all` 的承诺守卫）。
2. **加速比**：在**真实**的 `.agent_memory.json` 上比 `MemoryArchive.get_memory`
   与引擎 `recall` 的每次调用耗时（引擎侧含一次 IPC 往返，不挑好听的算）。

用法：
    python engine/tools/xcheck.py                 # 用默认数据与引擎路径
    python engine/tools/xcheck.py --queries 30 --repeat 200
    python engine/tools/xcheck.py --engine engine/target/release/ace-engine.exe

注意：**绝不写用户的 `.agent_memory.json`** —— 先复制到工作区临时目录再只读加载
（H-26 的教训：测试不许往用户真实状态目录里写东西）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent          # ace/engine/tools
ENGINE_DIR = HERE.parent                        # ace/engine
ACE_DIR = ENGINE_DIR.parent                     # ace
sys.path.insert(0, str(ACE_DIR))

# 终端编码防线：控制台是 cp936 时 ✅/中文会让脚本自己崩掉
# （实现在 core/ace_io.py，与 ai_code / agent_runner / test_all 同一道防线）
try:
    from core import ace_io as _ace_io
    _ace_io.harden_streams()
except Exception:  # noqa: BLE001 —— 加固失败也要能跑
    pass

from core import archive as py_archive          # noqa: E402

PROTO = 1
_results: list = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, bool(ok)))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"  —— {detail}" if detail and not ok else ""))
    return bool(ok)


class Engine:
    """极简 NDJSON 客户端：与 ADR-002 / ace_serve 同一套帧。"""

    def __init__(self, exe: str) -> None:
        self.proc = subprocess.Popen(
            [exe, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        self._id = 0
        r = self.call("initialize", {"protocol": PROTO})
        self.info = r

    def call(self, method: str, params: dict) -> dict:
        self._id += 1
        rid = str(self._id)
        frame = {"v": PROTO, "type": "req", "id": rid, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()[:400]
            raise RuntimeError(f"引擎无响应（{method}）: {err}")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(f"引擎报错（{method}）: {resp.get('error')}")
        return resp["result"]

    def raw(self, line: str) -> dict:
        """发一行原始文本（可以故意是坏的），读回一帧。"""
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        got = self.proc.stdout.readline()
        return json.loads(got) if got else {}

    def close(self) -> None:
        try:
            self.call("shutdown", {})
        except Exception:  # noqa: BLE001 —— 收尾失败不影响结论
            pass
        try:
            self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass


def read_memory(memory_path: Path) -> tuple:
    """把真实记忆复制到工作区临时目录后只读加载（不碰用户原文件）。"""
    tmp = ACE_DIR / ".test_tmp" / f"xcheck_{uuid.uuid4().hex[:8]}"
    tmp.mkdir(parents=True, exist_ok=True)
    copy = tmp / "memory.json"
    shutil.copyfile(memory_path, copy)
    arch = py_archive.MemoryArchive(str(copy), session_tag="default")
    return arch, tmp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="", help="引擎可执行文件路径")
    ap.add_argument("--memory", default="", help="记忆文件（默认 ace/.agent_memory.json）")
    ap.add_argument("--queries", type=int, default=20, help="基准用的查询条数")
    ap.add_argument("--repeat", type=int, default=100, help="每个查询重复次数")
    args = ap.parse_args()

    exe = args.engine or str(ENGINE_DIR / "target" / "release" /
                             ("ace-engine.exe" if os.name == "nt" else "ace-engine"))
    if not Path(exe).is_file():
        print(f"❌ 找不到引擎二进制: {exe}\n   先构建: cd engine && cargo build --release")
        return 2
    memory_path = Path(args.memory) if args.memory else (ACE_DIR / ".agent_memory.json")
    if not memory_path.is_file():
        print(f"❌ 找不到记忆文件: {memory_path}")
        return 2

    arch, tmp = read_memory(memory_path)
    entries = arch.entries
    print(f"[xcheck] 引擎: {exe}")
    print(f"[xcheck] 记忆: {memory_path.name} → {len(entries)} 条（已复制到临时目录，只读加载）")
    if not entries:
        print("❌ 记忆为空，无法对拍")
        return 2

    eng = Engine(exe)
    print(f"[xcheck] 引擎握手: {eng.info}")

    # ---------------------------------------------------------------- 1. 兼容性
    print("\n[1] 兼容性对拍（引擎必须逐位复现 Python）")

    samples = [e.text for e in entries[:40]]
    samples += ["", "a", "abc", "hello world", "帮我看看 core/archive.py",
                "中文测试", "SimHash 中文 test_1", "def foo(x): return x",
                "ACE-ENGINE 与 core/archive.py 必须一致", "12345_67890"]

    bad_hash = []
    for s in samples:
        want = format(py_archive.simhash(s), "016x")
        got = eng.call("fingerprint", {"text": s})["hex"]
        if got != want:
            bad_hash.append((s[:40], want, got))
    check(f"SimHash 逐位一致（{len(samples)} 条含中文/边界）", not bad_hash,
          f"{bad_hash[:3]}")

    bad_tok = []
    for s in samples[:30]:
        want = py_archive._tokenize(s)
        got = eng.call("tokenize", {"text": s})["tokens"]
        if got != want:
            bad_tok.append((s[:30], want[:6], got[:6]))
    check("分词序列完全一致（含顺序）", not bad_tok, f"{bad_tok[:2]}")

    bad_sim = []
    pairs = [(entries[i].text, entries[j].text)
             for i, j in zip(range(0, min(20, len(entries))),
                             range(1, min(21, len(entries))))]
    pairs += [("帮我看看 archive", "核心 archive 的 simhash"), ("abc", "xyz")]
    for a, b in pairs:
        want = round(py_archive.text_similarity(a, b), 4)
        got = eng.call("similarity", {"a": a, "b": b})["text_similarity"]
        if abs(want - got) > 1e-9:
            bad_sim.append((a[:20], want, got))
    check(f"主题相似度一致（{len(pairs)} 对）", not bad_sim, f"{bad_sim[:3]}")

    # 召回：同一条目集、同参数，比较**顺序 + 数值 + 身份**
    eng.call("index.build", {"entries": [
        {"id": str(i), "text": e.text, "weight": e.weight, "session": e.session}
        for i, e in enumerate(entries)]})

    queries = []
    for i in range(0, min(args.queries, len(entries))):
        queries.append(entries[i].text[:120])
    queries += ["simhash 记忆召回", "这个查询与任何记忆都无关 asdfqwer"]

    bad_recall = []
    for q in queries:
        want = [(r["similarity"], r["score"], r["text"][:200])
                for r in arch.get_memory(q, top_k=3)]
        items = eng.call("recall", {"query": q, "session": "default", "top_k": 3})["items"]
        got = []
        for it in items:
            src = entries[int(it["id"])]
            got.append((it["similarity"], it["score"], src.text[:200]))
        if want != got:
            bad_recall.append((q[:30], want[:2], got[:2]))
    check(f"召回结果一致：顺序 / similarity / score（{len(queries)} 次查询）",
          not bad_recall, f"{bad_recall[:2]}")

    # 畸形帧：引擎必须**活着**。ace_serve 的 `v="abc"` 会抛裸 ValueError 穿出
    # serve_forever 把进程带走（后端评审 §2.1）—— 这条要求引擎不重演那件事。
    garbage = [
        "not json at all",
        '{"type":"req","id":"g1","method":"stats"}',          # 缺 v
        '{"v":"abc","type":"req","id":"g2","method":"stats"}',  # v 不是整数
        '{"v":9,"type":"req","id":"g3","method":"stats"}',      # 版本不认识
        '{"v":1,"type":"req","id":"g4","method":"nope"}',       # 未知方法
    ]
    answered = []
    for g in garbage:
        r = eng.raw(g)
        answered.append(r.get("ok") is False and bool((r.get("error") or {}).get("code")))
    alive_hex = eng.call("fingerprint", {"text": "still alive"})["hex"]
    alive = alive_hex == format(py_archive.simhash("still alive"), "016x")
    check(f"畸形帧不杀会话（{len(garbage)} 条），之后仍能正常应答",
          all(answered) and alive, f"answered={answered} alive={alive}")

    # ---------------------------------------------------------------- 1b. 元处理：事件索引
    print("\n[1b] 元处理切片①：事件索引（引擎 ↔ core/ace_engine.py 的降级实现）")
    from core import ace_engine as _ae  # noqa: E402
    logs = sorted((ACE_DIR / ".ace_sessions").glob("*.jsonl"),
                  key=lambda p: -p.stat().st_size)
    if not logs:
        print("  （没有会话日志，跳过事件对拍）")
    else:
        log = logs[0]
        engine_side = _ae.session_meta(log)
        saved_path = _ae.engine_path
        _ae.engine_path = lambda: None          # 强制降级路径
        try:
            py_side = _ae.session_meta(log)
        finally:
            _ae.engine_path = saved_path
        fields = ("events", "bad_json", "missing_fields", "duplicate_lines", "kinds",
                  "tools", "bytes", "seq", "unknown_kinds")
        diff = [f for f in fields if engine_side.get(f) != py_side.get(f)]
        check(f"引擎与降级实现逐字段相等（{log.name}，9 个字段）", not diff,
              f"差异字段: {diff}")
        check("来源如实标注（降级不是静默失败）",
              engine_side.get("source") == "ace-engine"
              and py_side.get("source") == "python",
              f"{engine_side.get('source')}/{py_side.get('source')}")
        verify = _ae.session_verify(log)
        check("append-only 契约体检有结论（ok/checked/problems 齐备）",
              isinstance(verify.get("ok"), bool) and verify.get("checked", 0) > 0,
              str(verify)[:120])
        print(f"  真实日志: {engine_side.get('events')} 事件 · "
              f"{(engine_side.get('bytes') or {}).get('total', 0):,} B → "
              f"去重 {(engine_side.get('bytes') or {}).get('unique', 0):,} B")

    # ---------------------------------------------------------------- 2. 基准
    print("\n[2] 基准（真实数据，引擎侧含 IPC 往返）")
    bench_q = queries[:max(1, min(args.queries, len(queries)))]
    top_k = 3

    for _ in range(20):                      # 两侧都预热（Python 侧 _tokenize 有 lru_cache）
        arch.get_memory(bench_q[0], top_k=top_k)
        eng.call("recall", {"query": bench_q[0], "session": "default", "top_k": top_k})

    t0 = time.perf_counter()
    for _ in range(args.repeat):
        for q in bench_q:
            arch.get_memory(q, top_k=top_k)
    py_ms = (time.perf_counter() - t0) * 1000 / (args.repeat * len(bench_q))

    t0 = time.perf_counter()
    for _ in range(args.repeat):
        for q in bench_q:
            eng.call("recall", {"query": q, "session": "default", "top_k": top_k})
    rs_ms = (time.perf_counter() - t0) * 1000 / (args.repeat * len(bench_q))

    # 纯算力（无 IPC）：交给引擎自己的 --bench
    job = json.dumps({"texts": [e.text for e in entries], "queries": bench_q,
                      "session": "default", "top_k": top_k, "iterations": 200},
                     ensure_ascii=False)
    raw = subprocess.run([exe, "--bench"], input=job, capture_output=True,
                         text=True, encoding="utf-8")
    pure = json.loads(raw.stdout.strip().splitlines()[-1]) if raw.stdout.strip() else {}

    n = len(entries)
    print(f"  条目数: {n}   查询数: {len(bench_q)}   每查询重复: {args.repeat}")
    print(f"  Python  MemoryArchive.get_memory : {py_ms:.3f} ms/次")
    print(f"  Rust    引擎 recall（含 IPC）    : {rs_ms:.3f} ms/次"
          f"   → 加速 {py_ms / rs_ms:.1f}×" if rs_ms > 0 else "")
    if pure:
        print(f"  Rust    引擎 recall（纯算力）    : {pure.get('recall_per_call_ms')} ms/次"
              f"   → 加速 {py_ms / max(pure.get('recall_per_call_ms', 1e-9), 1e-9):.1f}×")
        print(f"  Rust    建索引一次               : {pure.get('build_ms')} ms"
              f"（{n} 条）")
        print(f"  Rust    指纹吞吐                 : {pure.get('fingerprint_ms')} ms"
              f" / {pure.get('fingerprint_chars')} 字符")

    # ---------------------------------------------------------------- 3. 结论
    eng.close()
    shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n[xcheck] 对拍通过 {passed} / {total}")
    if passed != total:
        print("[xcheck] FAILED —— 引擎与 Python 语义不一致，不许上线")
        return 1
    print("[xcheck] ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
