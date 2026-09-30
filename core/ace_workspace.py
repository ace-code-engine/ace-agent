#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.ace_workspace —— WP-4 工作区四层（Task → Workspace → Session → ExecutionProcess）

纯逻辑、可单测：本模块**不碰 subprocess、不做文件 I/O、不持有 guardian 引用** ——
worktree 的 git 操作在 `tools/git_ops.py`（`worktree_add` / `worktree_remove` /
`worktree_list`），持久化与 UI/CLI 接线留给后续切片（本切片 = 数据模型 + 回滚纪律 +
allowedRoots 注册表，见 C5 卡《WP-4-SNAPSHOT-SEMANTICS》）。

回滚纪律（C5 卡三条规则，本模块是它们的**数据面**）：

1. **回滚只有一个入口（guardian 快照）**：本模块**没有**任何"还原文件"的方法；
   删 worktree = 状态置位 `worktree_deleted`（= 这个工作区不再用了），**不是**回滚 ——
   两个动词、两条状态、两句文案，语义与 `/undo` 严格分开。
2. **worktree 只做隔离，不做回滚**：`allowedRoots` 的**唯一来源**是本注册表
   （注册过的 worktree 根 + 主根）；删除即除名。它是 `confine_files` / `sensitive.py`
   的**上位约束** —— 先问"这个根注册过吗"，再问"路径越界吗"，不是第二套越界判定。
3. **切换 worktree ≠ 切快照基**：`snapshot_base(ws)` 返回该工作区的文件系统根
   （worktree 根，必在 allowedRoots 之内）；worktree 已删则回落主根并**如实声明**。

无 worktree 支持（非 git / 四层未启用 / git 版本不支持 worktree）：
注册表为空 → `authorize()` 返回 `decision="fallback"` 且**带原因**（如实声明，
HL-03②），调用方按**当前单工作区语义**处理 —— 不静默。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RunReason(str, Enum):
    """`ExecutionProcess.run_reason` 枚举（照 vibe-kanban 四层，闭集）。"""
    SETUP_SCRIPT = "SetupScript"
    CLEANUP_SCRIPT = "CleanupScript"
    ARCHIVE_SCRIPT = "ArchiveScript"
    CODING_AGENT = "CodingAgent"
    DEV_SERVER = "DevServer"


# ExecutionProcess 的进程状态（人可读闭集）：
#   running = 还在跑；exited = 已结束（exit_code 随之落定）。
PROCESS_RUNNING = "running"
PROCESS_EXITED = "exited"


@dataclass
class ExecutionProcess:
    """一行进程记录。每行工作区状态取**最新进程**（见 `WorkspaceStore.latest_process`，
    等价于 vibe-kanban 的 LatestProcessInfo）。

    dropped：进程失联/被丢弃（留记录、不当作"还在跑"）——它**仍是**最新进程，
    只是带着这个标记。
    """
    id: str
    workspace_id: str
    run_reason: RunReason
    status: str = PROCESS_RUNNING
    exit_code: Optional[int] = None
    dropped: bool = False
    started_at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict:
        return {
            "id": self.id, "workspace_id": self.workspace_id,
            "run_reason": self.run_reason.value, "status": self.status,
            "exit_code": self.exit_code, "dropped": self.dropped,
            "started_at": self.started_at,
        }


@dataclass
class Session:
    """四层第三层：一次会话挂在一个 workspace 下。"""
    id: str
    workspace_id: str
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict:
        return {"id": self.id, "workspace_id": self.workspace_id,
                "created_at": self.created_at}


@dataclass
class Workspace:
    """四层第二层：一个 workspace = 一个 worktree + 一个 branch。

    四字段（照 vibe-kanban）：
    - archived：归档（不再活跃，但保留历史）；
    - pinned：置顶（列表里不许被自动清理/排走）；
    - name：首条 prompt 自动命名（见 name_from_prompt；空 = 未命名）；
    - worktree_deleted：worktree 已删（= 不再用；**不是回滚**，见模块 docstring）。
    """
    id: str
    task_id: str
    branch: str = ""
    worktree_path: Optional[Path] = None   # None = 主工作区（没有单独 worktree）
    archived: bool = False
    pinned: bool = False
    name: str = ""
    worktree_deleted: bool = False
    created_at: float = field(default_factory=time.time)

    @property
    def root(self) -> Optional[Path]:
        """这个工作区对应的文件系统根（注册进 allowedRoots 的那个）。

        worktree 已删 → None（根已除名，快照基回落主根，见 snapshot_base）。
        """
        if self.worktree_path is None or self.worktree_deleted:
            return None
        return self.worktree_path

    def as_dict(self) -> Dict:
        return {
            "id": self.id, "task_id": self.task_id, "branch": self.branch,
            "worktree_path": str(self.worktree_path) if self.worktree_path else None,
            "archived": self.archived, "pinned": self.pinned, "name": self.name,
            "worktree_deleted": self.worktree_deleted, "created_at": self.created_at,
        }


