#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_recovery —— 可逆性分类器（RG-04 第一阶段：只分类，不改裁决）

论文的主张是把安全的**对象**从"命令字符串"换成"被写的对象能不能重建"。ACE 今天回答不了
这个问题：判据是 `ace_execpolicy` 的黑名单 + 路径规则（`docs/SECURITY-AUDIT.md` 自己诊断过
"名单天生补不全"）。本模块给出**事实层**的分类：

    GIT         在版本控制里 → 可重建（`git ls-files` 说了算）
    SNAPSHOT    不在 git，但写前快照能覆盖（普通未跟踪文件；目标不存在时回滚即删除）
    REGENERABLE 依赖/构建产物类目录 → 删了能重新生成（**白名单**说了算）
    NEVER       不可重建或不该碰：`.git` / agent 状态 / 凭据 / 设备 / 工作区之外
    UNKNOWN     说不清 → 若开判据就该问人

**两条最要紧的口径**（都是踩过才写下来的）：

1. **"被 gitignore" ≠ "可再生"。** `docs/` 里被忽略的私有笔记、`secrets/`、用户自己的
   `*.local` 配置都是 gitignore 的，但删了不可重建。所以忽略状态一律判 **UNKNOWN**，
   只有**白名单**里的目录名（`node_modules` / `dist` / `__pycache__` / `target` …）才算 REGENERABLE。
2. **凭据与 agent 状态是 NEVER，不是 REGENERABLE。** `.guardian`（回滚安全网本身）、
   `.ace_sessions`（台账）、`.env` / `*.pem` 都**不在**快照里（被排除名单挡了），
   所以它们既不在 git、也没有快照 —— 删了就是没了。判据直接复用 `core.sensitive`，
   不再抄一份名单（"同一判据抄多份、漏改一份"正是本仓库反复栽的那个坑）。

第一阶段**只分类**：本模块不参与任何裁决，`assess()` 的 `would_release` 只是"若开判据会怎样"。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

GIT = "git"
SNAPSHOT = "snapshot"
REGENERABLE = "regenerable"
NEVER = "never"
UNKNOWN = "unknown"

# 删了能重新生成的目录名（**白名单**，不是"被忽略就算"）。加条目要给出"怎么重新生成"。
REGENERABLE_DIRNAMES = frozenset({
    "node_modules", "bower_components", "vendor_bundle",
    "dist", "build", "out", "target", "coverage", "htmlcov",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".venv", "venv", ".next", ".nuxt", ".parcel-cache", ".turbo",
})

# 版本库自身与 agent 自身状态：**快照排除它们**（`guardian.EXCLUDE_DIRS`），所以既没有
# git 那层"可重建"，也没有快照兜底 —— 删了就是没了。
NEVER_DIRNAMES = frozenset({
    ".git", ".hg", ".svn", ".guardian", ".ace_sessions",
    ".agent_flywheel", ".poc_reports",
})

# 设备/伪文件系统前缀：不是"文件"，谈不上重建
_DEVICE_PREFIXES = ("\\\\?\\", "\\\\.\\", "//./", "//?/", "/dev/", "/proc/", "/sys/")


def _is_device_path(p: str) -> bool:
    s = str(p).replace("\\", "/")
    low = s.lower()
    return (any(low.startswith(x.replace("\\", "/").lower()) for x in _DEVICE_PREFIXES)
            or low.startswith("//"))


def _is_drive_root(p: str) -> bool:
    """`C:\\` / `/` 这类根：删根不是"可逆性"问题，是 NEVER。"""
    s = str(p).replace("\\", "/").rstrip("/")
    return len(s) == 2 and s[1] == ":" or s == ""


