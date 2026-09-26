#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_sessionlog —— 会话事件日志（借鉴 DSH session 子系统的分期落地第一步）

DSH 的第一原则是「模型可见 ⟺ 可记录」：任何到达模型的输入、任何模型输出、
任何工具往返，都必须能从一份 append-only 事件日志里重建。压缩、回滚、审计、
调试因此都站在同一份事实源上，而不是各自维护一份内存状态。

本模块实现该原则的**阶段 1**（核心，不依赖 surface 投影）：
- append-only JSONL 落盘：事件只追加不修改，崩溃不产生半截记录
- seq 连续契约：每事件一个递增序号，跳号即丢事件，消费方可检测
- 深冻结：payload 在追加点做 JSON 序列化校验，坏事件当场失败而不是落盘后才发现
- 线程安全：CLI 与执行层并发追加不交错

阶段 2（surface 投影 / 无损压缩）留给后续：先有"事实源"，再做"从事实源派生"。

**RG-02（链式签名）**：append-only 只保证"只追加"，不保证"没被改过"。实测（探针
`_rel_test/rg02_probe.py`）：把一条 `permission/decision` 从 `deny` 改成 `allow`、
或往尾部追加一条伪造事件，`seq_contiguous()` 都返回 True，日志里也**没有任何字段**能说明
它被动过 —— 一份可被静默重写的审计记录，恰好能重写掉安全裁决那一行。所以每条事件带一个
`mac = HMAC(台账密钥, prev_mac ‖ 该条正文)`：改内容、删中间一条、剥掉某条的 mac、尾部伪造
都会让整链对不上。密钥来自 `core/guardian` 的**锚**（工作区之外），与快照签名密钥分开派生。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

# 事件种类（与 DSH SessionEventMap 对齐的 ACE 子集）
K_SESSION_START = "session/start"        # 会话头（在哪个文件夹里开的）
K_USER_MESSAGE = "user/message"          # 到达模型的用户输入（含注入的记忆/目标续跑）
K_ASSISTANT_MESSAGE = "assistant/message"  # 模型本轮完整输出（原文，含协议/JSON）
K_REQUEST_SNAPSHOT = "request/snapshot"  # 每次模型请求的 envelope 摘要（可重建"模型看到了什么"）
K_SYSTEM_SNAPSHOT = "system/snapshot"    # 每次模型请求的完整系统提示词（含 AGENTS.md/记忆/目标）
K_TOOL_CALL = "tool/call"                # 模型发出的工具调用（原始参数）
K_TOOL_RESULT = "tool/result"            # 工具执行结果（状态 + 摘要）
K_PERMISSION = "permission/decision"    # 执行层权限裁决（allow/deny/confirm/grant）
K_SECURITY = "security/denied"           # 安全拦截（路径越界/白名单/沙盒/敏感目标）—— 单独一类便于分级（SEC-017）
K_GUARD = "guard/verdict"                # 守卫违规 / 诱饵 / AST 拦截
K_SNAPSHOT_CREATE = "snapshot/create"    # 写入前快照
K_SNAPSHOT_ROLLBACK = "snapshot/rollback"  # 回滚
K_SNAPSHOT_FAIL = "snapshot/unavailable"  # 快照不可用（H-05：fail-close 的决定必须留痕）
K_GOAL_ROUND = "goal/round"              # 目标轮次推进
K_MODEL_ERROR = "model/error"            # 模型 API 调用失败
K_MODEL_USAGE = "model/usage"            # 每轮 token 用量与成本估算（本轮**增量**，不是累计）
K_COMPACTION = "compaction/event"        # 上下文压缩
K_MODEL_SWITCH = "model/switch"          # 模型/提供商切换


MAC_FIELD = "mac"
_CHAIN_DOMAIN = b"ace-sessionlog-chain-v1"


