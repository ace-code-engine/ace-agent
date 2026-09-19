#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_model —— 两个前端共用的模型层纯逻辑（R-03 的安全半边）

为什么只抽"纯逻辑"而不是把两个客户端合成一个：`ai_code.ModelClient` 是
**流式 + requests + 重试 + Anthropic 兼容**的交互式客户端，`agent_runner.ModelProvider`
是 urllib 一次性调用；两者的输出契约也不同（前者边流边渲染，后者只认
`🤖 Agent:` 那一行）。把两条路径合成一条，等于重写无头前端的行为，而现有测试
只能覆盖 mock 路径——那属于"改行为"，不是"重构"，得先在真实模型上跑通再说。

所以这里只放**两边确实重复、且是纯函数**的部分：

  · `trim_history(messages, max_history)` —— 历史裁剪（两边各写过一份，语义还不一致）
  · `error_hint(exc, translate)` —— HTTP 错误码 → 排查提示（原先只在 ai_code 里有）

`translate` 由调用方注入 i18n 的 `t`：这个模块不认识界面语言，也不 import 项目内
任何模块（与 ace_isolation 同一取态，谁都能安全地引它）。
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

# —— 图片输入（多模态）：只做**纯逻辑**（读文件 + 组装 payload），不发请求 ——
# 只认这几种格式：各家 API 支持的就是这些，别的传过去只会报错。
IMAGE_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".webp": "image/webp", ".gif": "image/gif"}
MAX_IMAGE_BYTES = 4_000_000        # 单张上限：再大就该先压缩，而不是把请求撑爆
MAX_IMAGES_PER_TURN = 3


def guess_media_type(path: str) -> Optional[str]:
    """按扩展名判断 MIME；不支持的类型返回 None（调用方据此说清原因）。"""
    import os
    ext = os.path.splitext(str(path or ""))[1].lower()
    return IMAGE_MEDIA_TYPES.get(ext)


def build_image_block(path: str, api_format: str = "openai"
                      ) -> Tuple[Optional[Dict[str, Any]], str]:
    """读一张图 → 该接口格式的 content block。返回 (block, 错误说明)。

    - OpenAI 兼容：`{"type":"image_url","image_url":{"url":"data:<mime>;base64,…"}}`
    - Anthropic：`{"type":"image","source":{"type":"base64","media_type":…,"data":…}}`

    超限/格式不对/读不出来都**如实返回原因**，不静默跳过 —— 用户以为图发出去了、
    其实没发，是这类功能最容易出的错。
    """
    import base64
    import os
    p = str(path or "").strip()
    if not p:
        return None, "路径为空"
    mime = guess_media_type(p)
    if not mime:
        return None, f"不支持的图片格式（只支持 {'/'.join(sorted(set(IMAGE_MEDIA_TYPES.values())))}）"
    if not os.path.isfile(p):
        return None, f"文件不存在: {p}"
    try:
        size = os.path.getsize(p)
        if size > MAX_IMAGE_BYTES:
            return None, f"图片过大（{size} 字节 > {MAX_IMAGE_BYTES}）"
        with open(p, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
    except OSError as e:
        return None, f"读取失败: {e}"
    if str(api_format).lower() == "anthropic":
        return {"type": "image",
                "source": {"type": "base64", "media_type": mime, "data": data}}, ""
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}, ""


def compose_user_message(text: str, images: Optional[List[Dict[str, Any]]] = None,
                         api_format: str = "openai") -> Dict[str, Any]:
    """把"文本 + 图片块"组装成一条 user 消息。

    没有图片时 content 就是字符串（保持与旧行为逐字节一致 —— 各家对纯字符串的
    处理最稳，改成数组反而可能踩兼容性）。
    """
    blocks = [b for b in (images or []) if isinstance(b, dict)]
    if not blocks:
        return {"role": "user", "content": str(text or "")}
    parts: List[Dict[str, Any]] = []
    if str(text or "").strip():
        parts.append({"type": "text", "text": str(text)})
    parts.extend(blocks)
    return {"role": "user", "content": parts}


def trim_history(messages: List[Dict], max_history: int) -> List[Dict]:
    """限制对话历史长度，防止本地小模型上下文溢出（保留最近 N 轮 = 2N 条消息）。

    口径统一在**消息条数**上：`max_history` 按"轮"计（一问一答 = 2 条）。
    `max_history <= 0` 表示不裁剪（用户显式关掉）。
    """
    if max_history <= 0:
        return messages
    max_msgs = max_history * 2
    return messages[-max_msgs:] if len(messages) > max_msgs else messages


def error_hint(exc: Exception, translate: Callable[[str], str]) -> str:
    """按 HTTP 错误码给出排查提示；没有可说的就返回空串。

    `translate` 传 i18n 的 `t`（键：`model_err_401/403/404/429/5xx`）。
    """
    code: Optional[int] = getattr(getattr(exc, "response", None), "status_code", None)
    if code == 401:
        return translate("model_err_401")
    if code == 403:
        return translate("model_err_403")
    if code == 404:
        return translate("model_err_404")
    if code == 429:
        return translate("model_err_429")
    if code and 500 <= code < 600:
        return translate("model_err_5xx")
    return ""


def messages_envelope(messages: List[Dict[str, Any]]) -> Dict[str, int]:
    """给会话日志用的消息摘要（条数 + 字符数）——两边都往日志里记这个。"""
    return {"count": len(messages),
            "chars": sum(len(str(m.get("content", ""))) for m in messages)}
