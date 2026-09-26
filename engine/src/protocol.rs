//! 帧协议与派发 —— 沿用 ADR-002（Go 执行器）与 `core/ace_serve.py` 的同一套形体：
//! `v` / `type` / `id` / 成功 `result` 与失败 `error{code,message,http_like}`，一行一帧。
//!
//! ## 边界铁律（这个引擎存在的理由，也是它的限制）
//!
//! 引擎**只算不裁**：
//! · 不做权限判定、不看路径、不碰敏感目标 —— 裁决永远在执行层（`execution_layer.py`）；
//! · 不读不写任何文件（缓冲区全在内存），持久化格式的唯一真源仍是 Python 侧；
//! · 不联网。
//!
//! 这样它才能待在 ACE 的安全模型里：一个可以被杀死、可以被替换、坏掉只会变慢
//! 而不会放宽任何闸门的**纯计算旁路**。

use crate::events::EventIndex;
use crate::json::Json;
use crate::simhash::{self, Index};

pub const PROTOCOL_VERSION: i64 = 1;
pub const MAX_LINE_BYTES: usize = 1 << 20;
pub const ENGINE_NAME: &str = "ace-engine";
pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");

pub struct ServeError {
    pub code: &'static str,
    pub message: String,
}

impl ServeError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        ServeError {
            code,
            message: message.into(),
        }
    }
}

fn http_like(code: &str) -> &'static str {
    match code {
        "E_BAD_REQUEST" | "E_UNKNOWN_TYPE" => "400",
        "E_BUSY" => "409",
        "E_NO_HANDLER" => "501",
        "E_NOT_READY" => "503",
        _ => "500",
    }
}

#[derive(Default)]
pub struct Engine {
    pub index: Index,
    /// 元处理切片①：会话事件流索引（只吃字符串行，不碰文件）
    pub events: EventIndex,
    pub ready: bool,
    pub shutdown: bool,
    pub calls: u64,
}

impl Engine {
    pub fn new() -> Self {
        Engine::default()
    }

    /// 处理一条已解析的帧，返回要写回的一帧。
    pub fn handle(&mut self, frame: &Json) -> Json {
        let id = frame.get("id").and_then(|v| v.as_str()).unwrap_or("");
        match self.dispatch(frame.get("method").and_then(|v| v.as_str()).unwrap_or(""), frame) {
            Ok(result) => resp_ok(id, result),
            Err(e) => resp_err(id, e.code, &e.message),
        }
    }

