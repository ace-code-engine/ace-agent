#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.git_ops —— git 工具族（ROADMAP WP-2 / G-01，照 Codewhale 命名）

8 个工具、两档权限：

- **只读档**（PERM_READ，免确认）：`git_status` / `git_diff` / `git_log` /
  `git_show` / `git_blame` —— 只跑"看"的子命令，输出确定性截断。
- **写档**（PERM_WRITE，`confirm=True` **逐次确认**）：`git_commit_plan` /
  `git_fetch` / `git_merge_tree`。

确认门与同前缀免确认的接线（**全部复用现有机制，不新造**）：

1. ToolSpec.confirm=True → 进 `CONFIRM_TOOLS` → execution_layer 的 5.0 逐次确认闸门
   （`_stage_permission`）在权限放行后**每次**返回 PERMISSION_REQUEST，人点头才跑；
2. 写类工具的参数是 `command`（完整 git 命令行）→ `confirm_subject` 把人看到的那条
   命令完整放进确认预览（H-28：不盲批）；
3. 同一条命令的 2-token 前缀由 `command_prefix` / `_prefix_auto_approved` 判定：
   人确认过 `git fetch origin` 之后 `git fetch upstream` 免再问；
   `BANNED_AUTO_PREFIXES` 对危险包装**永不**自动放行 —— 这里进一步把
   `git config` / `-c` / `-C` 整体拒掉，因此不存在"确认过 config 之后写路径被
   自动放行"这一说。
4. `git config` 的写路径不重开（SEC-06 已限定 --get/--list）：写类工具 argv[1]
   必须恰好是工具自己的子命令（commit / fetch / merge-tree），`git -c ...` 这类
   注入点在**结构上**不存在，token 校验里再显式拒绝 -c/--config/-C。

安全边界（本模块自己负责的那一层）：

- 一律 `shell=False` + argv 列表，`SHELL_META_RE` 先拦 shell 元字符；
- 写类工具的子命令之后按**选项正面清单**校验，清单外的 `-` 开头 token 一律 403；
- 路径参数（status/diff/log/show/blame 的 path）必须落在项目目录内（`_confined`），
  且不过 `.git` 内部目录、不过 `sensitive_target`（凭据/agent 状态目录与 `.git`
  内部协同判定 —— ROADMAP WP-2 风险项）；
- 输出确定性截断（stdout/stderr 各 20_000 字符上限 + 明确截断标记）。