class RecoveryClassifier:
    """按"世界的事实"分类。事实（git 状态）可注入，便于单测与复用。

    `runner` 只用于跑 git；给它 None 就退化成"没有 git 信息"（仍然能判 NEVER / REGENERABLE，
    其余落到 SNAPSHOT 并在 reason 里说明"无 git 信息"）。
    """

    def __init__(self, project_root: str, runner=None) -> None:
        self.root = Path(project_root).resolve()
        self._runner = runner
        self._tracked: Optional[Set[str]] = None
        self._repo: Optional[bool] = None

    # ---------- git 事实（一次问清，别按文件起进程） ----------

    def _git(self, args: List[str], stdin: str = "") -> Tuple[int, str]:
        if self._runner is not None:
            return self._runner(args, stdin)
        try:
            p = subprocess.run(["git", *args], cwd=str(self.root), input=stdin,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=20)
            return p.returncode, p.stdout
        except (OSError, subprocess.SubprocessError):
            return 1, ""

    def _ensure_facts(self) -> None:
        if self._tracked is not None:
            return
        rc, out = self._git(["rev-parse", "--is-inside-work-tree"])
        self._repo = (rc == 0 and out.strip() == "true")
        self._tracked = set()
        if not self._repo:
            return
        rc, out = self._git(["ls-files", "-z"])
        if rc == 0:
            for rel in out.split("\0"):
                if rel.strip():
                    self._tracked.add(rel.replace("\\", "/"))

    def _rel(self, path: Path) -> Optional[str]:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except (ValueError, OSError):
            return None

    # ---------- 判定 ----------

    def classify(self, path: str, exists: Optional[bool] = None) -> Tuple[str, str]:
        """→ (等级, 理由)。理由是要给人看的，别写成内部代号。"""
        p = Path(str(path))
        s = str(p)
        if _is_device_path(s) or _is_drive_root(s):
            return NEVER, "设备/伪文件系统或盘根，谈不上重建"
        abs_p = Path(p if p.is_absolute() else (self.root / p))
        try:
            abs_p = abs_p.resolve()
        except OSError:
            pass
        rel = self._rel(abs_p)
        if rel is None:
            return NEVER, "工作区之外：回滚快照盖不到它"
        parts = [x for x in rel.split("/") if x]
        # 版本库自身 / agent 自身状态：快照**排除**它们（`guardian.EXCLUDE_DIRS`），
        # 所以既不在 git 的"可重建"意义上、也没有快照兜底 —— 删了就是没了。
        if any(x in NEVER_DIRNAMES for x in parts):
            return NEVER, "版本库/agent 自身状态目录：不进程控制、也不进快照，删了无法重建"
        # 凭据文件：复用唯一来源的判据（core/sensitive），不再抄一份名单
        try:
            from core.sensitive import sensitive_target
            why = sensitive_target(str(abs_p))
        except Exception:      # noqa: BLE001 —— 判据不可用时保守：不当作可重建
            why = None
        if why:
            return NEVER, f"{why}（不在快照里、也不在 git 里，删了就是没了）"
        # 凭据文件是**另一个问题**：`sensitive_target` 答的是"工具能不能碰"（项目自己的 `.env`
        # 是正常开发对象，所以它放行），而这里要问的是"快照**有没有备份它**" ——
        # `is_credential_file` 才是那个判据（`snapshot()` 按它排除）。两个问题混用会得出
        # "删掉 .env 是可逆的"这种结论（实测就是这么错的）。
        try:
            from core.sensitive import is_credential_file
            _is_cred = bool(is_credential_file(str(abs_p)))
        except Exception:      # noqa: BLE001 —— 判据不可用时保守
            _is_cred = False
        if _is_cred:
            return NEVER, "凭据文件：快照按名单排除它（明文不进快照），删了无法重建"
        # 白名单目录名：目录自身或其祖先命中都算（"node_modules/x/y.js" 与 "node_modules"）
        check_parts = parts[:-1] if len(parts) > 1 else parts
        if any(x in REGENERABLE_DIRNAMES for x in check_parts):
            return REGENERABLE, "依赖/构建产物类目录（白名单），可重新生成"
        exists = abs_p.exists() if exists is None else exists
        self._ensure_facts()
        if rel in self._tracked:
            return GIT, "在版本控制内（git ls-files），可重建"
        if not exists:
            return SNAPSHOT, "目标不存在，回滚即删除（新建本身可逆）"
        if not self._repo:
            return SNAPSHOT, "无 git 信息；写前快照能覆盖它"
        rc, out = self._git(["check-ignore", "--", rel])
        if rc == 0 and out.strip():
            return UNKNOWN, ("被 gitignore 但**不在**可再生白名单里 —— 忽略不等于可再生，"
                             "删掉之后无法保证重建")
        return SNAPSHOT, "未跟踪但不在忽略名单：写前快照能覆盖它"

    def assess(self, targets: Iterable[str]) -> Dict[str, object]:
        """给一组目标做整体评估（**只测量**：`would_release` 表示"若开判据会不会放行"）。"""
        rows: List[Dict[str, str]] = []
        blocking: List[str] = []
        for t in targets or []:
            lvl, why = self.classify(str(t))
            rows.append({"target": str(t), "level": lvl, "reason": why})
            if lvl in (NEVER, UNKNOWN):
                blocking.append(str(t))
        return {
            "targets": rows,
            "blocking": blocking,
            "would_release": not blocking,
            "levels": sorted({r["level"] for r in rows}),
        }