    fn dispatch(&mut self, method: &str, frame: &Json) -> Result<Json, ServeError> {
        let params = frame.get("params").cloned().unwrap_or(Json::obj());
        self.calls += 1;

        // initialize 之前只接受 initialize 与 shutdown（与 ace_serve 的 _requires_init 同口径）
        if !self.ready && method != "initialize" && method != "shutdown" {
            return Err(ServeError::new("E_NOT_READY", "尚未 initialize"));
        }

        match method {
            "initialize" => {
                self.ready = true;
                if let Some(p) = params.get("protocol").and_then(|v| v.as_f64()) {
                    if p as i64 != PROTOCOL_VERSION {
                        return Err(ServeError::new(
                            "E_BAD_REQUEST",
                            format!("协议版本 {} 不支持（本端为 {}）", p, PROTOCOL_VERSION),
                        ));
                    }
                }
                Ok(Json::obj()
                    .set("protocol", Json::num(PROTOCOL_VERSION))
                    .set("name", Json::str(ENGINE_NAME))
                    .set("version", Json::str(ENGINE_VERSION))
                    .set(
                        "features",
                        Json::Arr(
                            [
                                "fingerprint",
                                "tokenize",
                                "similarity",
                                "index.build",
                                "recall",
                                "events.load",
                                "events.stats",
                                "events.timeline",
                                "events.verify",
                            ]
                            .iter()
                            .map(|s| Json::str(*s))
                            .collect(),
                        ),
                    ))
            }
            "shutdown" => {
                self.shutdown = true;
                Ok(Json::obj().set("ok", Json::Bool(true)))
            }
            "fingerprint" => {
                let text = want_str(&params, "text")?;
                let fp = simhash::simhash(&text);
                Ok(Json::obj()
                    .set("hex", Json::str(simhash::hex16(fp)))
                    .set("bits", Json::num(simhash::SIMHASH_BITS)))
            }
            "tokenize" => {
                let text = want_str(&params, "text")?;
                Ok(Json::obj().set(
                    "tokens",
                    Json::Arr(simhash::tokenize(&text).into_iter().map(Json::str).collect()),
                ))
            }
            "similarity" => {
                let a = want_str(&params, "a")?;
                let b = want_str(&params, "b")?;
                let (fa, fb) = (simhash::simhash(&a), simhash::simhash(&b));
                Ok(Json::obj()
                    .set("text_similarity", Json::num(simhash::round4(simhash::text_similarity(&a, &b))))
                    .set("simhash_similarity", Json::num(simhash::round4(simhash::similarity(fa, fb))))
                    .set("hamming", Json::num(simhash::hamming(fa, fb)))
                    .set("a", Json::str(simhash::hex16(fa)))
                    .set("b", Json::str(simhash::hex16(fb))))
            }
            "index.build" => {
                let arr = params
                    .get("entries")
                    .and_then(|v| v.as_arr())
                    .ok_or_else(|| ServeError::new("E_BAD_REQUEST", "index.build 需要 entries 数组"))?;
                let mode = params.get("mode").and_then(|v| v.as_str()).unwrap_or("replace");
                let mut items = Vec::with_capacity(arr.len());
                for (i, e) in arr.iter().enumerate() {
                    let text = e
                        .get("text")
                        .and_then(|v| v.as_str())
                        .ok_or_else(|| ServeError::new("E_BAD_REQUEST", format!("entries[{}] 缺 text", i)))?
                        .to_string();
                    let id = e
                        .get("id")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string())
                        .unwrap_or_else(|| i.to_string());
                    let weight = e.get("weight").and_then(|v| v.as_f64()).unwrap_or(1.0);
                    let session = e
                        .get("session")
                        .and_then(|v| v.as_str())
                        .unwrap_or("default")
                        .to_string();
                    items.push((id, text, weight, session));
                }
                if mode == "append" {
                    let mut all: Vec<(String, String, f64, String)> = self
                        .index
                        .entries
                        .drain(..)
                        .map(|e| (e.id, e.text, e.weight, e.session))
                        .collect();
                    all.extend(items);
                    self.index = Index::build(all);
                } else {
                    self.index = Index::build(items);
                }
                Ok(Json::obj().set("count", Json::num(self.index.entries.len())))
            }
            "index.clear" => {
                self.index.clear();
                Ok(Json::obj().set("count", Json::num(0)))
            }
            "recall" => {
                let query = params.get("query").and_then(|v| v.as_str()).unwrap_or("");
                let anchor = params.get("anchor_text").and_then(|v| v.as_str()).unwrap_or("");
                let session = params.get("session").and_then(|v| v.as_str()).unwrap_or("default");
                let top_k = params.get("top_k").and_then(|v| v.as_usize()).unwrap_or(5);
                let exclude_last = params
                    .get("exclude_last")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let hits = self.index.recall(query, anchor, session, top_k, exclude_last);
                let items = hits
                    .into_iter()
                    .map(|h| {
                        Json::obj()
                            .set("id", Json::str(h.id))
                            .set("index", Json::num(h.index))
                            .set("similarity", Json::num(h.similarity))
                            .set("score", Json::num(h.score))
                    })
                    .collect();
                Ok(Json::obj().set("items", Json::Arr(items)))
            }
            // ── 元处理切片①：会话事件流索引 ─────────────────────────────
            // 刻意吃**原始 JSONL 行**（不是解析后的对象）：Python 侧因此一行 JSON 都不用解，
            // 而那正是"扫一遍会话日志"最贵的部分。
            "events.load" => {
                let arr = params
                    .get("lines")
                    .and_then(|v| v.as_arr())
                    .ok_or_else(|| ServeError::new("E_BAD_REQUEST", "events.load 需要 lines 数组"))?;
                let mut lines: Vec<String> = Vec::with_capacity(arr.len());
                for (i, v) in arr.iter().enumerate() {
                    let s = v.as_str().ok_or_else(|| {
                        ServeError::new(
                            "E_BAD_REQUEST",
                            format!("lines[{}] 必须是字符串（原始 JSONL 行）", i),
                        )
                    })?;
                    lines.push(s.to_string());
                }
                let append = params.get("mode").and_then(|v| v.as_str()).unwrap_or("replace") == "append";
                let (accepted, skipped) = self.events.load_lines(&lines, append);
                Ok(Json::obj()
                    .set("accepted", Json::num(accepted))
                    .set("skipped", Json::num(skipped))
                    .set("total", Json::num(self.events.len())))
            }
            "events.clear" => {
                self.events.clear();
                Ok(Json::obj().set("total", Json::num(0)))
            }
            "events.stats" => {
                let seq = self.events.seq_report();
                let (total, unique) = self.events.byte_account();
                let kinds = Json::Arr(
                    self.events
                        .counts_by_kind()
                        .into_iter()
                        .map(|(k, c, b)| {
                            Json::obj()
                                .set("kind", Json::str(k))
                                .set("count", Json::num(c))
                                .set("bytes", Json::num(b))
                        })
                        .collect(),
                );
                let tools = Json::Arr(
                    self.events
                        .tools()
                        .into_iter()
                        .map(|t| {
                            Json::obj()
                                .set("tool", Json::str(t.tool))
                                .set("calls", Json::num(t.calls))
                                .set("results", Json::num(t.results))
                                .set("errors", Json::num(t.errors))
                                .set("elapsed_ms_total", Json::num(t.elapsed_ms_total))
                                .set("elapsed_ms_max", Json::num(t.elapsed_ms_max))
                        })
                        .collect(),
                );
                Ok(Json::obj()
                    .set("events", Json::num(self.events.len()))
                    .set("bad_json", Json::num(self.events.bad_json))
                    .set("missing_fields", Json::num(self.events.missing_fields))
                    .set("duplicate_lines", Json::num(self.events.duplicate_lines))
                    .set("kinds", kinds)
                    .set("tools", tools)
                    .set(
                        "bytes",
                        Json::obj()
                            .set("total", Json::num(total))
                            .set("unique", Json::num(unique))
                            .set("redundant", Json::num(total.saturating_sub(unique))),
                    )
                    .set(
                        "seq",
                        Json::obj()
                            .set("count", Json::num(seq.count))
                            .set("first", seq.first.map_or(Json::Null, Json::num))
                            .set("last", seq.last.map_or(Json::Null, Json::num))
                            .set("monotonic", Json::Bool(seq.monotonic))
                            .set(
                                "duplicates",
                                Json::Arr(seq.duplicates.into_iter().map(Json::num).collect()),
                            )
                            .set(
                                "gaps",
                                Json::Arr(
                                    seq.gaps
                                        .into_iter()
                                        .map(|(a, b)| Json::Arr(vec![Json::num(a), Json::num(b)]))
                                        .collect(),
                                ),
                            ),
                    )
                    .set(
                        "unknown_kinds",
                        Json::Arr(
                            self.events
                                .unknown_kinds()
                                .into_iter()
                                .map(Json::str)
                                .collect(),
                        ),
                    ))
            }
            "events.timeline" => {
                let kind = params.get("kind").and_then(|v| v.as_str()).unwrap_or("");
                let tool = params.get("tool").and_then(|v| v.as_str()).unwrap_or("");
                let limit = params.get("limit").and_then(|v| v.as_usize()).unwrap_or(20);
                let items = Json::Arr(
                    self.events
                        .timeline(kind, tool, limit)
                        .into_iter()
                        .map(|e| {
                            Json::obj()
                                .set("seq", Json::num(e.seq))
                                .set("kind", Json::str(e.kind.clone()))
                                .set("ts", Json::str(e.ts.clone()))
                                .set("tool", Json::str(e.tool.clone()))
                                .set("status", Json::str(e.status.clone()))
                                .set("level", Json::str(e.level.clone()))
                                .set("model", Json::str(e.model.clone()))
                                .set("subagent", Json::str(e.subagent.clone()))
                                .set("bytes", Json::num(e.bytes))
                                .set("elapsed_ms", Json::num(e.elapsed_ms))
                                .set("in_tokens", Json::num(e.in_tokens))
                                .set("out_tokens", Json::num(e.out_tokens))
                                .set("system_len", Json::num(e.system_len))
                                .set("messages_count", Json::num(e.messages_count))
                        })
                        .collect(),
                );
                Ok(Json::obj().set("items", items))
            }
            "events.verify" => {
                let seq = self.events.seq_report();
                let mut problems: Vec<Json> = Vec::new();
                if self.events.bad_json > 0 {
                    problems.push(
                        Json::obj()
                            .set("code", Json::str("bad_json"))
                            .set("detail", Json::num(self.events.bad_json)),
                    );
                }
                if self.events.missing_fields > 0 {
                    problems.push(
                        Json::obj()
                            .set("code", Json::str("missing_seq_or_kind"))
                            .set("detail", Json::num(self.events.missing_fields)),
                    );
                }
                if !seq.monotonic {
                    problems.push(
                        Json::obj()
                            .set("code", Json::str("seq_not_monotonic"))
                            .set("detail", Json::str("seq 出现回退")),
                    );
                }
                if !seq.duplicates.is_empty() {
                    problems.push(
                        Json::obj()
                            .set("code", Json::str("seq_duplicate"))
                            .set("detail", Json::Arr(seq.duplicates.iter().copied().map(Json::num).collect())),
                    );
                }
                if !seq.gaps.is_empty() {
                    problems.push(Json::obj().set("code", Json::str("seq_gap")).set(
                        "detail",
                        Json::Arr(
                            seq.gaps
                                .iter()
                                .map(|(a, b)| Json::Arr(vec![Json::num(*a), Json::num(*b)]))
                                .collect(),
                        ),
                    ));
                }
                Ok(Json::obj()
                    .set("ok", Json::Bool(problems.is_empty()))
                    .set("checked", Json::num(seq.count))
                    .set("problems", Json::Arr(problems)))
            }
            "stats" => Ok(Json::obj()                .set("entries", Json::num(self.index.entries.len()))
                .set("sessions", Json::num(self.index.sessions()))
                .set("tokens", Json::num(self.index.total_tokens()))
                .set("calls", Json::num(self.calls))
                .set("protocol", Json::num(PROTOCOL_VERSION))
                .set("version", Json::str(ENGINE_VERSION))),
            other => Err(ServeError::new(
                "E_NO_HANDLER",
                format!("不认识的方法: {}", other),
            )),
        }
    }
}

