# v3.40.1 —— 终端编码防线：不崩（UTF-8 + replace）· 不乱（字形按控制台代码页降级）

> 反馈一句"编码错误了"。查下来是**两个症状、一个根因**：中文 Windows 控制台是 **cp936**。

## 症状一：崩 —— `UnicodeEncodeError: 'gbk' codec can't encode character`

**关键细节**：只有把输出**重定向**时才炸。真控制台走 UTF-16 API，所以"我这儿好好的、
脚本里就报错"—— 这也是它一直没被发现的原因。

复现（在中文 Windows 上）：

```powershell
$env:PYTHONIOENCODING="gbk"
python -c "print(chr(0x1F4C1))"      # UnicodeEncodeError: 'gbk' codec can't encode ...
```

谁中招：`agent_runner.py`（打 `🧑`/`🤖`/`📋`）、`setup_env.py`、`demo/record_demo.py`、
`test_all.py` —— 它们**都没有加固**（只有 `ai_code.py` 早就加了）。

修法：新增 `core/ace_io.harden_streams()`，四个入口全部接上：

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

`errors="replace"` 是关键：宁可出现一个 `?`，也不该让一次对话被一个字符打断。幂等，可重复调用。

## 症状二：乱 —— `📁` 显示成乱码/方框

根因有两层：

1. `📁`/`◐`/`◉`/`▶`/`✓`/`✗` 这些字形在 **cp936 里根本编不出来**；
2. 而把 stdout 改成 UTF-8 之后，**cp936 终端会把 UTF-8 字节按 GBK 解释** ——
   于是 `🤖` 变 `馃`、`◐` 变问号。

> 这一条本项目早期就写过纪律："刻意不用 emoji（Windows 旧终端 conhost 会渲染成方框）"。
> 我上一版在主页顶行加的 `📁` 正是破例 —— 这次把它换成了 i18n 文字标签
> （`目录` / `dir` / `フォルダ`），并把防线做成通用能力。

第二道防线在 `core/ace_io.py`：

| 函数 | 作用 |
| --- | --- |
| `console_codepage()` | 取 Windows 控制台**输出代码页**（非 Windows → None） |
| `display_encoding()` | **实际影响显示**的编码：优先控制台代码页，其次 stdout |
| `can_encode(text, enc)` | 这段文本**能不能真的显示出来** |
| `glyph(utf8, fallback, enc)` | 要显示的字形，印不出来就换 ASCII（`▶→>`、`◐→o`、`◉→O`、`✓→v`、`✗→x`） |
| `safe(text, enc)` | 整串降级：**中文原样保留**，只换掉印不出来的符号 |

**为什么不能只看 stdout 的编码**：`harden_streams()` 刚把 stdout 设成 UTF-8，于是"流是 UTF-8"
永远为真 —— 可终端还是 cp936 的。判定必须看**控制台自己的代码页**。

已经接上的地方：菜单选中标记、主页选中/禁用标记、思考强度符号（CLI 底栏与提示条）。

## 为什么值得单开一版

这两件事**只在中文 Windows 上出现**：本地 macOS/Linux 与 CI（Ubuntu）永远看不到，
所以我在这台机器上加了断言 —— 不写就一定会复发：

- `[67]` 里两条 **GBK 环境真跑**：用 `PYTHONIOENCODING=gbk` 起子进程跑
  `ai_code.py --mock --preview`、`agent_runner.py --mock --input`、`setup_env.py --check`，
  要求**退出码 0、且输出里没有 `Traceback` / `UnicodeEncodeError`**；
- 一条"每个能独立跑的入口都调了 `harden_streams()`"的源码级断言（漏一个就有一个会崩）；
- 字形降级用**注入的编码**验（`glyph("▶", encoding="cp936") == ">"`），
  这样测试结果不取决于跑测试那台机器当前的控制台是什么。

## 验证

- `[67]` 12 项；三个环境各跑一遍全量；i18n 三语各 695 键；`ruff` 零命中；
- 四张演示图重录并自校验通过（首屏顶行现在是 `ACE 3.40.1 · 目录 ace · …`）。
