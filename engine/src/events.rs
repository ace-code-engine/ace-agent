//! 事件流索引 —— 元处理内核的第一个切片。
//!
//! ## 为什么这是"元处理"，不是"加速"
//!
//! 会话日志（`.ace_sessions/*.jsonl`）记的是**这次运行自身**：谁说了什么、模型看到了
//! 什么、跑过哪些工具、谁批了什么、快照建/回滚了几次。今天这些事件被三处各解析一遍
//! （`cli/ace_sessionlog.py` 写与重放、`cli/ace_sessions.py` 派生视图、`core/ace_todos.py`
//! 重放清单），而且**没有人算统计、没有人查连续性** —— `seq_contiguous()` 写好了却
//! 没有生产消费者。
//!
//! 这个切片就干那件事：把一坨 JSONL 变成可查询的元事实 —— 分类计数、体积账（含
//! **冗余体积**：每轮都把完整系统提示词写一遍，日志体积的大头就在那儿）、seq 连续性、
//! 工具成/败聚合、按 kind/tool 过滤的时间线。
//!
//! ## 边界（同引擎总则）
//!
//! 只吃字符串行、只在内存里建索引：不读文件、不判权限、不裁决任何东西。
//! 二进制原样留着 —— 因为"这次运行的元事实"必须能对回原始字节。
//!
//! ## 前向兼容
//!
//! kind 词表会随版本长出新值（这份数据里已经有 `session/start`，而 `K_*` 常量表里没有）。
//! 所以**不认识的 kind 不是错误**，只作为信息上报（`unknown_kinds`）；
//! 缺 `seq`/`kind` 的行走另一个计数（`missing_fields`），两者都不丢数据、不中止加载。

use crate::json::Json;
use crate::md5;
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// 已知事件 kind（`cli/ace_sessionlog.py` 的 `K_*` + `session/start`）。
/// 它只用来回答"有没有我不认识的 kind"，**不是白名单**。
pub const KNOWN_KINDS: &[&str] = &[
    "session/start",
    "user/message",
    "assistant/message",
    "request/snapshot",
    "system/snapshot",
    "tool/call",
    "tool/result",
    "permission/decision",
    "security/denied",
    "guard/verdict",
    "snapshot/create",
    "snapshot/rollback",
    "snapshot/unavailable",
    "goal/round",
    "model/error",
    "model/usage",
    "compaction/event",
    "model/switch",
];

/// 内容指纹：把对象里**除 seq/ts 之外的全部字符串值**按顺序拼起来再哈希。
///
/// 为什么不是整行哈希：整行里带着唯一的 `seq`，于是同一段系统提示词写 20 遍也
/// "永远不重复"，冗余恒为 0 —— 实测在真实日志上就是这么暴露出来的
/// （`system/snapshot` 占 88% 体积，而冗余算出 0）。
///
/// 为什么只取字符串值：数字/浮点的序列化格式在两种语言里细节不同（1 vs 1.0、
/// 空格、转义），取字符串就能让 Rust 与 Python 的降级实现**逐字节对得上**。
fn content_digest(v: &Json) -> u64 {
    let mut s = String::new();
    if let Json::Obj(m) = v {
        for (k, val) in m {
            if k == "seq" || k == "ts" {
                continue;
            }
            if let Json::Str(text) = val {
                s.push_str(text);
                s.push('\u{1}');
            }
        }
    }
    md5::hash64(&s)
}

pub struct EventMeta {
    pub seq: i64,
    pub kind: String,
    pub ts: String,
    /// 事件里的 `tool` 字段（tool/call、tool/result、permission/decision 都有）
    pub tool: String,
    /// 事件里的 `status`（tool/result）或 `decision`（permission/decision）
    pub status: String,
    /// `permission/decision` 的权限档（readonly/write/full）
    pub level: String,
    /// `request/snapshot` 的模型名（也是 `model/usage` 的模型）
    pub model: String,
    /// `request/snapshot` 的 `subagent`（非空 = 子代理请求，spawn/fork）
    pub subagent: String,
    pub bytes: usize,
    /// 实测耗时（tool/result 的 `elapsed_ms`；秒级 ts 推不出耗时，只能靠这个字段）
    pub elapsed_ms: i64,
    /// 每轮 token 用量（model/usage）
    pub in_tokens: i64,
    pub out_tokens: i64,
    /// 上下文规模（request/snapshot 的 `system_len` / `messages_count`）
    pub system_len: i64,
    pub messages_count: i64,
}

