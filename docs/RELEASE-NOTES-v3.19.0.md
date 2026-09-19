# ACE v3.19.0 · 更新介绍

> 面向使用者的发布说明，可直接贴进 GitHub Release。技术细节与守卫清单见
> [`CHANGELOG.md`](../CHANGELOG.md#v3190-2026-09-19)。无破坏性变更。

## 一句话

`ace --json` 给出**机器可读的事件流**：脚本、CI、编辑器插件、别的前端终于不用去解析人话了。

## ✨ 一行一个 JSON 事件

```bash
ace --json --input "现在几点" | jq -c 'select(.type=="final")'
```

```json
{"type":"session_start","ts":1789819231.8,"version":"3.19.0","permission":"write","sandbox":"off","project_root":".","model":"deepseek-v4-flash"}
{"type":"user_message","ts":...,"text":"现在几点"}
{"type":"model_request","ts":...,"round":1,"messages_count":3,"system_len":2541}
{"type":"tool_call","ts":...,"tool":"datetime_now","params":{}}
{"type":"tool_result","ts":...,"tool":"datetime_now","status":"SUCCESS","elapsed":0.0,"data":{"datetime":"2026-09-19 20:00:32"}}
{"type":"final","ts":...,"text":"当前时间是 2026-09-19 20:00:32","round":2,"sec":0.45}
{"type":"session_end","ts":...,"rounds":2,"tools":1,"violations":0,"elapsed":0.47}
```

| type | 必有字段 |
|---|---|
| `session_start` | `version` `permission` `sandbox` `project_root` |
| `user_message` | `text` |
| `model_request` | `round` `messages_count` `system_len` |
| `tool_call` | `tool` `params` |
| `tool_result` | `tool` `status` `elapsed`（成功时带 `data`） |
| `permission_request` | `tool` `reason` |
| `notice` | `text` |
| `final` | `text` |
| `session_end` | `rounds` `tools` `elapsed` |

契约的唯一来源是 `core/ace_events.EVENT_REQUIRED` —— 文档、运行时校验、测试断言都从它派生，所以不会出现"文档写了、代码没发"。

## ✨ 人话不丢

终端里原来看得到的那些输出（完成提示、权限提示、错误说明……）会变成 `notice` 事件：

```json
{"type":"notice","ts":...,"text":"  ✓ 完成（2 轮, 0.5s）"}
```

实现上不是把几百处 `print` 逐个改写，而是在 `--json` 模式下**替换 stdout**（`NoticeProxy`）—— 一处生效，后来人随手加的裸 `print` 也自动进事件流。同一份输出同时喂给人（终端）和机器（事件流），不会漂。

顺带三件事都是自动的：**没有 ANSI 颜色码**（消费者不是终端）、**没有 `\r` 重绘**（转轮/进度条整条丢掉）、**没有进度条噪音**。

## 📋 明说没做的

- **不发 `model_delta`**：一次回复可能几千条增量，灌进事件流只会让消费者自己再攒一遍。要增量请在 SDK 层接 `on_delta`。
- 非交互语义不变：需要审批的动作**一律拒绝**（不是"没人看着所以危险"，是"没人在就拒绝"）；被拒时照样发 `permission_request` 事件，让消费者看得见"这里被拒了、原因是什么"。

## 🛡️ 守卫

`[45]`（可 `--only 45`）：纯逻辑（事件构造、schema 四类问题、契约表覆盖全部类型）、`NoticeProxy` 行为（转轮丢弃、剥色、空行不产事件、`isatty` 恒 False），以及**真子进程端到端** —— 跑 `ai_code.py --mock --json …` 把 stdout 逐行当 JSON 解析：每行合法、每事件过 schema、首尾正确、五类关键事件齐全、整条流无 ANSI 无 `\r`；第二个子进程用 `--permission readonly` 验"写操作 → `permission_request` → 没有任何成功的 file_write"。

## 📋 兼容性

- 无破坏性变更：不加 `--json` 时输出与之前完全一致
- 新增 0 个 i18n 键（事件字段是机器契约，不做翻译）；契约表见 [`docs/INTERFACES.md`](../docs/INTERFACES.md)

---

# ACE v3.19.0 · Release Notes (English)

> Ready to paste into the GitHub Release. Technical detail and the guard list live in
> [`CHANGELOG.md`](../CHANGELOG.md#v3190-2026-09-19). No breaking changes.

## In one line

`ace --json` emits a **machine-readable event stream** — scripts, CI, editor plugins and other front ends no longer have to parse prose.

## ✨ One JSON event per line

```bash
ace --json --input "what time is it" | jq -c 'select(.type=="final")'
```

| type | required fields |
|---|---|
| `session_start` | `version` `permission` `sandbox` `project_root` |
| `user_message` | `text` |
| `model_request` | `round` `messages_count` `system_len` |
| `tool_call` | `tool` `params` |
| `tool_result` | `tool` `status` `elapsed` (plus `data` on success) |
| `permission_request` | `tool` `reason` |
| `notice` | `text` |
| `final` | `text` |
| `session_end` | `rounds` `tools` `elapsed` |

The single source of truth is `core/ace_events.EVENT_REQUIRED` — the docs, the runtime validator and the test assertions all derive from it, so "documented but never emitted" cannot happen.

## ✨ The prose is not lost

Everything the terminal used to show becomes a `notice` event:

```json
{"type":"notice","ts":...,"text":"  ✓ 完成（2 轮, 0.5s）"}
```

This is not a rewrite of hundreds of `print` calls: in `--json` mode stdout itself is replaced (`NoticeProxy`), so the conversion happens in one place and future bare `print`s join the stream automatically. The same output feeds the human (terminal) and the machine (event stream) without drifting.

Three things come for free: **no ANSI colour codes**, **no `\r` redraws** (spinner/progress writes are dropped wholesale), and **no progress-bar noise**.

## 📋 Explicitly not done

- **No `model_delta` events**: one reply can produce thousands of deltas, and streaming them would only make consumers re-assemble them. For incremental output, use `on_delta` at the SDK layer.
- Non-interactive semantics are unchanged: anything requiring approval is **refused** (not "dangerous because nobody is watching" but "refused because nobody is there"). A `permission_request` event is still emitted so consumers can see what was refused and why.

## 🛡️ Guards

`[45]` (runnable as `--only 45`): pure logic (event construction, four classes of schema problem, contract table covering every type), `NoticeProxy` behaviour (spinner dropped, colour stripped, blank lines ignored, `isatty()` always False), and a **real subprocess end-to-end** — run `ai_code.py --mock --json …`, parse stdout line by line as JSON: every line valid, every event schema-clean, first/last events correct, the five key event types present, and no ANSI or `\r` anywhere. A second subprocess with `--permission readonly` verifies "write attempt → `permission_request` → no successful file_write".

## 📋 Compatibility

- No breaking changes: without `--json`, output is exactly as before
- 0 new i18n keys (event fields are a machine contract and are not translated); the table lives in [`docs/INTERFACES.md`](../docs/INTERFACES.md)
