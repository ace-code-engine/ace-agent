# ACE v3.28.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节见
> [`CHANGELOG.md`](../CHANGELOG.md#v3280-2026-09-19)。无破坏性变更。

## 一句话

交互体验第二批：把**最需要你拍板的那一步**做成产品级 —— 授权对话框编号三态、拒绝能带一句给模型的话、一个键把"全都给我看"打开。

## ✨ 授权对话框：编号三态，拒绝还能带话

以前是这样：

```
是否授权？[y 本次 / a 本会话 / N 拒绝]:
```

现在是：

```
1) 本次允许   2) 本会话允许   3) 拒绝（可写理由：n 别动这个文件）  [1-3/y/a/n]:
```

- **编号直选**：高频确认可以盲打（`1` `2` `3`），`y/a/n` 老手感照旧
- **拒绝可以附一句给模型的话**：`n 别动那个文件` —— 理由会随拒绝回传，模型下一次就知道该绕开什么。拒绝不再是死路，而是一次可执行的纠偏
- 空输入 = 拒绝（危险对话框里，回车不该等于放行）；理由超过 400 字符会被夹住

## ✨ 全部展开：`/expandall` 或 `Ctrl+E`

一个开关同时放开三处：

| | 平时 | 全部展开 |
|---|---|---|
| 工具卡片 | 输出折叠到 8 行 | 不折叠（最多 500 行） |
| diff | 按上限截断 | 不截断 |
| 思考过程 | 要 `/thinking` 或 F4 才显示 | 直接显示 |
| 只读调用 | 合成一句话（`读取 3 项`） | 逐条打出 |

日常要"干净"，排查要"全都给我看"——后者以前只能靠 `/expand` 一条条翻。

## ✨ 状态行说清"动的是哪个东西"

```
◈ 正在读取 ace/ui/ace_prompt.py 3s
◈ 正在检索 TODO 1s
◈ 正在执行 pytest -q 8s
```

比"正在调用工具"多出来的信息，是让你当场就能判断"它是不是在翻错地方"。

## ✨ 内置输入行：双击确认

`Ctrl+C` 在空输入时改成**双击确认**（第一次只提示，第二次才退出）—— 与浮层路径同一条纪律：一次误按不该杀掉跑了十分钟的会话。

## 🐛 顺带修掉的

`Ctrl+字母`之前没被映射成键名（键源只给裸控制字符），所以**任何 `Ctrl+字母` 热键都永远匹配不上** —— 这次新增的 `Ctrl+E` 当场暴露了它。

## 📋 兼容性

- 无破坏性变更；新增 9 个 i18n 键（中英日各 496 键对齐）；新增测试段 `[54]`（20 项断言）
- 仍未做：折叠组的"进行中实时说明"、持久授权规则（可编辑前缀规则 + 保存作用域选择）、通知区

---

# ACE v3.28.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail lives in
> [`CHANGELOG.md`](../CHANGELOG.md#v3280-2026-09-19). No breaking changes.

## In one line

The second interaction batch: the moment that needs **your** decision is now product-grade — numbered three-way permission options, a deny that can carry a sentence back to the model, and one key that turns on "show me everything".

## ✨ Permission dialog: numbered, and a deny that can talk

```
1) allow once   2) allow this session   3) deny (add a reason: n do not touch that file)  [1-3/y/a/n]:
```

- **number keys** for blind confirmation; `y/a/n` still work
- **deny with a reason**: the text is passed back with the refusal, so the model knows what to avoid next time — a deny becomes an actionable correction instead of a dead end
- empty input means deny (Enter must not mean "allow" in a dangerous dialog); reasons are capped at 400 characters

## ✨ Expand everything: `/expandall` or `Ctrl+E`

One switch opens tool cards (no collapsing, up to 500 lines), removes the diff cap, shows thinking without `/thinking`, and disables read-call folding. Day-to-day you want it clean; when debugging you want all of it.

## ✨ The status line names the target

`Reading ace/ui/ace_prompt.py`, `Searching TODO`, `Running pytest -q` — instead of a generic "calling a tool", so you can tell at a glance whether it is looking in the wrong place.

## ✨ Ctrl+C double-press in the built-in input line

One press hints, two presses exit — the same discipline as the overlay path: an accidental press should not kill a ten-minute session.

## 🐛 Also fixed

`Ctrl+letter` was never mapped to a key name (the key source only yields raw control characters), so **every `Ctrl+letter` hotkey silently never matched** — the new `Ctrl+E` exposed it.

## 📋 Compatibility

- No breaking changes; 9 new i18n keys (496 per locale, aligned); new test section `[54]` (20 assertions)
- Still open: live "reading X" progress inside collapsed groups, persistent permission rules (editable prefix rules + save scope), and the notification area