#[derive(Default)]
pub struct EventIndex {
    pub events: Vec<EventMeta>,
    /// 不是合法 JSON
    pub bad_json: usize,
    /// 是 JSON，但缺 `seq`/`kind`（契约要求的两个字段）
    pub missing_fields: usize,
    /// 内容与前面某条**逐字节相同**的事件数（"这段系统提示词被写了几遍"）。
    /// 这是体积账的分子：`system/snapshot` 每轮都写完整系统提示词。
    pub duplicate_lines: usize,
    /// 字节账：digest → 该内容首次出现时的字节数
    digests: HashMap<u64, usize>,
    total_bytes: usize,
}

pub struct SeqReport {
    pub count: usize,
    pub first: Option<i64>,
    pub last: Option<i64>,
    pub monotonic: bool,
    pub duplicates: Vec<i64>,
    pub gaps: Vec<(i64, i64)>,
}

pub struct ToolStat {
    pub tool: String,
    pub calls: usize,
    pub results: usize,
    pub errors: usize,
    /// 实测耗时合计/最大（毫秒）。此前推不出来 —— ts 只有秒级粒度。
    pub elapsed_ms_total: i64,
    pub elapsed_ms_max: i64,
}

impl EventIndex {
    pub fn clear(&mut self) {
        self.events.clear();
        self.bad_json = 0;
        self.missing_fields = 0;
        self.duplicate_lines = 0;
        self.digests.clear();
        self.total_bytes = 0;
    }

    pub fn len(&self) -> usize {
        self.events.len()
    }

    /// 吃一批**原始 JSONL 行**（不是解析后的对象）。
    ///
    /// 刻意吃原文：Python 侧因此一行 JSON 都不用解 —— 那正是这条路径上最贵的部分。
    /// 返回 (接受, 跳过)。
    pub fn load_lines(&mut self, lines: &[String], append: bool) -> (usize, usize) {
        if !append {
            self.clear();
        }
        let (mut accepted, mut skipped) = (0usize, 0usize);
        for line in lines {
            let raw = line.trim();
            if raw.is_empty() {
                continue;
            }
            match Json::parse(raw) {
                Ok(v) => {
                    let seq = v.get("seq").and_then(|x| x.as_i64());
                    let kind = v.get("kind").and_then(|x| x.as_str()).map(|s| s.to_string());
                    match (seq, kind) {
                        (Some(seq), Some(kind)) => {
                            let ts = v
                                .get("ts")
                                .and_then(|x| x.as_str())
                                .unwrap_or("")
                                .to_string();
                            let tool = v
                                .get("tool")
                                .and_then(|x| x.as_str())
                                .unwrap_or("")
                                .to_string();
                            // tool/result 用 status；permission/decision 用 decision —— 都归一到一个字段
                            let status = v
                                .get("status")
                                .and_then(|x| x.as_str())
                                .or_else(|| v.get("decision").and_then(|x| x.as_str()))
                                .unwrap_or("")
                                .to_string();
                            let level = v
                                .get("level")
                                .and_then(|x| x.as_str())
                                .unwrap_or("")
                                .to_string();
                            let model = v
                                .get("model")
                                .and_then(|x| x.as_str())
                                .unwrap_or("")
                                .to_string();
                            let subagent = v
                                .get("subagent")
                                .and_then(|x| x.as_str())
                                .unwrap_or("")
                                .to_string();
                            let num = |key: &str| -> i64 {
                                v.get(key).and_then(|x| x.as_i64()).unwrap_or(0)
                            };
                            let bytes = raw.len();
                            let digest = content_digest(&v);
                            self.total_bytes += bytes;
                            if self.digests.contains_key(&digest) {
                                self.duplicate_lines += 1;
                            } else {
                                self.digests.insert(digest, bytes);
                            }
                            self.events.push(EventMeta {
                                seq,
                                kind,
                                ts,
                                tool,
                                status,
                                level,
                                model,
                                subagent,
                                bytes,
                                elapsed_ms: num("elapsed_ms"),
                                in_tokens: num("in_tokens"),
                                out_tokens: num("out_tokens"),
                                system_len: num("system_len"),
                                messages_count: num("messages_count"),
                            });
                            accepted += 1;
                        }
                        _ => {
                            self.missing_fields += 1;
                            skipped += 1;
                        }
                    }
                }
                Err(_) => {
                    self.bad_json += 1;
                    skipped += 1;
                }
            }
        }
        (accepted, skipped)
    }

