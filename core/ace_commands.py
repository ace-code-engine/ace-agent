#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ace_commands —— 自定义斜杠命令与插件目录（`.ace/commands/*.md`）

为什么需要：ACE 的斜杠命令写在代码里，用户能改的只有"怎么问"，改不了"问什么"。
团队里反复要打的那段话（"按仓库规范跑一遍测试、失败项逐条列出、不要自动改测试"）
应该是一个命令，而不是每次重敲。

文件格式（刻意简单，零依赖）：

```
---
description: 跑全量测试并逐条列失败项
argument-hint: [段号]
---
请运行 python test_all.py $ARGUMENTS，失败项逐条列出；不要改动测试文件。
```

- frontmatter 只支持 `key: value` 与逗号分隔的列表 —— **不引入 YAML 依赖**
  （核心零依赖是硬约束；需要的只是"描述 + 参数提示"这几个字段）。
- 正文里 `$ARGUMENTS` 是整串参数，`$1`/`$2` 是按空白切开的第 n 个。
- 没有 frontmatter 的 md 文件也算命令：整份正文就是提示词，描述取第一行。

插件目录（`.ace/plugins/<名字>/`）：

- `commands/*.md` → 命令（命令名加 `插件名:` 前缀，避免不同插件撞名）
- `hooks.json` → 钩子（与用户配置同样的格式，追加生效）
- `plugin.json`（可选）→ `{"name": ..., "description": ...}`

**插件不能带工具**：tools 需要 Python 模块，那是一个大得多的信任面（等于让插件
在进程内跑代码）。这一版只做"命令 + 钩子"这两种纯数据扩展，写在文档里明说。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.ace_hooks import HookSpec, _as_spec_list, substitute_placeholders

__all__ = ["CustomCommand", "parse_command_file", "load_commands_dir",
           "load_plugins", "PluginInfo", "MAX_COMMAND_CHARS"]

MAX_COMMAND_CHARS = 20_000
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
# 命令名允许 `:`（插件前缀，如 `demo:review`）与 `.`；不允许空格/斜杠 —— 命令名要能被
# `/` 菜单直接打出来。第一次实现漏了 `:`，插件命令全部被判非法（测试 [44] 当场抓到）。
_CMD_NAME = re.compile(r"^[A-Za-z0-9_.:\u4e00-\u9fff-]{1,40}$")


@dataclass
class CustomCommand:
    """一个自定义命令。"""
    name: str                    # 不含前导 "/"
    prompt: str                  # 展开后的提示词模板（还未代入参数）
    description: str = ""
    argument_hint: str = ""
    path: str = ""
    source: str = "project"      # project / plugin:<名字>

    def expand(self, arguments: str) -> str:
        return substitute_placeholders(self.prompt, arguments)

    def menu_entry(self) -> Tuple[str, str]:
        """补全菜单用：(显示名, 说明)。"""
        hint = f" {self.argument_hint}" if self.argument_hint else ""
        desc = self.description or "（自定义命令）"
        return (f"/{self.name}{hint}", f"{desc} · {self.source}")


def parse_command_file(text: str, name: str, path: str = "",
                       source: str = "project") -> Optional[CustomCommand]:
    """Markdown 文本 → CustomCommand（纯函数，可单测）。

    非法名字（含空格/斜杠等）返回 None —— 命令名要能被 `/` 菜单直接打出来。
    """
    if not _CMD_NAME.match(name or ""):
        return None
    body = text or ""
    desc = ""
    hint = ""
    m = _FRONTMATTER.match(body)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")
            if key == "description":
                desc = value
            elif key in ("argument-hint", "argument_hint", "args"):
                hint = value
        body = body[m.end():]
    prompt = body.strip()
    if not prompt:
        return None
    if not desc:
        # 没写描述就取正文第一行（去掉 markdown 标题符号），至少菜单里不是空的
        first = prompt.splitlines()[0].lstrip("#").strip()
        desc = first[:60]
    if len(prompt) > MAX_COMMAND_CHARS:
        prompt = prompt[:MAX_COMMAND_CHARS] + "\n…(命令正文过长，已截断)"
    return CustomCommand(name=name, prompt=prompt, description=desc[:120],
                         argument_hint=hint[:40], path=path, source=source)


def load_commands_dir(dir_path: str, source: str = "project",
                      prefix: str = "") -> Dict[str, CustomCommand]:
    """读一个目录下的 `*.md` → {名字: CustomCommand}。读不到就返回空。"""
    out: Dict[str, CustomCommand] = {}
    try:
        d = Path(dir_path)
        if not d.is_dir():
            return out
        for p in sorted(d.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            name = prefix + p.stem
            cmd = parse_command_file(text, name, str(p), source)
            if cmd is not None:
                out[cmd.name] = cmd
    except OSError:
        return out
    return out


@dataclass
class PluginInfo:
    """一个插件目录的加载结果。"""
    name: str
    path: str
    description: str = ""
    commands: Dict[str, CustomCommand] = field(default_factory=dict)
    hooks: Dict[str, List[HookSpec]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


def load_plugins(root: str) -> List[PluginInfo]:
    """扫 `.ace/plugins/*/`：每个目录 = 一个插件（commands/ + hooks.json）。

    单个插件出错不影响其它插件：错误记在 `PluginInfo.errors` 里，由 `/plugins`
    如实展示 —— 插件是用户自己放进去的，坏了要能看见原因，而不是静默消失。
    """
    out: List[PluginInfo] = []
    try:
        base = Path(root) / ".ace" / "plugins"
        if not base.is_dir():
            return out
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            info = PluginInfo(name=d.name, path=str(d))
            meta_file = d / "plugin.json"
            if meta_file.is_file():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if isinstance(meta, dict):
                        info.name = str(meta.get("name") or d.name)
                        info.description = str(meta.get("description") or "")
                except (OSError, json.JSONDecodeError) as e:
                    info.errors.append(f"plugin.json 解析失败: {e}")
            info.commands = load_commands_dir(str(d / "commands"),
                                              source=f"plugin:{info.name}",
                                              prefix=f"{info.name}:")
            hooks_file = d / "hooks.json"
            if hooks_file.is_file():
                try:
                    data = json.loads(hooks_file.read_text(encoding="utf-8"))
                    src = (data.get("hooks") if isinstance(data.get("hooks"), dict)
                           else data)
                    if isinstance(src, dict):
                        for event, value in src.items():
                            info.hooks.setdefault(str(event), []).extend(
                                _as_spec_list(value, str(event)))
                    else:
                        info.errors.append("hooks.json 顶层不是对象")
                except (OSError, json.JSONDecodeError) as e:
                    info.errors.append(f"hooks.json 解析失败: {e}")
            out.append(info)
    except OSError:
        return out
    return out


def merge_plugin_hooks(plugins: List[PluginInfo],
                       into: Dict[str, List[HookSpec]],
                       valid_events: Tuple[str, ...]) -> List[str]:
    """把插件钩子并进总表，返回被忽略的事件名（未知事件如实报出来）。"""
    ignored: List[str] = []
    for info in plugins:
        for event, specs in info.hooks.items():
            if event not in valid_events:
                ignored.append(f"{info.name}:{event}")
                continue
            into.setdefault(event, []).extend(specs)
    return ignored
