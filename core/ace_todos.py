#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_todos —— 逐项待办清单（纯逻辑）

为什么要有它：`goal`（持久目标 + 自动续跑）回答的是"这件事整体完成没有"，而 Claude Code
那种 todo 清单回答的是"这一趟要做哪几步、走到第几步了"。两者不是一回事：目标是**任务级**，
待办是**步骤级**，而且待办应该能在底栏一眼看到进度。

设计取舍：
- **纯函数**：所有操作都是 `(todos, ...) -> todos`，不改入参。这样可单测、可重放，
  也避免"某处顺手改了列表"这种没法追的 bug。
- **id 用递增整数**：模型/人都能在一条命令里引用（`/todo done 2`）。不用文本匹配当 id ——
  两件事文字一样就分不开了。
- 状态只有三档（pending / in_progress / done）。没有"取消"：不做的就删掉，
  留着"取消了"的条目只会让进度数字失真。
- 事件日志是事实源：写进 `.ace_sessions/*.jsonl`（`todo/add`、`todo/update`、`todo/clear`），
  恢复会话时按日志重放 —— 与消息历史同一套规矩。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["TodoItem", "TodoStore", "STATUSES", "add", "update", "remove", "clear_done",
           "clear_all", "summary", "render", "apply_event", "replay", "MAX_ITEMS",
           "MAX_TEXT"]

STATUSES = ("pending", "in_progress", "done")
MAX_ITEMS = 50          # 待办多到这个数就不是清单了，是噪音
MAX_TEXT = 200          # 单条上限（模型爱写小作文）


@dataclass(frozen=True)
class TodoItem:
    id: int
    text: str
    status: str = "pending"

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "status": self.status}


def _next_id(todos: List[TodoItem]) -> int:
    return max((t.id for t in todos), default=0) + 1


def add(todos: List[TodoItem], text: str) -> Tuple[List[TodoItem], Optional[TodoItem]]:
    """加一条。返回 (新列表, 新条目)；文本为空或超量时返回 (原列表, None)。"""
    clean = " ".join(str(text or "").split())[:MAX_TEXT]
    if not clean or len(todos) >= MAX_ITEMS:
        return list(todos), None
    item = TodoItem(id=_next_id(todos), text=clean)
    return list(todos) + [item], item


def update(todos: List[TodoItem], item_id: int, status: str,
           text: str = "") -> Tuple[List[TodoItem], Optional[TodoItem]]:
    """改状态（可顺带改文本）。id 不存在或状态非法时返回 (原列表, None)。"""
    st = str(status or "").strip().lower()
    if st not in STATUSES:
        return list(todos), None
    out: List[TodoItem] = []
    hit: Optional[TodoItem] = None
    for t in todos:
        if t.id == int(item_id):
            new_text = " ".join(str(text).split())[:MAX_TEXT] if text else t.text
            hit = replace(t, status=st, text=new_text)
            out.append(hit)
        else:
            out.append(t)
    return (out, hit) if hit is not None else (list(todos), None)


def remove(todos: List[TodoItem], item_id: int) -> Tuple[List[TodoItem], bool]:
    out = [t for t in todos if t.id != int(item_id)]
    return out, len(out) != len(todos)


def clear_done(todos: List[TodoItem]) -> List[TodoItem]:
    return [t for t in todos if t.status != "done"]


def clear_all(todos: List[TodoItem]) -> List[TodoItem]:
    return []


def summary(todos: List[TodoItem]) -> Dict[str, int]:
    """进度：{done, total, in_progress, pending}。底栏与断言共用这一个口径。"""
    done = sum(1 for t in todos if t.status == "done")
    prog = sum(1 for t in todos if t.status == "in_progress")
    return {"done": done, "total": len(todos), "in_progress": prog,
            "pending": len(todos) - done - prog}


