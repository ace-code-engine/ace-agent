#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""敏感目标判定：**唯一来源**（H-11）。

## 两个不同的问题，故意放在一起

| | 问题 | 谁在用 | 入口 |
|---|---|---|---|
| ① | agent **能不能碰**这个路径？ | 文件工具 / 只读终端 / 命令执行 | `sensitive_target()` |
| ② | 这个文件的**内容是不是秘密**？ | `core/guardian`（决定要不要把它**明文复制**进快照） | `is_credential_file()` |

它们**故意不同**，而最大的那个差集就是 `.env`：项目内的 `.env` 是正常开发对象
（"帮我建个 .env"必须能用），所以 ① 不拦它；但快照是明文副本，② 必须排除它。

## 为什么必须同源

此前这两份名单分散在两个模块里各改各的，实测**双向漂移**：

- **方向 A（安全）**：25 个名字 —— `.npmrc` `.pypirc` `.pgpass` `.git-credentials`
  `.netrc` `.htpasswd` `.terraformrc` `.dockercfg` `.my.cnf` `.agent_cli.json` … ——
  对 ① 是凭据，② 却会**明文复制进 `.guardian/snapshots/**/files/`**。
  而 `guardian.py` 自己的注释写着"**绝不能**把用户凭据再复制一份进 `.guardian`"
  （SEC-04，且 BACKLOG 里记的是 ✅ 已完成）。
- **方向 B（可用性）**：`.claude.json` / `client.ovpn` / `key.asc` ② 不快照、
  ① 却视为普通文件 ⇒ 这些写入**不可回滚**。

两份名单各改一半，就成了两个都不完整的名单。现在同源，差异只剩本文件里显式写出的
那一条 —— 它从"没人知道的漂移"变成"写在这里的设计决定"。

## 仍不是完备边界

这是"已知高价值目标"清单，不是安全边界（真正的隔离仍需容器/低权限账户）。
判据方向仍是"列举禁止什么"，而列举天生补不全 —— 这一点见本卡 §0 与 H-06/H-11。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.canonical import canonical_text

__all__ = [
    "CREDENTIAL_BASENAMES", "CREDENTIAL_SUFFIXES", "PRIVATE_KEY_PREFIXES",
    "TOOL_BLOCKED_BASENAMES", "AGENT_STATE_DIRNAMES", "AGENT_STATE_FILENAMES",
    "SENSITIVE_DIRNAMES", "SENSITIVE_DIR_PREFIXES", "STARTUP_FRAGMENTS",
    "is_credential_file", "sensitive_target",
]

# ---------------------------------------------------------------- ② 凭据名单

# 明文凭据 / 密钥材料 / 持久化入口（两份旧名单的**并集**）。
# 加一个名字要同时想清楚它对 ① 和 ② 的影响 —— 不想清楚就会漂移。
CREDENTIAL_BASENAMES = frozenset({
    # 本工具与同类的凭据配置
    ".ai_code.json", ".agent_cli.json", ".claude.json",
    # 各类工具链的明文 token 存放点：不存在"agent 需要改它"的正常场景
    ".netrc", "_netrc", ".git-credentials", ".npmrc", ".pypirc", ".dockercfg",
    ".pgpass", ".my.cnf", ".htpasswd", ".terraformrc",
    # 项目内的 .env（**只在 ② 生效**，见下面那个显式差集）
    ".env",
    # shell 启动脚本：写它们等于装持久化后门
    ".bashrc", ".bash_profile", ".zshrc", ".zprofile", ".profile",
    ".zshenv", ".zlogin", ".bash_aliases", ".bash_logout",
    # 系统凭据与会话
    "authorized_keys", "known_hosts", "credentials", "shadow", "sudoers",
})
CREDENTIAL_SUFFIXES = (".pem", ".key", ".ppk", ".p12", ".pfx", ".keystore",
                       ".jks", ".ovpn", ".asc")
PRIVATE_KEY_PREFIXES = ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")

# ① 与 ② 的**唯一显式差集**：agent 可以碰、但快照不收。
# `.env` 是项目内的正常开发对象（"帮我建个 .env"必须能用），拦死它会把正常请求也拒掉。
# 代价：写 `.env` **不可回滚**（它不进快照）。这一点是刻意的取舍，不是漏项 ——
# 若要收紧，正确做法是"写凭据形态的目标时额外确认"，而不是把它塞回 ① 里一拒了之。
TOOL_BLOCKED_BASENAMES = CREDENTIAL_BASENAMES - {".env"}

# ---------------------------------------------------------------- ① 路径判定

SENSITIVE_DIRNAMES = {
    ".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".config/gcloud",
    # 用户级自启动 / 定时任务：写这里等于装持久化后门
    ".config/autostart", ".config/systemd", ".local/share/systemd",
}
# 目录整体不可写（系统 / 自启动 / 定时任务）
SENSITIVE_DIR_PREFIXES = (
    "c:/windows", "c:/program files", "c:/program files (x86)", "c:/programdata",
    "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/boot", "/sys", "/proc",
    "/var/spool/cron",
)
STARTUP_FRAGMENTS = ("start menu/programs/startup", "currentversion/run")