fn want_str(params: &Json, key: &str) -> Result<String, ServeError> {
    params
        .get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| ServeError::new("E_BAD_REQUEST", format!("缺少字符串参数 {}", key)))
}

fn resp_ok(id: &str, result: Json) -> Json {
    Json::obj()
        .set("v", Json::num(PROTOCOL_VERSION))
        .set("type", Json::str("resp"))
        .set("id", Json::str(id))
        .set("ok", Json::Bool(true))
        .set("result", result)
}

fn resp_err(id: &str, code: &str, message: &str) -> Json {
    Json::obj()
        .set("v", Json::num(PROTOCOL_VERSION))
        .set("type", Json::str("resp"))
        .set("id", Json::str(id))
        .set("ok", Json::Bool(false))
        .set(
            "error",
            Json::obj()
                .set("code", Json::str(code))
                .set("message", Json::str(message))
                .set("http_like", Json::str(http_like(code))),
        )
}

/// 解析一帧。**版本字段是必填且必须是整数** ——
/// `ace_serve.parse_frame` 那处「缺 v 也接受、`v="abc"` 抛裸 ValueError 穿出去」
/// 的教训（见后端评审 §2.1）在这里不重演。
pub fn parse_frame(line: &str) -> Result<Json, ServeError> {
    let raw = line.trim();
    if raw.is_empty() {
        return Err(ServeError::new("E_BAD_REQUEST", "空行不是合法帧"));
    }
    if raw.len() > MAX_LINE_BYTES {
        return Err(ServeError::new(
            "E_BAD_REQUEST",
            format!("单行超过上限 {} 字节", MAX_LINE_BYTES),
        ));
    }
    let frame = Json::parse(raw).map_err(|e| ServeError::new("E_BAD_REQUEST", format!("不是合法 JSON: {}", e)))?;
    let ftype = frame
        .get("type")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ServeError::new("E_BAD_REQUEST", "缺 type"))?;
    if ftype != "req" {
        return Err(ServeError::new("E_UNKNOWN_TYPE", format!("不认识的 type: {}", ftype)));
    }
    match frame.get("v") {
        None => return Err(ServeError::new("E_BAD_REQUEST", "缺 v（协议版本必填）")),
        Some(v) => match v.as_f64() {
            Some(f) if f.fract() == 0.0 && f as i64 == PROTOCOL_VERSION => {}
            Some(f) => {
                return Err(ServeError::new(
                    "E_BAD_REQUEST",
                    format!("协议版本 {} 不支持（本端为 {}）", f, PROTOCOL_VERSION),
                ))
            }
            None => return Err(ServeError::new("E_BAD_REQUEST", "v 必须是整数")),
        },
    }
    if frame.get("method").and_then(|v| v.as_str()).is_none() {
        return Err(ServeError::new("E_BAD_REQUEST", "req 缺 method"));
    }
    if frame.get("id").and_then(|v| v.as_str()).is_none() {
        return Err(ServeError::new("E_BAD_REQUEST", "req 缺 id"));
    }
    Ok(frame)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(id: &str, method: &str, params: Json) -> Json {
        Json::obj()
            .set("v", Json::num(1))
            .set("type", Json::str("req"))
            .set("id", Json::str(id))
            .set("method", Json::str(method))
            .set("params", params)
    }

    #[test]
    fn version_is_mandatory_and_typed() {
        assert!(parse_frame(r#"{"v":1,"type":"req","id":"1","method":"stats"}"#).is_ok());
        // 缺 v → 拒（ace_serve 是"缺 v 也接受"，这里不重复那个洞）
        assert!(parse_frame(r#"{"type":"req","id":"1","method":"stats"}"#).is_err());
        // 非整数 v → 拒，且是 ServeError 而不是裸 panic
        assert!(parse_frame(r#"{"v":"abc","type":"req","id":"1","method":"stats"}"#).is_err());
        assert!(parse_frame(r#"{"v":2,"type":"req","id":"1","method":"stats"}"#).is_err());
    }

    #[test]
    fn needs_initialize_first() {
        let mut e = Engine::new();
        let r = e.handle(&req("1", "stats", Json::obj()));
        assert_eq!(r.get("ok").unwrap().as_bool(), Some(false));
        assert_eq!(
            r.get("error").unwrap().get("code").unwrap().as_str(),
            Some("E_NOT_READY")
        );
        let r = e.handle(&req("2", "initialize", Json::obj()));
        assert_eq!(r.get("ok").unwrap().as_bool(), Some(true));
        assert_eq!(r.get("result").unwrap().get("protocol").unwrap().as_f64(), Some(1.0));
    }

    #[test]
    fn unknown_method_reports_501() {
        let mut e = Engine::new();
        e.handle(&req("1", "initialize", Json::obj()));
        let r = e.handle(&req("2", "nope", Json::obj()));
        assert_eq!(
            r.get("error").unwrap().get("http_like").unwrap().as_str(),
            Some("501")
        );
    }

    #[test]
    fn recall_top_k_semantics() {
        let mut e = Engine::new();
        e.handle(&req("1", "initialize", Json::obj()));
        let entries = Json::Arr(vec![
            Json::obj().set("id", Json::str("a")).set("text", Json::str("帮我看看 archive 的 simhash")),
            Json::obj().set("id", Json::str("b")).set("text", Json::str("完全无关的英文内容")),
            Json::obj().set("id", Json::str("c")).set("text", Json::str("archive simhash 主题相似度")),
        ]);
        e.handle(&req("2", "index.build", Json::obj().set("entries", entries)));
        let r = e.handle(&req(
            "3",
            "recall",
            Json::obj()
                .set("query", Json::str("看看 archive simhash"))
                .set("session", Json::str("default"))
                .set("top_k", Json::num(5)),
        ));
        let items = r.get("result").unwrap().get("items").unwrap().as_arr().unwrap();
        // 无 token 交集的条目必须被丢弃（Python: score <= 0 → break）
        assert!(items.iter().all(|i| i.get("score").unwrap().as_f64().unwrap() > 0.0));
        assert!(items.iter().any(|i| i.get("id").unwrap().as_str() == Some("a")));
    }
}