    /// 分类计数（按条数降序，同数按名字升序 —— 稳定，便于对拍）
    pub fn counts_by_kind(&self) -> Vec<(String, usize, usize)> {
        let mut m: BTreeMap<&str, (usize, usize)> = BTreeMap::new();
        for e in &self.events {
            let slot = m.entry(e.kind.as_str()).or_insert((0, 0));
            slot.0 += 1;
            slot.1 += e.bytes;
        }
        let mut v: Vec<(String, usize, usize)> = m
            .into_iter()
            .map(|(k, (c, b))| (k.to_string(), c, b))
            .collect();
        v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        v
    }

    /// 体积账：(总字节, 去重后的字节)。差值就是"同一段内容被重复写了几遍"。
    ///
    /// 这条是这套日志最值得看的一个数：`system/snapshot` 每轮都写完整系统提示词，
    /// 一份 132 KB / 122 事件的日志里，大头就是它。
    pub fn byte_account(&self) -> (usize, usize) {
        let unique: usize = self.digests.values().sum();
        (self.total_bytes, unique)
    }

    pub fn seq_report(&self) -> SeqReport {
        let count = self.events.len();
        let first = self.events.first().map(|e| e.seq);
        let last = self.events.last().map(|e| e.seq);
        let mut monotonic = true;
        let mut duplicates: Vec<i64> = Vec::new();
        let mut gaps: Vec<(i64, i64)> = Vec::new();
        let mut seen: BTreeSet<i64> = BTreeSet::new();
        let mut prev: Option<i64> = None;
        for e in &self.events {
            if !seen.insert(e.seq) {
                if duplicates.len() < 20 && !duplicates.contains(&e.seq) {
                    duplicates.push(e.seq);
                }
            }
            if let Some(p) = prev {
                if e.seq <= p {
                    monotonic = false;
                } else if e.seq > p + 1 && gaps.len() < 20 {
                    gaps.push((p, e.seq));
                }
            }
            prev = Some(e.seq);
        }
        SeqReport {
            count,
            first,
            last,
            monotonic,
            duplicates,
            gaps,
        }
    }

    pub fn tools(&self) -> Vec<ToolStat> {
        let mut m: BTreeMap<&str, ToolStat> = BTreeMap::new();
        for e in &self.events {
            if e.tool.is_empty() {
                continue;
            }
            let slot = m.entry(e.tool.as_str()).or_insert_with(|| ToolStat {
                tool: e.tool.clone(),
                calls: 0,
                results: 0,
                errors: 0,
                elapsed_ms_total: 0,
                elapsed_ms_max: 0,
            });
            if e.kind == "tool/call" {
                slot.calls += 1;
            } else if e.kind == "tool/result" {
                slot.results += 1;
                if !e.status.is_empty() && e.status != "success" {
                    slot.errors += 1;
                }
                if e.elapsed_ms > 0 {
                    slot.elapsed_ms_total += e.elapsed_ms;
                    if e.elapsed_ms > slot.elapsed_ms_max {
                        slot.elapsed_ms_max = e.elapsed_ms;
                    }
                }
            }
        }
        let mut v: Vec<ToolStat> = m.into_values().collect();
        v.sort_by(|a, b| b.calls.cmp(&a.calls).then(a.tool.cmp(&b.tool)));
        v
    }

