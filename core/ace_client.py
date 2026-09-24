#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_client —— 两个前端共用的**唯一一份**模型 HTTP 客户端（R-03 的收口处）

在这之前，项目里有两条各自独立、各自演化过的模型调用路径：

  · `ai_code.ModelClient`     —— requests + 流式（SSE）+ Anthropic 变体降级 + tools 非流式
  · `agent_runner._post_chat` —— 纯 stdlib urllib 一次性调用，错误文案与输出契约都另写一份

于是"怎么打这个端点"这件事有两个地方知道：URL 怎么拼、头怎么带、重试找谁、tools
被拒之后怎么办，改一处漏一处。R-03 的上一半已经把**纯逻辑**收进了 `core/ace_model.py`
（历史裁剪 / 错误码提示）；这一半收的是**唯一那条出网路径**。

设计取态：

  1. **一家做传输，各家做契约。** 这里只负责"把请求打出去、把响应读回来、把失败
     规范化"，以及三种调用形态（一次性 JSON / 流式 SSE / Anthropic 变体降级）。
     至于"模型这段话是什么意思"（协议文本转换、清洗、最终回复包装）仍归
     `agent_runner` —— 那是前端契约，不是传输层的事。
  2. **降级策略由调用方定，降级循环由这里跑。** 两家前端对"端点不支持 tools"
     的判据不同（ai_code 认 400/404，agent_runner 还要求错误正文里有 "tool"），
     所以 `chat_stream` 只提供**一次重来**的机会，要不要重来由 `should_degrade`
     判定；循环本身只写一遍，避免又长出两份。
  3. **错误规范化成 `ChatHTTPError`，但保留原始异常。** 两家前端原先分别用
     `requests.HTTPError` 和 `urllib.error.HTTPError` 的私有细节做判断
     （`.response.status_code`、`e.read()`），这些细节一并暴露出来，
     迁移才是"换调用点"而不是"改行为"。
  4. **零项目依赖。** 只 import `core.ace_http`（同为纯 stdlib）——谁都能安全地引它，
     `requests` 仍然只在真要发请求时才用（惰性 import，无依赖的解释器照样跑得动）。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import ace_http

# —— 端点路径（两个前端从这里取，不再各自字面量拼一遍）——
OPENAI_CHAT_PATH = "/chat/completions"
ANTHROPIC_MESSAGES_PATH = "/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# 出网预算。300s 给长回答留足时间；重试次数与总时长封顶在 ace_http.RetryPolicy 里。
CHAT_TIMEOUT = 300
ANTHROPIC_TIMEOUT = 300

# 错误正文进异常/日志只留这么长 —— 有些端点的错误正文是一整页 HTML。
ERROR_BODY_CHARS = 400


class ChatHTTPError(RuntimeError):
    """模型端点的 HTTP 失败（**规范化后的唯一错误类型**）。

    `status` / `body` 是给调用方做降级判断用的：
      · `body` 在第一次访问时读一次并缓存 —— `urllib.error.HTTPError` 只能读一次，
        `requests.HTTPError` 的正文则永远可读，缓存把两者抹平成同一件事。

    `.response.status_code` 也照旧可用：`ace_model.error_hint` 按 HTTP 错误码出
    排查提示，读的就是这个属性 —— 规范化的异常不该让那条提示失灵。
    """

    def __init__(self, status: Optional[int], body: str = "",
                 url: str = "", raw: Optional[BaseException] = None,
                 attempts: int = 0) -> None:
        head = f"HTTP {status}" if status is not None else "连接失败"
        super().__init__(f"{head} · {url}")
        self.status = status
        self.body = str(body or "")
        self.url = url
        self.raw = raw
        self.attempts = attempts
        if status is not None:
            self.response = type("ChatResponse", (), {"status_code": status})()


def _requests():
    """惰性取 requests；没装就返回 None（纯 stdlib 环境照样能 import 本模块）。"""
    try:
        import requests
    except ImportError:
        return None
    return requests


