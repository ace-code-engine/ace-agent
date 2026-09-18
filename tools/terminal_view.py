#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.terminal_view —— 只读终端查看（白名单命令，内建实现不经 shell）

R-02（v3.9）：从 tools/file_tools.py 原样切出——方法体逐字节未改，只搬运。
共享常量在 tools/file_common.py。
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict

from tools.base import (GIT_READONLY_SUBCOMMANDS, MAX_COMMAND_LENGTH,
                        READ_ONLY_COMMANDS, SHELL_META_RE, VERSION_ONLY_COMMANDS,
                        VERSION_SUBCOMMANDS, sensitive_target)
from tools.result import ExecutionResult


class TerminalView:
    def _escapes_project(self, token: str) -> bool:
        """这个命令行 token 是一个指向项目目录外的路径吗？不像路径、或在项目内则 False。"""
        if token.startswith("-"):
            return False
        if os.name == "nt" and self._NT_SWITCH_RE.match(token):
            return False
        expanded = os.path.expanduser(token)
        looks_like_path = (os.path.isabs(expanded)
                           or re.match(r"^[a-zA-Z]:[\\/]", expanded)
                           or ".." in Path(expanded).parts)
        if not looks_like_path:
            return False
        return self._confined(Path(expanded)) is None

    # Windows 开关（tree /F、where /R）会被 os.path.isabs 误判成绝对路径
    _NT_SWITCH_RE = re.compile(r"^/[A-Za-z]+$")
    # DOS 版 dir 的开关白名单。用白名单而不是 "^/字母+$"：后者会把 Linux 上的
    # `dir /tmp` 当成开关吃掉。单字母开关可带 :参数（/a:d、/o:-s）。
    _DOS_DIR_SWITCH_RE = re.compile(r"^/[bsaopwdlnqrtxc4](?:[:\-]\w+)?$", re.IGNORECASE)

    def _exec_terminal_view(self, params: Dict) -> ExecutionResult:

        """只读终端查看：白名单命令 + 无 shell 执行（修复：readonly 不再能执行任意命令）

        越界口径：读"目录名单"允许越界，读"文件内容"不允许。目录名单泄露的是文件名，
        文件内容泄露的是凭据本身，量级不同；ls 的越界是本文件 60-62 行记录的产品决定
        （"帮我看看桌面"不该因为工具选择而失败），cat 的越界只是漏检。
        """
        cmd = (params.get("command") or "").strip()
        if not cmd:
            # 小模型常漏 command 参数：缺省列出项目目录，避免 400 死循环
            cmd = "ls -la"
        if len(cmd) > MAX_COMMAND_LENGTH:
            return ExecutionResult(status="error", error_code="400", message="命令过长")
        if SHELL_META_RE.search(cmd):
            return ExecutionResult(status="error", error_code="403",
                                   message="terminal_view 检测到 shell 元字符，已拦截（只读工具禁止管道/重定向/连接符）")
        import shlex
        try:
            if os.name == "nt":
                # Windows 专用分词：双引号分组 + 保留反斜杠路径（shlex 会吃掉 \ 且在空格处断开）
                parts = self._split_cmd_windows(cmd)
            else:
                parts = shlex.split(cmd)
        except ValueError as e:
            return ExecutionResult(status="error", error_code="400", message=f"命令解析失败: {e}")
        if not parts:
            return ExecutionResult(status="error", error_code="400", message="命令为空")
        base = parts[0].lower()

        # —— 原生实现的只读内建命令（完全不经过 shell）——
        if base in ("ls", "dir"):
            # 忽略常见列表参数（ls 的 -l/-a/--all、dir 的 /b 等），支持 ~ 展开。
            # "/x" 是不是开关取决于命令方言、而不是当前系统：dir 是 DOS 风格，/b 是开关；
            # ls 是 POSIX 风格，"/" 开头就是绝对路径。按系统判会两头都错 ——
            # 之前按 "只要以 / 开头就丢掉" 处理，POSIX 上 ls /etc 会静默退化成 ls 项目根目录；
            # 改成按系统判又会让 Linux 上的 dir /b 把 /b 当成目录去列。
            dos_dialect = base == "dir"
            target_args = [p for p in parts[1:]
                           if not p.startswith("-")
                           and not (dos_dialect and self._DOS_DIR_SWITCH_RE.match(p))]

            target = target_args[0] if target_args else "."
            target = os.path.expanduser(target)
            # 支持通配符：ls *.py / dir /b *.py
            if any(ch in target for ch in "*?"):
                import glob
                pattern = target if os.path.isabs(target) else str(self.project_root / target)
                try:
                    matches = sorted(glob.glob(pattern))
                except Exception as e:
                    return ExecutionResult(status="error", error_code="500", message=str(e))
                lower_parts = [p.lower() for p in parts[1:]]
                bare = "/b" in lower_parts or "-1" in lower_parts
                if bare:
                    items = [os.path.basename(m) for m in matches]
                else:
                    items = [os.path.relpath(m, self.project_root)
                             if not os.path.isabs(target) else m
                             for m in matches]
                return ExecutionResult(status="success", data={
                    "stdout": "\n".join(items), "stderr": "", "returncode": 0})
            p = Path(target)
            if not p.is_absolute():
                p = self.project_root / p
            try:
                items = sorted(os.listdir(p))
            except FileNotFoundError:
                return ExecutionResult(status="error", error_code="404",
                                       message=f"目录不存在: {p}")
            except Exception as e:
                return ExecutionResult(status="error", error_code="500", message=str(e))
            return ExecutionResult(status="success", data={"stdout": "\n".join(items),
                                                           "stderr": "", "returncode": 0})
        if base == "pwd":
            return ExecutionResult(status="success", data={"stdout": str(self.project_root),
                                                           "stderr": "", "returncode": 0})
        if base in ("cat", "type"):
            if len(parts) < 2:
                return ExecutionResult(status="error", error_code="400", message="cat/type 需要文件参数")
            p = Path(os.path.expanduser(parts[1]))
            if not p.is_absolute():
                p = self.project_root / p
            # 读文件内容一律限项目内，与 grep / file_read 同口径。这里以前只查
            # sensitive_target，等于用黑名单当边界：名单外的项目外文件（别人的源码、
            # 浏览器 profile、随手记的 token）readonly 会话照样读得走。
            if self.confine_files and self._confined(p) is None:
                return ExecutionResult(status="error", error_code="403",
                                       message=f"路径越界：cat/type 只能读项目目录内的文件: {p}"
                                               "（列目录可用 ls）")
            # confine_files=False 时仍要挡住凭据文件，否则 ~/.ai_code.json 里的
            # 明文 API key 会被只读会话读走。
            reason = sensitive_target(p)
            if reason:
                return ExecutionResult(status="error", error_code="403",
                                       message=f"拒绝读取敏感文件（{reason}）: {p}")
            try:
                content = self._read_text_any(p)
            except FileNotFoundError:
                return ExecutionResult(status="error", error_code="404", message=f"文件不存在: {p}")
            except Exception as e:
                return ExecutionResult(status="error", error_code="500", message=str(e))
            return ExecutionResult(status="success", data={"stdout": content[:5000],
                                                           "stderr": "", "returncode": 0})
        if base == "echo":
            return ExecutionResult(status="success", data={"stdout": " ".join(parts[1:]),
                                                           "stderr": "", "returncode": 0})
        if base == "ver":
            import platform
            return ExecutionResult(status="success", data={"stdout": f"{platform.system()} {platform.release()}",
                                                           "stderr": "", "returncode": 0})
        if base in ("date", "time"):
            from datetime import datetime
            return ExecutionResult(status="success", data={"stdout": datetime.now().isoformat(),
                                                           "stderr": "", "returncode": 0})

        # —— 白名单外部命令 ——
        if base in VERSION_ONLY_COMMANDS:
            # 严格校验：只允许恰好两个 token 的版本查询，防止 "-v -c 代码" 注入
            if len(parts) != 2 or parts[1] not in VERSION_SUBCOMMANDS:
                return ExecutionResult(status="error", error_code="403",
                                       message=f"{base} 仅允许查询版本（--version / -V，且不允许附加任何参数）")
        elif base == "git":
            if len(parts) < 2 or parts[1].lower() not in GIT_READONLY_SUBCOMMANDS:
                return ExecutionResult(status="error", error_code="403",
                                       message=f"git 仅允许只读子命令: {sorted(GIT_READONLY_SUBCOMMANDS)}")
        elif base not in READ_ONLY_COMMANDS:
            return ExecutionResult(status="error", error_code="403",
                                   message=f"命令 '{base}' 不在 terminal_view 白名单中（只读工具）")
        # 白名单挡的是"命令名"，挡不住"参数指向哪"：tree C:\\Users 会递归列出主目录，
        # git diff --no-index A B 会直接打印两个项目外文件的内容。参数级检查在这里补。
        if self.confine_files:
            escaping = next((p for p in parts[1:] if self._escapes_project(p)), None)
            if escaping is not None:
                return ExecutionResult(status="error", error_code="403",
                                       message=f"路径越界：terminal_view 的路径参数必须在项目目录内: {escaping}")
        try:
            result = subprocess.run(parts, capture_output=True, text=True, timeout=30,
                                    cwd=str(self.project_root), shell=False,
                                    stdin=subprocess.DEVNULL)
            return ExecutionResult(status="success", data={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            })
        except subprocess.TimeoutExpired:
            return ExecutionResult(status="error", error_code="504", message="命令执行超时（30 秒）")
        except Exception as e:
            return ExecutionResult(status="error", error_code="500", message=str(e))

    # terminal_exec 的判定整体搬到了 ace_execpolicy（三值判定 + 纯函数），
    # 原来那张 _DANGEROUS_CMD_PATTERNS 表已被它的 _FORBIDDEN_RULES 覆盖并扩展
    # （多了卷影副本删除、bcdedit、账户/ACL 变更、certutil/bitsadmin/mshta 下载器、
    # 服务与 crontab 持久化、关闭 Defender/防火墙、注册表 hive 删除）。
    # 留在这里的只有 execpolicy 没有的那一层：敏感目标扫描，见 _evaluate_exec_command。
