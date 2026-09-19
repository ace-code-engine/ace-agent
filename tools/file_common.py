#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools.file_common —— file_ops / terminal_view / terminal_exec 共享的常量（R-02）

原样搬自拆分前的 tools/file_tools.py 顶部（常量与注释未改一行），避免三个 mixin
各抄一份、日后改一处忘两处。这里**只放常量**，import 由各 mixin 自己按需写。
"""


# Windows cmd 的内建命令：不是磁盘上的可执行文件，argv + shell=False 调不起来。
# terminal_exec 的 allow 档据此决定走 argv 还是走 shell（见 _exec_terminal_exec）。
_CMD_BUILTIN_BASES = {"echo", "dir", "type", "cd", "copy", "move", "ren", "rename",
                      "md", "mkdir", "rd", "rmdir", "del", "erase", "ver",
                      "time", "date", "cls", "set"}

# Windows 无默认打开程序时，文本类扩展名回退记事本打开（.py 常无关联程序）
_TEXT_EXTENSIONS = {".py", ".txt", ".md", ".json", ".log", ".csv", ".ini", ".cfg",
                    ".yaml", ".yml", ".toml", ".xml", ".html", ".css", ".js",
                    ".ts", ".bat", ".cmd", ".ps1", ".sql", ".env"}

# —— grep / glob 检索参数 ——
# 跳过依赖与构建产物：搜进 node_modules/.venv 只有噪音，还会把遍历拖到分钟级。
_SEARCH_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules",
                     ".venv", "venv", ".idea", ".vscode", ".mypy_cache",
                     ".pytest_cache", "dist", "build", "site-packages",
                     ".ace_shots", ".ace_images", ".guardian"}
_SEARCH_MAX_FILE_BYTES = 2_000_000   # 超过 2MB 视为非源码，跳过
_SEARCH_MAX_FILES = 5_000            # 遍历文件数上限，防止指到巨大目录时卡死
_SEARCH_MAX_LINE_CHARS = 300         # 单条匹配行截断长度（避免压缩后的长行吃满上下文）
# 单行参与正则匹配的字符上限。和上面那个是两件事：那个管"回给模型多长"，
# 这个管"让模型的正则最多啃多长" —— re 没有超时，输入长度是唯一能收的那道界。
_SEARCH_MAX_MATCH_CHARS = 4_000

GREP_DEFAULT_MAX_RESULTS = 200
GLOB_DEFAULT_MAX_RESULTS = 200
# file_read 未显式传 limit 时的默认行数上限：整读大文件会吃满上下文
FILE_READ_DEFAULT_LIMIT = 2_000
# str_replace 上限：超过就该整文件重写或拆分，不在局部编辑工具里处理
_STR_REPLACE_MAX_BYTES = 5_000_000
_STR_REPLACE_MAX_DIFF_LINES = 200
# file_write 覆盖已有文件时算 diff 的上限（旧文件与新内容任一超过就放弃）。
# 只为渲染几行改动去读一个 10MB 文件，代价远大于收益。
_WRITE_DIFF_MAX_BYTES = 200_000