def _response_body(exc: BaseException) -> str:
    """尽量取出错误正文（截断后返回）。取不到就返回空串 —— 降级判断要的是"有没有那句话"。"""
    resp = getattr(exc, "response", None)
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text:
        return text[:ERROR_BODY_CHARS]
    read = getattr(exc, "read", None)          # urllib.error.HTTPError 本身就是响应对象
    if callable(read):
        try:
            data = read()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="ignore")[:ERROR_BODY_CHARS]
            return str(data or "")[:ERROR_BODY_CHARS]
        except Exception:                      # noqa: BLE001 —— 响应体读不出来不是致命问题
            return ""
    return ""


def _http_error(exc: BaseException, url: str) -> Optional[ChatHTTPError]:
    """把两家 HTTP 库的失败规范化成 `ChatHTTPError`；不是 HTTP 失败就返回 None。

    urllib 把 4xx/5xx 抛成 HTTPError，requests 同样抛 HTTPError，两边都带 `response`。
    其余（连接抖动、超时）由 `RetryExhausted` 代表，不在这里处理。
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    resp = getattr(exc, "response", None)
    if status is None and resp is not None:
        status = getattr(resp, "status_code", None)
    if status is None:
        return None
    return ChatHTTPError(int(status), _response_body(exc), url, raw=exc)


def resolve_error(exc: BaseException, url: str = "") -> BaseException:
    """任意异常 → 可判断的错误。HTTP 失败变 `ChatHTTPError`，其余原样返回。

    **时间点很关键**：正文必须在 retry 层抛出异常的那一刻读掉（urllib 的
    HTTPError 只能读一次，晚一步拿到的就是空串）。
    """
    if isinstance(exc, ChatHTTPError):
        return exc
    err = _http_error(exc, url)
    return err if err is not None else exc


def _run(url: str, *, method: str, headers: Dict[str, str], payload: Dict[str, Any],
         stream: bool, timeout: int,
         on_retry: Optional[Callable[..., None]] = None):
    """出网一次（含 ace_http 的退避重试），返回状态已检查过的响应；失败已规范化。"""
    try:
        return ace_http.request_with_retry(
            method, url, headers=headers, json=payload,
            stream=stream, timeout=timeout, on_retry=on_retry)
    except Exception as exc:                     # noqa: BLE001 —— 只为规范化错误类型
        raise resolve_error(exc, url) from exc


# ============================================================
# 载荷构造（纯函数：形状固定，两个前端共用同一套）
# ============================================================

def openai_payload(model: str, messages: List[Dict], *, stream: bool = True,
                   tools: Optional[List[Dict]] = None,
                   temperature: float = 0.2) -> Dict[str, Any]:
    """OpenAI 兼容 `/chat/completions` 的请求体。

    带 tools 时应当**非流式**（调用方传 stream=False）：Ollama 一类端点的兼容层在
    stream=true 下会丢掉 tool_calls 增量（ollama#7881 / #5769），后果不是报错而是
    静默降级 —— 模型明明生成了 file_write，agent 只收到一段"我已经帮你创建好了"
    的纯文本，文件根本没写。打字机效果没有"工具真的被执行"重要。
    """
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": bool(stream),
        "temperature": temperature,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return body


def anthropic_payload(model: str, system: str, messages: List[Dict], *,
                      stream: bool = True, max_tokens: int = 8192) -> Dict[str, Any]:
    """Anthropic `/v1/messages` 的一种载荷形状（变体见 `anthropic_payload_variants`）。"""
    return {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": messages, "stream": bool(stream)}


def anthropic_payload_variants(system: str, messages: List[Dict], *,
                               model: str) -> List[Dict[str, Any]]:
    """多组兼容变体：不同服务商对 system 字段格式 / 流式支持要求不一，逐个降级尝试。

    顺序即优先级：先用最常规的（system 字符串 + 流式），最后才退到非流式。
    """
    base = {"model": model, "max_tokens": 8192, "messages": messages}
    msgs_blocks = [
        {"role": m.get("role", "user"),
         "content": [{"type": "text", "text": str(m.get("content", ""))}]}
        for m in messages
    ]
    sys_blocks = [{"type": "text", "text": system}]
    return [
        {**base, "system": system, "stream": True},
        {**base, "system": sys_blocks, "stream": True},
        {**base, "system": system, "messages": msgs_blocks, "stream": True},
        {**base, "system": sys_blocks, "messages": msgs_blocks, "stream": True},
        {**base, "system": system, "stream": False},
        {**base, "system": sys_blocks, "stream": False},
    ]


# ============================================================
# 一次性调用（非流式）
# ============================================================

def chat_complete(base_url: str, api_key: str, payload: Dict[str, Any], *,
                  timeout: int = CHAT_TIMEOUT,
                  on_retry: Optional[Callable[..., None]] = None) -> Dict[str, Any]:
    """POST {base}/chat/completions，返回解析后的 JSON。429/5xx/连接抖动按 ace_http 退避。

    4xx 规范化成 `ChatHTTPError` 抛出，**在抛出前把错误正文读下来** ——
    "端点不认 tools 参数"这件事只能从正文里看出来（见 `_http_error`）。
    """
    url = f"{str(base_url).rstrip('/')}{OPENAI_CHAT_PATH}"
    with _run(url, method="POST",
              headers={"Authorization": f"Bearer {api_key}",
                       "Content-Type": "application/json"},
              payload=payload, stream=False, timeout=timeout,
              on_retry=on_retry) as r:
        return r.json()


# ============================================================
# 流式调用（SSE 或一次性；tools 增量照收）
# ============================================================

def _emit(on_delta: Optional[Callable[[str], None]], full: str,
          chunk: str = "", *, newline: bool = False,
          last: List[Optional[str]] = None) -> None:
    """增量交付：有回调就把"到目前为止的完整文本"交出去，没有就直接打 stdout（老行为）。

    回调收到的是完整文本而不是增量片段 —— 两侧的展示层（Markdown 渲染器 /
    打字机）都是按"全量文本"记账的。

    `last` 是调用方给的"上次交付过什么"的小账本（只有一个元素的列表）：收尾那次
    不该重复交付同一份文本 —— 重复喂给 Markdown 渲染器是白做功，而展示层
    看到"文本没变"也无从分辨，索性在源头省掉。
    """
    if on_delta is not None:
        if last is None or last[0] != full:
            if last is not None:
                last[0] = full
            on_delta(full)
    elif chunk:
        print(chunk, end="", flush=True)
    if newline and on_delta is None:
        print()


def openai_message(body: Dict[str, Any]) -> Tuple[str, List[Dict]]:
    """从一次性响应里取出 `(正文, tool_calls 列表)`，与流式分支同构。"""
    choices = body.get("choices") or []
    msg = ((choices[0] or {}).get("message") or {}) if choices else {}
    calls = [tc for tc in (msg.get("tool_calls") or []) if isinstance(tc, dict)]
    return (msg.get("content") or ""), calls


def stream_openai(base_url: str, api_key: str, payload: Dict[str, Any], *,
                  on_delta: Optional[Callable[[str], None]] = None,
                  timeout: int = CHAT_TIMEOUT,
                  on_retry: Optional[Callable[..., None]] = None) -> Tuple[str, List[Dict]]:
    """OpenAI 兼容调用。返回 `(正文, tool_calls 列表)` —— 流式与非流式同构。

    流式只把**正文**增量交给 `on_delta`；tool_calls 的参数分片默默累积、不污染显示
    （那是 JSON 碎片，打出来只会让人以为模型在胡说）。
    """
    url = f"{str(base_url).rstrip('/')}{OPENAI_CHAT_PATH}"
    headers = {"Authorization": f"Bearer {api_key}"}
    tool_calls: Dict[int, Dict] = {}
    full = ""
    last: List[Optional[str]] = [None]

    if not payload.get("stream"):
        with _run(url, method="POST", headers=headers, payload=payload,
                  stream=False, timeout=timeout, on_retry=on_retry) as r:
            body = r.json()
        full, calls = openai_message(body)
        if full:
            _emit(on_delta, full, full)
        return full, calls

    # 重试只覆盖到"拿到响应头"为止，这一点是刻意的：此刻还没有任何字符吐给用户，
    # 重发是安全的。读到一半断流则不在覆盖范围内 —— 那时正文已经在屏幕上了，
    # 重发会造成重复输出，宁可报错。
    with _run(url, method="POST", headers=headers, payload=payload,
              stream=True, timeout=timeout, on_retry=on_retry) as r:
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            choices = obj.get("choices") or []
            delta = ((choices[0] or {}).get("delta", {}) if choices else {})
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if content:
                full += content
                _emit(on_delta, full, content, last=last)
            for tc in (delta.get("tool_calls") or []):
                if not isinstance(tc, dict):
                    continue
                idx = int(tc.get("index", 0))
                slot = tool_calls.setdefault(
                    idx, {"function": {"name": "", "arguments": ""}})
                fn = tc.get("function") or {}
                # 名字与参数都**追加**：分片协议下任何一个字段都可能被切开
                # （arguments 被切是常态；name 有些兼容层也会切），覆盖写会
                # 静默丢掉前半截，最后变成一个查不到的工具名。
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
    _emit(on_delta, full, "", newline=True, last=last)
    return full, [v for _, v in sorted(tool_calls.items())]


def anthropic_headers(api_key: str) -> Dict[str, str]:
    """Anthropic 兼容的头（x-api-key 而非 Bearer，两家端点就差在这一行）。"""
    return {"x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json"}


def post_anthropic(base_url: str, api_key: str, payload: Dict[str, Any], *,
                   on_delta: Optional[Callable[[str], None]] = None,
                   timeout: int = ANTHROPIC_TIMEOUT,
                   on_retry: Optional[Callable[..., None]] = None) -> str:
    """POST {base}/v1/messages，流式（SSE）与非流式（JSON）两种响应都处理，返回正文。

    重试在 ace_http 里，与调用方的变体循环分工明确：变体循环只管 400
    （"这个端点不认这种 payload 形状"），429/5xx 由退避接手 —— 一次 429
    不该让整个变体循环立刻放弃，那样用户看到的会是"已尝试多种请求格式"，
    而真实原因只是限流。
    """
    url = f"{str(base_url).rstrip('/')}{ANTHROPIC_MESSAGES_PATH}"
    streaming = bool(payload.get("stream"))
    with _run(url, method="POST", headers=anthropic_headers(api_key), payload=payload,
              stream=streaming, timeout=timeout, on_retry=on_retry) as r:
        if not streaming:
            data = r.json()
            blocks = data.get("content") or []
            full = "".join(b.get("text", "") for b in blocks
                           if isinstance(b, dict) and b.get("type") == "text")
            _emit(on_delta, full, full, newline=True)
            return full
        full = ""
        last: List[Optional[str]] = [None]
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            try:
                obj = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "content_block_delta":
                delta = obj.get("delta") or {}
                text = delta.get("text", "") if isinstance(delta, dict) else ""
                if text:
                    full += text
                    _emit(on_delta, full, text, last=last)
        _emit(on_delta, full, "", newline=True, last=last)
        return full


def stream_anthropic(base_url: str, api_key: str, system: str, messages: List[Dict], *,
                     model: str,
                     on_delta: Optional[Callable[[str], None]] = None,
                     timeout: int = ANTHROPIC_TIMEOUT,
                     on_retry: Optional[Callable[..., None]] = None) -> str:
    """Anthropic 调用：多格式变体自动降级，兼容不同服务商。"""
    last_err = ""
    for payload in anthropic_payload_variants(system, messages, model=model):
        try:
            return post_anthropic(base_url, api_key, payload, on_delta=on_delta,
                                  timeout=timeout, on_retry=on_retry)
        except ChatHTTPError as e:
            body = e.body
            last_err = f"{e} | 响应体: {body}"
            # 常见错误码给出可操作提示（如智谱 1214 = 模型名不存在）
            try:
                err_obj = json.loads(body or "{}")
                code = str(err_obj.get("error", {}).get("code", ""))
                msg = str(err_obj.get("error", {}).get("message", ""))
                if code == "1214" or "modelCode" in msg or "不存在" in msg:
                    last_err += ("\n提示: 该端点不存在这个模型名。用 /model glm-4.6 切换"
                                 "（智谱真实模型码，如 glm-4.6 / glm-4.5-air），或用 /config 改端点")
            except Exception:                  # noqa: BLE001 —— 错误正文不是 JSON 是常态
                pass
            if e.status != 400:
                break   # 401/403/429/5xx 等不换形状重试，避免浪费请求
    raise RuntimeError(f"模型 API 调用失败（已尝试多种请求格式）: {last_err}")


# ============================================================
# 高层入口：降级循环只写一遍
# ============================================================

def chat_stream(base_url: str, api_key: str, model: str, fmt: str,
                system: str, messages: List[Dict], *,
                tools: Optional[List[Dict]] = None,
                on_delta: Optional[Callable[[str], None]] = None,
                on_retry: Optional[Callable[..., None]] = None,
                should_degrade: Optional[Callable[[BaseException], bool]] = None,
                max_attempts: int = 2) -> Tuple[str, List[Dict]]:
    """按接口格式发一次（必要时**关掉 tools** 重来一次）→ `(正文, tool_calls)`。

    `should_degrade(exc)` 由调用方判断"这次失败是不是'端点不认 tools 参数'"：
    两家前端的判据不同（一家认 400/404，一家还要求正文里有 "tool"），所以判据注入；
    但"判据成立 → 关掉 tools 重发一次 → 仍然失败就如实抛"这段循环只此一份。

    返回的 tool_calls 对 Anthropic 格式恒为空 —— 它的工具调用不走这条协议。
    """
    toolkit = list(tools or [])
    use_tools = bool(toolkit) and fmt != "anthropic"
    attempts = 1 if fmt == "anthropic" else max(1, int(max_attempts))
    last: Optional[BaseException] = None
    for _attempt in range(attempts):
        try:
            if fmt == "anthropic":
                text = stream_anthropic(base_url, api_key, system, messages, model=model,
                                        on_delta=on_delta, on_retry=on_retry)
                return text, []
            # tools 模式强制非流式，理由见 openai_payload 的说明
            payload = openai_payload(model,
                                     [{"role": "system", "content": system}] + list(messages),
                                     stream=not use_tools,
                                     tools=toolkit if use_tools else None)
            return stream_openai(base_url, api_key, payload, on_delta=on_delta,
                                 on_retry=on_retry)
        except BaseException as exc:           # noqa: BLE001 —— 判据要看到原始失败
            err = resolve_error(exc, base_url)
            last = err
            if not use_tools or should_degrade is None or not should_degrade(err):
                raise
            use_tools = False                  # 降级：下一次不带 tools，恢复流式
    raise last if last is not None else RuntimeError("模型 API 调用失败")


def chat_once(base_url: str, api_key: str, model: str, fmt: str,
              system: str, messages: List[Dict], *,
              tools: Optional[List[Dict]] = None,
              on_retry: Optional[Callable[..., None]] = None,
              **kwargs) -> Dict[str, Any]:
    """一次性（非流式）调用：不需要流式渲染、只要那句回答时的形状。

    `agent_runner` 走这条 —— 它把模型整段输出交给执行层解析，不做流式显示。
    返回结构与 OpenAI 的响应体一致（Anthropic 格式也包成同一形状），
    调用方因此不必分情况读 `choices[0].message`。
    """
    if fmt == "anthropic":
        text = stream_anthropic(base_url, api_key, system, messages, model=model,
                                on_retry=on_retry)
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}
    payload = openai_payload(model,
                             [{"role": "system", "content": system}] + list(messages),
                             stream=False, tools=tools)
    return chat_complete(base_url, api_key, payload, on_retry=on_retry, **kwargs)


def stream_mock(text: str, on_delta: Optional[Callable[[str], None]] = None,
                delay: float = 0.02) -> str:
    """脚本化假模型的"流式"输出：逐行吐出，模拟打字机。

    放在这里而不是各前端各写一份：mock 是**两个前端都要走**的路径（CI 与离线演示
    全靠它），它一旦和真实路径分叉，"测试通过"就不再代表"能跑"。
    """
    import time
    if on_delta is None:
        for line in text.splitlines():
            print(line)
            time.sleep(delay)
        return text
    buf = ""
    for line in text.splitlines():
        buf += line + "\n"
        on_delta(buf)
        time.sleep(delay)
    return text