@dataclass
class Task:
    """四层第一层：一次任务拥有 1..n 个 workspace。"""
    id: str
    title: str = ""
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict:
        return {"id": self.id, "title": self.title, "created_at": self.created_at}


def name_from_prompt(prompt: str, max_len: int = 24) -> str:
    """首条 prompt 自动命名：折行压空白、超长截断（确定性，同一 prompt 同一名字）。"""
    text = " ".join(str(prompt or "").split())
    if not text:
        return ""
    return text[:max_len].rstrip()


# authorize() 的三态判定（allowedRoots 上位约束，不是第二套越界判定）：
AUTH_ALLOWED = "allowed"    # 路径在某注册根之内 → 放行（接下来才是 confine_files/sensitive）
AUTH_DENIED = "denied"      # 路径不在任何注册根之内 → **拒绝**（如实声明）
AUTH_FALLBACK = "fallback"  # 注册表为空（非 git/四层未启用/worktree 全删）→ 单工作区语义（如实声明）


class WorkspaceStore:
    """四层注册表 + allowedRoots 的唯一来源。纯内存、纯状态、零文件操作。

    primary_root：主工作区根（四层启用时由接线方注册；None = 只有 worktree 根在册）。
    注意：不传 primary_root 且没有任何 worktree 时，allowed_roots() 为空 ——
    authorize() 会落 fallback 并**如实声明**，绝不会静默放行任意路径。
    """

    def __init__(self, primary_root: "Optional[str | Path]" = None):
        self.primary_root: Optional[Path] = (
            Path(primary_root).resolve() if primary_root else None)
        self.tasks: Dict[str, Task] = {}
        self.workspaces: Dict[str, Workspace] = {}
        self.sessions: Dict[str, Session] = {}
        self.processes: List[ExecutionProcess] = []

    # ---------- 四层构造 ----------

    def new_task(self, title: str = "") -> Task:
        task = Task(id=_new_id("task"), title=title)
        self.tasks[task.id] = task
        return task

    def add_workspace(self, task_id: str, branch: str = "",
                      worktree_path: "Optional[str | Path]" = None,
                      name: str = "", pinned: bool = False,
                      archived: bool = False) -> Workspace:
        ws = Workspace(
            id=_new_id("ws"), task_id=task_id, branch=branch,
            worktree_path=Path(worktree_path).resolve() if worktree_path else None,
            name=name, pinned=pinned, archived=archived)
        self.workspaces[ws.id] = ws
        return ws

    def add_session(self, workspace_id: str) -> Session:
        s = Session(id=_new_id("sess"), workspace_id=workspace_id)
        self.sessions[s.id] = s
        return s

    def record_process(self, workspace_id: str, run_reason: RunReason,
                       status: str = PROCESS_RUNNING,
                       exit_code: Optional[int] = None,
                       dropped: bool = False,
                       started_at: Optional[float] = None) -> ExecutionProcess:
        """登记一条进程记录；返回该记录（id 生成、started_at 可注入以便测试确定性）。"""
        p = ExecutionProcess(
            id=_new_id("proc"), workspace_id=workspace_id, run_reason=run_reason,
            status=status, exit_code=exit_code, dropped=dropped,
            started_at=started_at if started_at is not None else time.time())
        self.processes.append(p)
        return p

    def finish_process(self, process_id: str, exit_code: int) -> Optional[ExecutionProcess]:
        """进程结束：status=exited、exit_code 落定；找不到返回 None。"""
        for p in self.processes:
            if p.id == process_id:
                p.status = PROCESS_EXITED
                p.exit_code = exit_code
                return p
        return None

    def latest_process(self, workspace_id: str) -> Optional[ExecutionProcess]:
        """每行工作区状态取**最新进程**（LatestProcessInfo 语义）。

        最新 = started_at 最大；并列取后登记的那条（注册表按登记顺序保存）。
        dropped 的进程**仍是**最新进程 —— 它是"最近发生的那件事"，只是带着失联标记。
        """
        cands = [(i, p) for i, p in enumerate(self.processes)
                 if p.workspace_id == workspace_id]
        if not cands:
            return None
        return max(cands, key=lambda ip: (ip[1].started_at, ip[0]))[1]

    # ---------- allowedRoots（唯一来源 + 上位约束） ----------

    def allowed_roots(self) -> frozenset:
        """注册过的 worktree 根（未删）+ 主根（若注册）。allowedRoots 唯一来源。"""
        roots = set()
        if self.primary_root is not None:
            roots.add(self.primary_root)
        for ws in self.workspaces.values():
            if ws.root is not None:
                roots.add(ws.root)
        return frozenset(roots)

    def authorize(self, path: "str | Path") -> Dict:
        """allowedRoots **上位约束**：先问"这个根注册过吗"（不替代 confine_files/sensitive）。

        返回 {"decision": allowed|denied|fallback, "root": 命中根或 None, "reason": 声明文本}。
        - allowed：路径在某个注册根之内（后续判定照旧：confine_files / sensitive.py）；
        - denied：注册表非空但路径不在任何注册根之内 → **拒绝**，reason 如实说明；
        - fallback：注册表为空（非 git / 四层未启用 / worktree 全删）→ 单工作区语义，
          reason 如实声明（HL-03②，不静默）。
        """
        roots = self.allowed_roots()
        if not roots:
            return {
                "decision": AUTH_FALLBACK, "root": None,
                "reason": ("未启用工作区四层：没有注册过的 worktree 根"
                           "（非 git 仓库 / 四层未开启 / worktree 已全删），"
                           "按当前单工作区语义处理"),
            }
        try:
            rp = Path(str(path)).resolve(strict=False)
        except OSError:
            rp = Path(str(path))
        # 最长的注册根优先：嵌套 worktree 时命中更深的那一个。
        for root in sorted(roots, key=lambda r: len(str(r)), reverse=True):
            try:
                rp.relative_to(root)
            except ValueError:
                continue
            return {"decision": AUTH_ALLOWED, "root": root, "reason": ""}
        return {
            "decision": AUTH_DENIED, "root": None,
            "reason": (f"路径不在任何注册过的 worktree 根之内（allowedRoots 上位约束，"
                       f"先于 confine_files/sensitive 判定）: {rp}"),
        }

    # ---------- worktree 生命周期（只动注册表，不碰文件） ----------

    def mark_worktree_deleted(self, workspace_id: str) -> Tuple[bool, str]:
        """删 worktree = 状态置位（这个工作区不再用了），**不是回滚**。

        只动注册表：worktree_deleted=True、archived=True、根从 allowedRoots 除名；
        不还原任何文件、不碰 git、不删进程/会话记录。
        真正的 `git worktree remove` 在 tools/git_ops.worktree_remove（同样不做还原）。
        返回 (是否发生变更, 声明文本)。
        """
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            return False, f"没有注册过 workspace {workspace_id}"
        if ws.worktree_deleted:
            return False, f"workspace {workspace_id} 的 worktree 已标记删除"
        ws.worktree_deleted = True
        ws.archived = True
        return True, (f"workspace {workspace_id} 的 worktree 已除名"
                      f"（allowedRoots 不再含其根）；这只表示'该工作区不再使用'，"
                      f"**不触发任何文件还原** —— 回滚只有 /undo 那一条路（guardian 快照）")

    def snapshot_base(self, workspace_id: str) -> Tuple[Optional[Path], str]:
        """切到该工作区时快照基应指向的根（C5 规则 3：切 worktree 快照基跟着换）。

        返回 (root, note)：
        - worktree 未删：root = 该 worktree 根（必在 allowedRoots 之内），note 为空；
        - worktree 已删 / 未注册：root 回落主根（若有），note **如实声明**。
        """
        ws = self.workspaces.get(workspace_id)
        if ws is not None and ws.root is not None:
            return ws.root, ""
        fallback = self.primary_root
        if fallback is not None:
            return fallback, ("该工作区的 worktree 已删/未注册，快照基回落主根"
                              "（guardian 快照仍只对当前根生效，不跨 worktree 串）")
        return None, "没有可用的快照基：无主根、worktree 已删/未注册"
