#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「模型声称完成了操作」的措辞检测（H-20）。

**为什么单独一个模块**：这条判据有两个使用者 ——
`agent_runner`（编排层，供 CLI 打印提示）与 `execution_layer`（执行层，做真正的裁决）。
让 `execution_layer` 去 import `agent_runner` 会成环（`agent_runner` 本来就 import 执行层），
所以判据收在这里，两边都从这儿取。

**为什么执行层也要用它**：这道闸门此前**只在 CLI**（`ai_code.py`）里 ——
于是 headless / CI / SDK 完全没有防线：模型回一句"我已经帮你在桌面上创建了
example.py"、零工具调用，`run_conversation` 直接 `print` 然后 `return`，**退出码 0**。
而 headless 恰好是"没人在看"的那个模式。
"""
from __future__ import annotations

import re

__all__ = ["claims_completed_action", "PROMPT_UNVERIFIED_CLAIM"]

# 模型"声称已完成写操作"的措辞。只匹配完成态（已…/…了/created/has been），
# 不匹配"我将要创建"这类意图陈述，否则正常的计划说明会被误判。
#
# 2026-09 补课：原词典漏掉了**最常用的一批口语完成态** —— 实测 `改好了` /
# `已经改好了，你看一下` / `弄好了，文件在桌面上` / `我已经把那个 bug 修复了` /
# `帮你处理完了` 全部漏检（只认「创建/修改/删除」这类书面动词）。漏的方向恰好是
# 危险方向：零工具调用 + 这几句 = 幻觉被当成最终回复放行。现在补上
# 改/弄/做/修复/处理/清理/搞定/删/建 这组，并让"…好了/完了/掉了/干净了"独立成一条
# （不要求前面有"已"，因为 `改好了` 这种口语本来就不带）。
_CLAIM_VERBS = (r"(?:创建|建立|新建|写入|保存|生成|修改|更新|删除|移动|重命名|执行"
                r"|改|弄|做|修复|处理|清理|搞定|删|建)")
_CLAIM_DONE_RE = re.compile(
    r"已(?:经)?(?:为你|帮你|在)?[^。\n]{0,12}?" + _CLAIM_VERBS
    + r"|" + _CLAIM_VERBS + r"(?:好|完|掉|干净)(?:了)?"
    + r"|搞定(?:了)?"
    r"|文件已(?:经)?(?:成功)?(?:创建|保存|生成|写入|修改|删除|改)"
    r"|(?:created|wrote|saved|generated|deleted|updated|executed|fixed|patched)"
      r"\s+(?:the\s+)?(?:file|it|that)"
    r"|file\s+(?:has\s+been|was)\s+(?:created|written|saved|updated|deleted)"
    r"|I(?:'ve|\s+have)\s+(?:created|written|saved|updated|deleted|executed|fixed)",
    re.IGNORECASE)


def claims_completed_action(content: str) -> bool:
    """模型是否在"没有调用任何工具"的前提下声称自己完成了文件/命令操作。

    这是本项目见过的最有害的失败模式：小模型（或被端点吞掉了 tool_calls 的情况）
    回一句"我已经帮你在桌面创建了 example.py"，`final_reply_protocol` 无条件把它
    包成模式 B，执行层判 FINAL_REPLY，CLI 打绿色的"✓ 完成（1 轮）"然后退出 ——
    用户以为成功了，桌面上什么都没有。零工具调用 + 完成态措辞 = 必须拦。

    只做措辞检测、不做语义判断：宁可偶尔多问模型一轮，也不能把幻觉当成功。
    """
    return bool(_CLAIM_DONE_RE.search(content or ""))


# 让模型自己改一次的指令（承认没做 / 或者真去做，都行 —— 但别说谎）。
# 原文照搬自 `agent_runner`（那是被真机验证过的一版），不要在这里自行缩写。
PROMPT_UNVERIFIED_CLAIM = (
    "停。你刚才声称已经完成了文件/命令操作，但这一轮你没有调用任何工具，"
    "所以系统里什么都没有发生——文件不存在，命令没执行。\n"
    "二选一：\n"
    "1) 如果确实要做，现在就调用对应工具真正执行（新建文件用 file_write，"
    "改已有文件用 str_replace，跑命令用 terminal_exec）；\n"
    "2) 如果不需要执行，重写你的回答，去掉「已创建 / 已保存 / 已执行」这类说法，"
    "改成如实描述。\n"
    "不要再向用户索要确认——权限审批由执行层负责，不是你的职责。")