错误码沿用 `tools/status.py` 既有口径：400 参数错 / 403 策略拒绝 / 404 不存在
（非 git 仓库、未知 revision、pathspec 不匹配）/ 500 git 失败 / 504 超时。
"""

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.base import MAX_COMMAND_LENGTH, SHELL_META_RE, sensitive_target
from tools.result import ExecutionResult

# git 子进程超时（秒）——与 terminal_view 的 30 秒同档
GIT_TIMEOUT = 30
# 每条输出流（stdout/stderr）的确定性截断上限（字符数）
MAX_GIT_OUTPUT = 20_000

# git_show / git_merge_tree 的 tree-ish 白名单形状：拒绝空白、shell 元字符与长串
_TREEISH_RE = re.compile(r"^[A-Za-z0-9_./@^~{}~\-]{1,64}$")

# 各写类工具的选项正面清单（子命令之后的 token）。价值选项（--depth 3）单独列出。
_GIT_FLAGS: Dict[str, Tuple[frozenset, frozenset, Tuple[str, ...]]] = {
    #                       flags（无值）                       value_flags     attached 前缀
    "commit": (frozenset({"--all", "-a", "--amend", "--no-verify", "--allow-empty",
                          "--no-edit", "--verbose", "-v", "--signoff", "-s"}),
               frozenset({"-m", "--message"}),
               ("--message", "-m")),
    "fetch": (frozenset({"--all", "--prune", "-p", "--tags", "-t", "--no-tags",
                         "--prune-tags", "--no-prune-tags", "--dry-run", "-n",
                         "--force", "-f", "--verbose", "-v", "--quiet", "-q"}),
              frozenset({"--depth"}),
              ("--depth",)),
    "merge-tree": (frozenset({"--write-tree", "--trivial-merge", "-m",
                              "--name-only", "--name-status", "-z"}),
                   frozenset(),
                   ()),
}


class GitOps:
    """git 工具族 handlers。所有方法由 tools.registry 的 ToolSpec.handler 引用。"""

    # ---------- 共享助手 ----------

    @staticmethod
    def _clip_output(text: str) -> str:
        """确定性截断：超过上限就截断并附带字数的标记（同一个输入永远同一个输出）。"""
        if len(text) <= MAX_GIT_OUTPUT:
            return text
        return (text[:MAX_GIT_OUTPUT]
                + f"\n… [ACE git 输出截断] 已省略 {len(text) - MAX_GIT_OUTPUT} 字符"
                  f"（单条输出流上限 {MAX_GIT_OUTPUT} 字符，可用 git_log max_count / "
                  f"git_show 指定 revision 缩小范围）")

    @staticmethod
    def _looks_missing(stderr: str) -> bool:
        """git 报错里"对象不存在"的那一类 → 404；其余 → 500。"""
        low = (stderr or "").lower()
        return any(m in low for m in (
            "not a git repository", "no such path", "did not match any files",
            "does not have any commits", "unknown revision", "bad revision",
            "ambiguous argument", "pathspec '", "unable to resolve",
        ))

    def _run_git(self, argv: List[str]) -> ExecutionResult:
        """跑一条 git argv（shell=False、cwd=项目根、超时、输出截断）。"""
        try:
            result = subprocess.run(argv, capture_output=True, timeout=GIT_TIMEOUT,
                                    cwd=str(self.project_root), shell=False,
                                    stdin=subprocess.DEVNULL,
                                    encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return ExecutionResult(status="error", error_code="504",
                                   message=f"git 命令执行超时（{GIT_TIMEOUT} 秒）: "
                                           f"{' '.join(argv[:6])}")
        except OSError as e:
            return ExecutionResult(status="error", error_code="500",
                                   message=f"无法启动 git: {e}")
        stdout = self._clip_output(result.stdout or "")
        stderr = self._clip_output(result.stderr or "")
        data = {"stdout": stdout, "stderr": stderr,
                "returncode": result.returncode, "command": " ".join(argv)}
        if result.returncode != 0:
            return ExecutionResult(
                status="error", error_code="404" if self._looks_missing(stderr) else "500",
                message=stderr.strip() or f"git 退出码 {result.returncode}", data=data)
        return ExecutionResult(status="success", data=data)

    def _repo_path_check(self, raw: Optional[str]) -> Optional[str]:
        """路径参数校验：返回拒绝原因，None = 放行。

        三层：项目内（_confined）→ .git 内部 → sensitive_target（凭据/agent 状态）。
        ROADMAP WP-2：'.git 是敏感目录，需与 sensitive.py 判定协同' —— 第三层就是
        sensitive_target，'.git' 内部目录是 git 工具特有的额外一层（git 会自己读
        .git，不必把内部文件当参数交给模型点名）。
        """
        if raw is None or not str(raw).strip():
            return None
        p = Path(os.path.expanduser(str(raw).strip()))
        if not p.is_absolute():
            p = self.project_root / p
        if self.confine_files and self._confined(p) is None:
            return f"路径越界：git 工具的路径参数必须在项目目录内: {raw}"
        if ".git" in {part.lower() for part in p.parts}:
            return ("拒绝直接访问 .git 内部目录（仓库状态由 git_status/git_diff/"
                    f"git_log 等工具给出）: {raw}")
        reason = sensitive_target(p)
        if reason:
            return f"敏感目标（{reason}）: {raw}"
        return None

    def _path_arg(self, params: Dict, name: str = "path") -> Tuple[str, Optional[ExecutionResult]]:
        """取 path 参数并校验；返回 (path, 失败结果)。"""
        raw = str(params.get(name) or "").strip()
        if not raw:
            return "", None
        reason = self._repo_path_check(raw)
        if reason:
            return "", ExecutionResult(status="error", error_code="403", message=reason)
        return raw, None

    # ---------- 只读档 ----------

    def _exec_git_status(self, params: Dict) -> ExecutionResult:
        path, err = self._path_arg(params)
        if err:
            return err
        argv = ["git", "status", "--porcelain=v1", "--branch"]
        if path:
            argv += ["--", path]
        res = self._run_git(argv)
        if res.status == "success":
            res.data["clean"] = not str(res.data.get("stdout") or "").strip()
            if res.data["clean"]:
                res.data["stdout"] = "（工作区干净：没有未提交的变更）"
        return res

    def _exec_git_diff(self, params: Dict) -> ExecutionResult:
        path, err = self._path_arg(params)
        if err:
            return err
        argv = ["git", "diff"]
        if bool(params.get("staged")):
            argv.append("--cached")
        if path:
            argv += ["--", path]
        return self._run_git(argv)

    def _exec_git_log(self, params: Dict) -> ExecutionResult:
        path, err = self._path_arg(params)
        if err:
            return err
        try:
            n = int(params.get("max_count") or 10)
        except (TypeError, ValueError):
            return ExecutionResult(status="error", error_code="400",
                                   message=f"max_count 必须是整数: {params.get('max_count')!r}")
        if not 1 <= n <= 50:
            return ExecutionResult(status="error", error_code="400",
                                   message="max_count 取值 1..50（默认 10）")
        argv = ["git", "log", f"-n{n}", "--oneline", "--decorate"]
        if path:
            argv += ["--", path]
        return self._run_git(argv)

    def _exec_git_show(self, params: Dict) -> ExecutionResult:
        path, err = self._path_arg(params)
        if err:
            return err
        rev = str(params.get("revision") or "HEAD").strip()
        if not _TREEISH_RE.match(rev):
            return ExecutionResult(status="error", error_code="400",
                                   message=f"revision 不是合法的 tree-ish（只允许字母数字与 "
                                           f"_./@^~{{}}-，最长 64）: {rev!r}")
        argv = ["git", "show", "--stat", "--patch", rev]
        if path:
            argv += ["--", path]
        return self._run_git(argv)

    def _exec_git_blame(self, params: Dict) -> ExecutionResult:
        path, err = self._path_arg(params)
        if err:
            return err
        if not path:
            return ExecutionResult(status="error", error_code="400",
                                   message="git_blame 需要 path 参数")
        return self._run_git(["git", "blame", "--", path])

    # ---------- 写档 ----------

    def _parse_write_command(self, tool_name: str,
                             params: Dict) -> Tuple[Optional[List[str]], Optional[ExecutionResult]]:
        """写类工具共用入口：取出并校验 command，返回 (parts, 失败结果)。"""
        cmd = str(params.get("command") or "").strip()
        if not cmd:
            return None, ExecutionResult(
                status="error", error_code="400",
                message=f"{tool_name} 需要 command 参数（完整 git 命令行，如 "
                        f'"git commit -m \\"feat: ...\\""）')
        if len(cmd) > MAX_COMMAND_LENGTH:
            return None, ExecutionResult(status="error", error_code="400",
                                         message="命令过长")
        if SHELL_META_RE.search(cmd):
            return None, ExecutionResult(
                status="error", error_code="403",
                message="检测到 shell 元字符，已拦截（git 写类工具禁止管道/重定向/连接符）")
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            return None, ExecutionResult(status="error", error_code="400",
                                         message=f"命令解析失败: {e}")
        if not parts:
            return None, ExecutionResult(status="error", error_code="400",
                                         message="命令为空")
        if parts[0].lower() not in ("git", "git.exe"):
            return None, ExecutionResult(
                status="error", error_code="403",
                message=f"{tool_name} 只接受 git 命令，收到: {parts[0]}")
        if len(parts) < 2:
            return None, ExecutionResult(status="error", error_code="400",
                                         message="git 命令缺少子命令")
        want = {"git_commit_plan": "commit", "git_fetch": "fetch",
                "git_merge_tree": "merge-tree"}[tool_name]
        sub = parts[1].lower()
        if sub != want:
            if sub == "config":
                return None, ExecutionResult(
                    status="error", error_code="403",
                    message="不接受 git config：SEC-06 已限定 git config 为 --get/--list，"
                            "本工具不重开写路径")
            return None, ExecutionResult(
                status="error", error_code="403",
                message=f"{tool_name} 只接受 git {want}，收到子命令: {parts[1]}")
        flags, value_flags, attached = _GIT_FLAGS[want]
        reason = self._reject_bad_tokens(parts, flags, value_flags, attached)
        if reason:
            return None, ExecutionResult(status="error", error_code="403", message=reason)
        return parts, None

    @staticmethod
    def _reject_bad_tokens(parts: List[str], flags: frozenset, value_flags: frozenset,
                           attached: Tuple[str, ...]) -> Optional[str]:
        """子命令之后的 token 按正面清单校验；返回拒绝原因，None = 放行。"""
        i = 2
        while i < len(parts):
            t = parts[i]
            # git config 写路径三重关闭：-c / --config / -C（含 = 与粘连形态）。
            if (t in ("-c", "--config", "-C")
                    or t.startswith("--config=")
                    or (t.startswith("-c") and len(t) > 2)
                    or (t.startswith("-C") and len(t) > 2)):
                return (f"git config 相关选项被拒（SEC-06 不重开写路径）: {t}")
            if t == "--":
                return None          # 之后是 pathspec，交给 git 自己解释
            if t.startswith("-"):
                if t in flags:
                    i += 1
                    continue
                if t in value_flags:
                    if i + 1 >= len(parts):
                        return f"选项 {t} 缺少值"
                    i += 2
                    continue
                if any((t.startswith(p + "=") or (len(t) > len(p) and t.startswith(p)))
                       for p in attached):
                    i += 1
                    continue
                return f"不接受的选项: {t}"
            i += 1
        return None

    @staticmethod
    def _commit_messages(parts: List[str]) -> List[str]:
        """从 commit 的 argv 里取出 -m/--message（含粘连形态）的全部消息段。"""
        msgs: List[str] = []
        i = 2
        while i < len(parts):
            t = parts[i]
            if t == "--":
                break
            if t in ("-m", "--message"):
                msgs.append(parts[i + 1])
                i += 2
            elif t.startswith("--message="):
                msgs.append(t[len("--message="):])
                i += 1
            elif t.startswith("-m") and len(t) > 2:
                msgs.append(t[2:])
                i += 1
            else:
                i += 1
        return msgs

    def _commit_plan(self) -> ExecutionResult:
        """提交计划三件套：状态 / 暂存 stat / 未暂存 stat（任一失败即中止）。"""
        probes = {
            "status": ["git", "status", "--porcelain=v1"],
            "staged_stat": ["git", "diff", "--cached", "--stat"],
            "unstaged_stat": ["git", "diff", "--stat"],
        }
        plan: Dict[str, str] = {}
        for key, argv in probes.items():
            res = self._run_git(argv)
            if res.status != "success":
                return res
            plan[key] = str(res.data.get("stdout") or "").strip()
        return ExecutionResult(status="success", data={"plan": plan})

    def _exec_git_commit_plan(self, params: Dict) -> ExecutionResult:
        """生成提交计划（status + diff stat + message 摘要），确认门放行后执行提交。

        两步都在**同一次调用**里，而 ToolSpec.confirm=True 保证整次调用只发生在
        人看过 command 预览并点头之后（"执行 commit 前必须过确认门"）。
        `dry_run=true` 时只出计划、不提交 —— 模型可以先预览再决定要不要真提交。
        """
        parts, err = self._parse_write_command("git_commit_plan", params)
        if err:
            return err
        messages = self._commit_messages(parts)
        if not messages:
            return ExecutionResult(
                status="error", error_code="400",
                message='git_commit_plan 的 command 需要 -m/--message 写提交信息，'
                        '如 {"command": "git commit -m \\"feat: ...\\""}')
        plan_res = self._commit_plan()
        if plan_res.status != "success":
            return plan_res
        data = {"plan": plan_res.data["plan"], "message": "\n\n".join(messages),
                "committed": False}
        if bool(params.get("dry_run")):
            data["stdout"] = ("（dry_run：仅生成提交计划，未执行 git commit）\n\n"
                              + plan_res.data["plan"]["status"])
            return ExecutionResult(status="success", data=data)
        add = self._run_git(["git", "add", "-A"])
        if add.status != "success":
            return add
        commit = self._run_git(["git", "commit"] + parts[2:])
        if commit.status != "success":
            if "nothing to commit" in str(commit.data.get("stderr") or "").lower():
                data["stdout"] = ("没有可提交的变更（工作区已是最新，"
                                  "add -A 之后 git commit 报 nothing to commit）")
                return ExecutionResult(status="success", data=data)
            return commit
        data["committed"] = True
        data["stdout"] = commit.data.get("stdout") or ""
        head = self._run_git(["git", "rev-parse", "--short", "HEAD"])
        if head.status == "success":
            data["commit_hash"] = str(head.data.get("stdout") or "").strip()
        return ExecutionResult(status="success", data=data)

    def _exec_git_fetch(self, params: Dict) -> ExecutionResult:
        """拉取远程（写 refs）。egress=True + confirm=True：目的地由人看过命令才放行。"""
        parts, err = self._parse_write_command("git_fetch", params)
        if err:
            return err
        return self._run_git(["git", "fetch"] + parts[2:])

    def _exec_git_merge_tree(self, params: Dict) -> ExecutionResult:
        """plumbing 级试合并：给出合并结果树（--write-tree）而不动工作区/分支。"""
        parts, err = self._parse_write_command("git_merge_tree", params)
        if err:
            return err
        treeish = [p for p in parts[2:] if p != "--" and not p.startswith("-")]
        if len(treeish) < 2:
            return ExecutionResult(
                status="error", error_code="400",
                message="git_merge_tree 需要两个 tree-ish 参数（两个分支/提交），如 "
                        '"git merge-tree --write-tree main feature"')
        if len(treeish) > 2:
            return ExecutionResult(
                status="error", error_code="400",
                message=f"git_merge_tree 只接受两个 tree-ish，收到: {treeish}")
        for t in treeish:
            if not _TREEISH_RE.match(t):
                return ExecutionResult(
                    status="error", error_code="400",
                    message=f"tree-ish 形状不合法（只允许字母数字与 _./@^~{{}}-，"
                            f"最长 64）: {t!r}")
        return self._run_git(["git", "merge-tree"] + parts[2:])