def _canonical_body(ev: Dict[str, Any]) -> str:
    """事件正文的规范形式（**不含 `mac` 本身**）：键排序 + 紧凑分隔符。

    为什么必须规范化：校验时要拿"文件里那条"重新算一遍 MAC，而写的时候是插入序 ——
    只要按解析后的 dict 直接重算，键序一变就对不上。排序键 + 固定分隔符让两边恒等。
    """
    return json.dumps({k: v for k, v in ev.items() if k != MAC_FIELD},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_mac(key: bytes, prev_mac: str, ev: Dict[str, Any]) -> str:
    """`mac = HMAC(key, prev_mac ‖ 本条正文)`。

    把**上一条的 MAC** 一起签进去，才有"链"：单条独立签名挡不住**删中间一条**
    （剩下的每条自己都还是自洽的），而链一断就全露。
    """
    msg = _CHAIN_DOMAIN + prev_mac.encode("utf-8") + b"\n" + \
        _canonical_body(ev).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


class SessionLog:
    """append-only 会话事件日志。path 指向 .jsonl 文件。"""

    def __init__(self, path: str, mac_key: Optional[bytes] = None,
                 project_root: Optional[str] = None,
                 anchor_dir: Optional[str] = None) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._next_seq = 1
        self._prev_mac = ""
        self._legacy_prefix = 0          # 早于链式签名、无法核验的前缀条数
        self._mac_key: Optional[bytes] = mac_key
        self._mac_key_tried = mac_key is not None
        self._mac_error = ""
        self._mac_warned = False
        # 锚的定位需要项目根：默认取日志目录的上一级（`.ace_sessions/x.jsonl` → 项目根）
        self._project_root = Path(project_root) if project_root else self.path.parent.parent
        self._anchor_dir = anchor_dir    # 与 Guardian 同义的注入点（受限环境/测试）
        self._load_seq()

    def _load_seq(self) -> None:
        """从已有文件恢复 seq **与链尾**：任何时刻重放都能接着写（跨进程续记）。"""
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    last = 0
                    prefix = 0
                    started = False
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                            last = max(last, int(ev.get("seq", 0)))
                        except (json.JSONDecodeError, ValueError, TypeError):
                            continue   # 半截尾部（崩溃残留）跳过，不阻塞续记
                        mac = ev.get("mac")
                        if isinstance(mac, str) and mac:
                            started = True
                            self._prev_mac = mac
                        elif not started:
                            prefix += 1        # 老日志：这一段没签名，续写时另起链段
                    self._next_seq = last + 1
                    self._legacy_prefix = prefix
        except OSError:
            pass

    # ---------- 链式签名（RG-02） ----------

    def _get_mac_key(self) -> Optional[bytes]:
        """台账密钥：从锚派生（与快照签名密钥**分开**：各用各的，互不牵连）。

        取不到时返回 None 并记下原因 —— 调用方据此**如实标记**这批事件没有签名，
        而不是假装签过。台账是"记录"，不是"闸门"：写不下去会让整轮对话挂掉，
        而攻击者本来就能删掉整份日志，所以这里不 fail-close，只 fail-loud。
        """
        if self._mac_key_tried:
            return self._mac_key
        self._mac_key_tried = True
        try:
            from core.guardian import anchor_dir_for, load_or_create_anchor_secret
            secret = load_or_create_anchor_secret(
                anchor_dir_for(self._project_root, self._anchor_dir) / "sessionlog_key")
            self._mac_key = hmac.new(secret.encode("utf-8"),
                                     b"ace-sessionlog-v1", hashlib.sha256).digest()
        except Exception as e:      # noqa: BLE001 —— 锚不可用不该让对话挂掉，但要看得见
            self._mac_error = f"{type(e).__name__}: {e}"
            self._mac_key = None
        return self._mac_key

    def append(self, kind: str, payload: Dict[str, Any]) -> int:
        """追加一个事件，返回其 seq。payload 必须是可 JSON 序列化的 dict（深冻结）。"""
        with self._lock:
            ev: Dict[str, Any] = {
                "seq": self._next_seq,
                "kind": kind,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                **payload,
            }
            # 深冻结契约要在**算 MAC 之前**兑现：不可序列化的 payload 必须在这里当场失败，
            # 抛既有的 ValueError（有断言盯着）；否则会在规范化那步漏出 TypeError。
            try:
                _canonical_body(ev)
            except (TypeError, ValueError) as e:
                raise ValueError(f"事件 payload 不可序列化（kind={kind}）: {e}") from e
            key = self._get_mac_key()
            if key is not None:
                ev[MAC_FIELD] = _event_mac(key, self._prev_mac, ev)
            elif not self._mac_warned:
                self._mac_warned = True
                print(f"⚠ 台账密钥不可用（{self._mac_error}）：本次会话的事件不带 MAC，"
                      f"`/audit stats` 会如实报『不可核验』", file=sys.stderr)
            line = json.dumps(ev, ensure_ascii=False, separators=(",", ":"))
            self.path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
            if key is not None:
                self._prev_mac = ev[MAC_FIELD]
            seq = self._next_seq
            self._next_seq += 1
            return seq

    def verify_chain(self) -> Tuple[str, str]:
        """校验整链。返回 `(status, detail)`：

        - `"ok"`：每条（链段内）的 MAC 都对得上 —— 没被改、没被删、没被插；
        - `"broken"`：第几条对不上，或某条被剥掉了 MAC；
        - `"unverifiable"`：整份都没有 MAC（早于链式签名），或拿不到台账密钥；
        - `"empty"`：空日志（没东西可验，也不假装"通过"）。

        为什么不是布尔：**"验过了没问题"与"根本没法验"必须能区分** —— 把后者当 ok
        正是这类机制最常见的失效方式（旧日志、锚丢失都会被读成"一切正常"）。
        """
        evs = list(self.events())
        if not evs:
            return "empty", "空日志"
        signed = [e for e in evs if isinstance(e.get(MAC_FIELD), str) and e[MAC_FIELD]]
        if not signed:
            return "unverifiable", f"整份日志都没有 MAC（早于链式签名），{len(evs)} 条"
        key = self._get_mac_key()
        if key is None:
            return "unverifiable", f"拿不到台账密钥，无法核验（{self._mac_error}）"
        prev = ""
        started = False
        prefix = 0
        for i, e in enumerate(evs, 1):
            mac = e.get(MAC_FIELD)
            if not (isinstance(mac, str) and mac):
                if not started:
                    prefix += 1
                    continue
                return "broken", f"第 {i} 条缺少 MAC（被剥离或伪造）"
            started = True
            if not hmac.compare_digest(mac, _event_mac(key, prev, e)):
                return "broken", f"第 {i} 条内容与 MAC 不符（被改过或被插进链里）"
            prev = mac
        detail = f"链完整，{len(signed)} 条"
        if prefix:
            detail += f"；前缀 {prefix} 条不可核验（早于链式签名）"
        return "ok", detail

    def events(self) -> Iterator[Dict[str, Any]]:
        """按序重放全部事件（生成器，可流式消费）。"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        """最近 n 条事件（审计/排障用）。"""
        all_ev = list(self.events())
        return all_ev[-n:]

    def seq_contiguous(self) -> bool:
        """seq 是否从 1 连续无跳号（丢事件检测）。"""
        expect = 1
        for ev in self.events():
            if int(ev.get("seq", 0)) != expect:
                return False
            expect += 1
        return True

    def count(self) -> int:
        return sum(1 for _ in self.events())

    # ---------- 便捷记录方法（会话层调用） ----------

    def record_session_start(self, project_root: str = "", cwd: str = "",
                             model: str = "") -> int:
        """写一条会话头：**这段会话是在哪个文件夹里开的**。

        为什么要记：`/sessions` 与主页要把"继续哪一段"讲清楚，而"在哪个项目里"
        是比时间更有用的线索（同一天可能在三个项目里各聊过一段）。不记的话，
        列表只能显示"昨天 · 3 轮 · 帮我改一下 X"，用户根本认不出是哪一段。
        """
        return self.append(K_SESSION_START, {
            "project_root": str(project_root or ""),
            "cwd": str(cwd or ""),
            "model": str(model or ""),
        })

    def record_user(self, content: str) -> int:
        return self.append(K_USER_MESSAGE, {"content": content})

    def record_assistant(self, content: str) -> int:
        return self.append(K_ASSISTANT_MESSAGE, {"content": content})

    def record_request(self, *, model: str, base_url: str, permission: str,
                       system_len: int, messages_count: int,
                       subagent: str = "") -> int:
        """每次模型请求的 envelope 摘要：足够重建"这次请求模型看到了什么"的结构。
        subagent 非空表示这是子代理请求（spawn/fork），replay 时可区分。"""
        return self.append(K_REQUEST_SNAPSHOT, {
            "model": model, "base_url": base_url, "permission": permission,
            "system_len": system_len, "messages_count": messages_count,
            "subagent": subagent,
        })

    def record_tool_call(self, tool: str, params: Dict[str, Any]) -> int:
        return self.append(K_TOOL_CALL, {"tool": tool, "params": params})

    def record_tool_result(self, tool: str, status: str, message: str = "",
                           elapsed_ms: int = 0) -> int:
        """工具结果。`elapsed_ms` 是**实测耗时**（执行层 `result.metadata["elapsed"]`，秒 → 毫秒）。

        为什么要记它：耗时此前只活在内存里，落进日志之前谁也聚合不了 —— 而 `ts` 只有秒级
        粒度（实测 262 份真实日志：平均 11.2 事件却只有 1.8 个不同 ts），所以"哪个工具慢"
        根本推不出来。这个字段一落，度量就能算。
        """
        payload = {"tool": tool, "status": status, "message": (message or "")[:300]}
        if elapsed_ms:
            payload["elapsed_ms"] = int(elapsed_ms)
        return self.append(K_TOOL_RESULT, payload)

    def record_usage(self, *, model: str, in_tokens: int, out_tokens: int,
                     usd: Optional[float] = None, subagent: str = "") -> int:
        """每轮 token 用量（**增量**）与成本估算。

        为什么是增量：累计值写进 append-only 日志，重放时会一路翻倍；增量重放求和才是真值。
        为什么由这里记：`self._cost` 只活在内存里，会话一结束就没了，跨会话的用量/成本
        无从聚合 —— 而日志是唯一事实源。
        """
        payload = {"model": model, "in_tokens": int(in_tokens),
                   "out_tokens": int(out_tokens)}
        if usd is not None:
            payload["usd"] = round(float(usd), 6)
        if subagent:
            payload["subagent"] = subagent
        return self.append(K_MODEL_USAGE, payload)

    def record_goal_round(self, rounds_started: int, max_rounds: int) -> int:
        return self.append(K_GOAL_ROUND, {
            "rounds_started": rounds_started, "max_rounds": max_rounds})

    def record_system(self, system: str) -> int:
        """每次请求的完整系统提示词（含 AGENTS.md/记忆注入/目标——"模型看到了什么"的全文）。"""
        return self.append(K_SYSTEM_SNAPSHOT, {"system": system})

    def record_permission(self, tool: str, decision: str,
                          level: str, detail: str = "",
                          attribution: str = "", would_escalate: bool = False,
                          recovery: str = "", recovery_release: bool = False) -> int:
        """`attribution` / `recovery` 等只在**写类工具放行**那一处传（RG-03/RG-04 测量版）。

        刻意做成可选：不传时 payload 与旧版**逐字相同**，免得给其余十来处调用点改事件形状。
        """
        payload = {"tool": tool, "decision": decision, "level": level,
                   "detail": (detail or "")[:200]}
        if attribution:
            payload["attribution"] = attribution
            payload["would_escalate"] = bool(would_escalate)
        if recovery:
            payload["recovery"] = recovery
            payload["recovery_release"] = bool(recovery_release)
        return self.append(K_PERMISSION, payload)

    def record_guard(self, rule: str, action: str, detail: str = "") -> int:
        return self.append(K_GUARD, {"rule": rule, "action": action,
                                     "detail": (detail or "")[:200]})

    def record_security(self, tool: str, reason: str, count: int) -> int:
        """安全拦截单列一类（SEC-017）：403 里的"执行层主动防御"与 400 参数错不是一回事，
        混在同一条失败路径里，事后没法按安全事件分级查看。"""
        return self.append(K_SECURITY, {"tool": tool, "reason": (reason or "")[:200],
                                        "count": int(count)})

    def record_snapshot(self, kind: str, snapshot_id: str, tag: str = "") -> int:
        return self.append(kind, {"snapshot_id": snapshot_id, "tag": tag})

    def record_model_error(self, err: str, hint: str = "") -> int:
        return self.append(K_MODEL_ERROR, {"error": (err or "")[:300],
                                           "hint": (hint or "")[:200]})

    def record_compaction(self, before: int, after: int, reason: str) -> int:
        return self.append(K_COMPACTION, {
            "before": before, "after": after, "reason": reason})

    # ---------- 从日志重建（DSH B2：消息历史 = 日志派生，不单独存储） ----------

    def replay_messages(self) -> List[Dict[str, str]]:
        """从事件日志重建模型看到的消息序列（user/assistant 交替，按 seq 排序）。

        阶段 2a 能力：消息历史是日志的派生视图 —— 审计、调试、未来的 resume
        重放重建都从这一份事实源来，而不是各自维护一份内存副本。
        """
        msgs: List[Dict[str, str]] = []
        for ev in self.events():
            if ev.get("kind") == K_USER_MESSAGE:
                msgs.append({"role": "user", "content": ev.get("content", "")})
            elif ev.get("kind") == K_ASSISTANT_MESSAGE:
                msgs.append({"role": "assistant", "content": ev.get("content", "")})
        return msgs


def list_sessions(sessions_dir: str, limit: int = 3) -> List[Dict[str, Any]]:
    """最近会话摘要（首屏用）：文件名、修改时间、消息条数、首条用户输入。

    只读、**任何异常都退化成空列表** —— 首屏不该因为一个半截日志文件就崩掉，
    "看不到历史"远比"界面上抛出 traceback"可接受。
    每份日志只读到找到首条用户输入为止，不整体解析（旧会话可能很大）。
    """
    out: List[Dict[str, Any]] = []
    try:
        d = Path(sessions_dir)
        if not d.is_dir():
            return out
        files = sorted((p for p in d.glob("*.jsonl") if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:max(0, int(limit))]
    except OSError:
        return out
    for p in files:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        msgs = 0
        first = ""
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("kind") == K_USER_MESSAGE:
                        msgs += 1
                        if not first:
                            first = str(ev.get("content", ""))
                        elif msgs >= 200:
                            break
        except OSError:
            pass
        out.append({"name": p.name, "mtime": mtime, "messages": msgs, "preview": first})
    return out