def render(todos: List[TodoItem], width: int = 0) -> List[str]:
    """渲染成可打印的行（纯文本，不带颜色）。

    符号刻意用 ASCII+常见符号：`[ ]` 未开始、`[~]` 进行中、`[x]` 完成 ——
    旧 conhost 渲染 emoji 会变方框，而这个清单是要天天看的。
    """
    marks = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
    out: List[str] = []
    for t in todos:
        line = f"{marks.get(t.status, '[ ]')} {t.id}. {t.text}"
        if width and width > 8:
            from ui.ace_text import truncate_width
            line = truncate_width(line, width)
        out.append(line)
    return out


def apply_event(todos: List[TodoItem], ev: Dict[str, Any]) -> List[TodoItem]:
    """把一条 `todo/*` 事件重放到清单上（恢复会话时用）。

    未知动作一律忽略 —— 旧日志里可能有新版本才懂的动作，读不动跳过比整份日志失败好。
    """
    kind = str((ev or {}).get("kind") or "")
    if kind == "todo/add":
        new, _item = add(todos, str(ev.get("text") or ""))
        return new
    if kind == "todo/update":
        new, _hit = update(todos, int(ev.get("id") or 0), str(ev.get("status") or ""),
                           str(ev.get("text") or ""))
        return new
    if kind == "todo/remove":
        return remove(todos, int(ev.get("id") or 0))[0]
    if kind == "todo/clear":
        return clear_all(todos) if ev.get("all") else clear_done(todos)
    return list(todos)


def replay(events) -> List[TodoItem]:
    """从事件序列重建清单（append-only 日志 = 事实源）。"""
    todos: List[TodoItem] = []
    for ev in events or []:
        todos = apply_event(todos, ev if isinstance(ev, dict) else {})
    return todos


class TodoStore:
    """带日志的清单：每次改动都写一条 `todo/*` 事件，状态由日志重放而来。

    为什么不是"内存里存一份 + 顺手记日志"：两处状态一定会漂（崩溃后、resume 后）。
    这里只有一个真相源 —— 事件日志；`items` 是它的派生视图。
    """

    def __init__(self, log: Any = None, items: Optional[List[TodoItem]] = None) -> None:
        self.log = log
        self._items: List[TodoItem] = list(items or [])

    @classmethod
    def from_log(cls, log: Any) -> "TodoStore":
        """从会话日志重建（恢复会话时用）。日志读不动就当空清单，不抛。"""
        store = cls(log=log)
        try:
            events = [ev for ev in log.events() if str(ev.get("kind") or "").startswith("todo/")]
            store._items = replay(events)
        except Exception:  # noqa: BLE001 —— 清单读不出来不该让会话起不来
            store._items = []
        return store

    # ---- 读 ----
    @property
    def items(self) -> List[TodoItem]:
        return list(self._items)

    def summary(self) -> Dict[str, int]:
        return summary(self._items)

    def render(self, width: int = 0) -> List[str]:
        return render(self._items, width)

    # ---- 写（每次都落日志） ----
    def _record(self, kind: str, payload: Dict[str, Any]) -> None:
        if self.log is not None:
            try:
                self.log.append(kind, payload)
            except Exception:  # noqa: BLE001 —— 日志写不进去不该让清单操作失败
                pass

    def add(self, text: str) -> Optional[TodoItem]:
        self._items, item = add(self._items, text)
        if item is not None:
            self._record("todo/add", {"id": item.id, "text": item.text})
        return item

    def update(self, item_id: int, status: str,
               text: str = "") -> Optional[TodoItem]:
        self._items, hit = update(self._items, item_id, status, text)
        if hit is not None:
            self._record("todo/update", {"id": hit.id, "status": hit.status,
                                         "text": hit.text})
        return hit

    def remove(self, item_id: int) -> bool:
        self._items, ok = remove(self._items, item_id)
        if ok:
            self._record("todo/remove", {"id": int(item_id)})
        return ok

    def clear(self, all_items: bool = False) -> int:
        before = len(self._items)
        self._items = clear_all(self._items) if all_items else clear_done(self._items)
        removed = before - len(self._items)
        if removed:
            self._record("todo/clear", {"all": bool(all_items), "removed": removed})
        return removed