# Agent 自身的安全状态目录：回滚快照存在项目目录内，而项目目录正是 agent 可写的范围。
# 不挡这里，agent 改一行 `.guardian/snapshots/<id>/meta.json` 就能让 verify_snapshot
# 失败，熔断回滚静默变成空操作 —— 安全网被它要防的东西拆了。
# 审计与运行状态同理（SEC-017）：会话事件日志、飞轮样本、POC 报告都是"事后取证"用的，
# 让被审计方自己可写，等于没有记录。挡住文件工具这一层；`terminal_exec` 仍能碰它们，
# 但它每次都过人，且那一步本身就是可被看见的动作。
AGENT_STATE_DIRNAMES = {".guardian", ".ace_sessions", ".agent_flywheel", ".poc_reports"}
# 同上，但是文件形态（目标状态 / 记忆）：改它等于伪造"用户偏好"或"任务已完成"
AGENT_STATE_FILENAMES = {".ace_goals.json", ".agent_memory.json"}


# ---------------------------------------------------------------- ② 判定

def is_credential_file(path: "Path | str") -> bool:
    """这个文件的**内容**是不是秘密（要不要排除在明文快照之外）。

    只看**文件名**：凭据的判别依据是命名约定，与路径无关（`a/.env` 与 `b/.env`
    同样是凭据）。`.env.local` 这类 `*.env.*` 变体也算。
    """
    try:
        name = Path(str(path)).name.lower()
    except (TypeError, ValueError):
        return False
    return (name in CREDENTIAL_BASENAMES
            or name.startswith(".env.")
            or name.startswith(PRIVATE_KEY_PREFIXES)
            or name.endswith(CREDENTIAL_SUFFIXES))


# ---------------------------------------------------------------- ① 判定

def _match(spelled: str) -> Optional[str]:
    """在**一段已折成小写、斜杠统一**的路径串上做名单判定。"""
    low = spelled.replace("\\", "/").lower()
    name = low.rsplit("/", 1)[-1]
    parts = [p for p in low.split("/") if p]

    if name in TOOL_BLOCKED_BASENAMES:
        return f"敏感文件（凭据/启动脚本）: {name}"
    if AGENT_STATE_DIRNAMES & set(parts):
        return "Agent 自身的运行/审计状态目录（改它等于改自己的记录或拆掉回滚安全网）"
    if name in AGENT_STATE_FILENAMES:
        return f"Agent 自身的状态文件（目标/记忆）: {name}"
    if name.endswith(CREDENTIAL_SUFFIXES):
        return f"私钥/证书文件: {name}"
    for d in SENSITIVE_DIRNAMES:
        if d in parts or (("/" in d) and d in low):
            return f"敏感目录: {d}"
    if low.startswith(SENSITIVE_DIR_PREFIXES):
        return "系统目录"
    if any(frag in low for frag in STARTUP_FRAGMENTS):
        return "自启动项"
    # `.claude/settings.json` 等同类配置（含模型凭据）
    if ".claude/" in low and name.endswith(".json"):
        return "敏感文件（模型凭据配置）"
    return None


def sensitive_target(path: "Path | str") -> Optional[str]:
    """命中敏感目标返回原因串，否则 None（① 的问题）。

    用于文件写/删/移与终端命令的前置拦截。挡两类东西：用户的凭据/自启动入口，
    以及 agent 自己的回滚快照目录。

    **H-10：先按 OS 解析后的规范路径判一遍，再按原串判一遍。**
    只按原串判就是此前那个绕过 —— `SSH~1/config` 指向 `.ssh/config`，但拼写上
    没有任何敏感成分。两遍都判只会**多**命中，不会少（原串那遍是超集兜底：
    终端命令里的 `%USERPROFILE%` 之类展开不了，只能按原串看）。
    """
    raw = str(path)
    for spelled in (canonical_text(raw), raw):
        if not spelled:
            continue
        hit = _match(spelled)
        if hit:
            return hit
    return None


# 兼容别名：老代码/测试按这些私有名引用。新代码请用上面的公开名。
_SENSITIVE_BASENAMES = TOOL_BLOCKED_BASENAMES
_SENSITIVE_SUFFIXES = CREDENTIAL_SUFFIXES
_SENSITIVE_DIRNAMES = SENSITIVE_DIRNAMES
_SENSITIVE_DIR_PREFIXES = SENSITIVE_DIR_PREFIXES
_STARTUP_FRAGMENTS = STARTUP_FRAGMENTS
_AGENT_STATE_DIRNAMES = AGENT_STATE_DIRNAMES
_AGENT_STATE_FILENAMES = AGENT_STATE_FILENAMES