    /// 时间线：按 kind 子串 / tool 过滤，取**末尾** limit 条（与 `/audit` 同口径：
    /// 人看的永远是最近发生的事）。limit = 0 表示不截断。
    pub fn timeline(&self, kind_sub: &str, tool: &str, limit: usize) -> Vec<&EventMeta> {
        let mut picked: Vec<&EventMeta> = self
            .events
            .iter()
            .filter(|e| kind_sub.is_empty() || e.kind.contains(kind_sub))
            .filter(|e| tool.is_empty() || e.tool == tool)
            .collect();
        if limit > 0 && picked.len() > limit {
            picked.drain(0..picked.len() - limit);
        }
        picked
    }

    pub fn unknown_kinds(&self) -> Vec<String> {
        let known: BTreeSet<&str> = KNOWN_KINDS.iter().copied().collect();
        self.events
            .iter()
            .map(|e| e.kind.as_str())
            .filter(|k| !known.contains(k))
            .collect::<BTreeSet<&str>>()
            .into_iter()
            .map(|s| s.to_string())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lines_of(raw: &[&str]) -> Vec<String> {
        raw.iter().map(|s| s.to_string()).collect()
    }

    const SAMPLE: &[&str] = &[
        r#"{"seq":1,"kind":"session/start","ts":"2026-09-24 23:57:28","model":"m"}"#,
        r#"{"seq":2,"kind":"user/message","ts":"2026-09-24 23:57:28","content":"ping"}"#,
        r#"{"seq":3,"kind":"tool/call","ts":"2026-09-24 23:57:28","tool":"datetime_now","params":{}}"#,
        r#"{"seq":4,"kind":"tool/result","ts":"2026-09-24 23:57:28","tool":"datetime_now","status":"success","message":""}"#,
        r#"{"seq":5,"kind":"tool/call","ts":"2026-09-24 23:57:29","tool":"file_write","params":{"path":"a"}}"#,
        r#"{"seq":6,"kind":"tool/result","ts":"2026-09-24 23:57:29","tool":"file_write","status":"403","message":"越界"}"#,
    ];

    #[test]
    fn loads_and_counts() {
        let mut idx = EventIndex::default();
        let (a, s) = idx.load_lines(&lines_of(SAMPLE), false);
        assert_eq!((a, s), (6, 0));
        let counts = idx.counts_by_kind();
        assert_eq!(counts[0].1, 2); // tool/call 与 tool/result 各 2，平手按名字升序
        assert!(idx.counts_by_kind().iter().any(|(k, c, _)| k == "session/start" && *c == 1));
    }

    #[test]
    fn tools_aggregate_and_errors() {
        let mut idx = EventIndex::default();
        idx.load_lines(&lines_of(SAMPLE), false);
        let t = idx.tools();
        let dw = t.iter().find(|t| t.tool == "datetime_now").unwrap();
        assert_eq!((dw.calls, dw.results, dw.errors), (1, 1, 0));
        let fw = t.iter().find(|t| t.tool == "file_write").unwrap();
        assert_eq!((fw.calls, fw.results, fw.errors), (1, 1, 1));
    }

    #[test]
    fn seq_gaps_and_duplicates_are_reported() {
        let mut idx = EventIndex::default();
        idx.load_lines(
            &lines_of(&[
                r#"{"seq":1,"kind":"user/message"}"#,
                r#"{"seq":2,"kind":"user/message"}"#,
                r#"{"seq":2,"kind":"user/message"}"#,
                r#"{"seq":9,"kind":"user/message"}"#,
            ]),
            false,
        );
        let r = idx.seq_report();
        assert_eq!(r.count, 4);
        assert!(!r.monotonic);
        assert_eq!(r.duplicates, vec![2]);
        assert_eq!(r.gaps, vec![(2, 9)]);
    }

    #[test]
    fn bad_lines_do_not_abort_and_are_counted() {
        let mut idx = EventIndex::default();
        let (a, s) = idx.load_lines(
            &lines_of(&[
                r#"{"seq":1,"kind":"user/message"}"#,
                "不是 JSON",
                r#"{"seq":2}"#,                      // 缺 kind
                r#"{"kind":"user/message"}"#,        // 缺 seq
                "",
            ]),
            false,
        );
        assert_eq!((a, s), (1, 3));
        assert_eq!(idx.bad_json, 1);
        assert_eq!(idx.missing_fields, 2);
        assert_eq!(idx.len(), 1);
    }

    #[test]
    fn redundancy_account() {
        let a1 = r#"{"seq":1,"kind":"system/snapshot","ts":"t1","system":"AAAA"}"#;
        let a2 = r#"{"seq":5,"kind":"system/snapshot","ts":"t2","system":"AAAA"}"#;
        let b = r#"{"seq":9,"kind":"system/snapshot","ts":"t3","system":"BBBB"}"#;
        let mut idx = EventIndex::default();
        idx.load_lines(&lines_of(&[a1, a2, b]), false);
        // 内容 A 重复一次（seq 1 与 5），B 首次
        assert_eq!(idx.duplicate_lines, 1);
        let (total, unique) = idx.byte_account();
        assert_eq!(total, a1.len() + a2.len() + b.len());
        // 唯一内容 = A 首次出现的那行 + B 那行（a2 整行计入 total，但不计入 unique）
        assert_eq!(unique, a1.len() + b.len());
        assert!(total > unique, "整行不同、内容相同的行必须算出冗余");
    }

    #[test]
    fn extracts_metrics_fields() {
        let mut idx = EventIndex::default();
        idx.load_lines(
            &lines_of(&[
                r#"{"seq":1,"kind":"request/snapshot","model":"m1","permission":"write","system_len":2875,"messages_count":8}"#,
                r#"{"seq":2,"kind":"permission/decision","tool":"file_write","decision":"allowed","level":"write"}"#,
                r#"{"seq":3,"kind":"tool/call","tool":"file_write","params":{}}"#,
                r#"{"seq":4,"kind":"tool/result","tool":"file_write","status":"success","elapsed_ms":1200}"#,
                r#"{"seq":5,"kind":"tool/result","tool":"file_write","status":"403","elapsed_ms":300}"#,
                r#"{"seq":6,"kind":"model/usage","model":"m1","in_tokens":1000,"out_tokens":200}"#,
            ]),
            false,
        );
        let e0 = &idx.events[0];
        assert_eq!((e0.model.as_str(), e0.system_len, e0.messages_count), ("m1", 2875, 8));
        let e1 = &idx.events[1];
        assert_eq!((e1.level.as_str(), e1.status.as_str()), ("write", "allowed"));
        let t = idx
            .tools()
            .into_iter()
            .find(|t| t.tool == "file_write")
            .expect("file_write 统计");
        assert_eq!((t.calls, t.results, t.errors), (1, 2, 1));
        assert_eq!((t.elapsed_ms_total, t.elapsed_ms_max), (1500, 1200));
        let u = &idx.events[5];
        assert_eq!((u.in_tokens, u.out_tokens), (1000, 200));
    }

    #[test]
    fn unknown_kind_is_informational_not_an_error() {
        let mut idx = EventIndex::default();
        idx.load_lines(&lines_of(&[r#"{"seq":1,"kind":"future/thing"}"#]), false);
        assert_eq!(idx.len(), 1);
        assert_eq!(idx.bad_json, 0);
        assert_eq!(idx.unknown_kinds(), vec!["future/thing".to_string()]);
    }
}
