//! ACE 内置计算引擎（Rust）—— 入口。
//!
//! 用法：
//!   ace-engine                 # serve：从 stdin 读 NDJSON 帧，往 stdout 写 resp 帧
//!   ace-engine --selftest      # 自检（不依赖 Python；失败退出码 1）
//!   ace-engine --bench         # 基准：stdin 收一份 JSON 作业，输出耗时
//!   ace-engine --version
//!
//! 与 Go 执行器（`executor/`）的分工：那个是**边界**（Job Object、进程树回收），
//! 这个是**算力**（分词/指纹/召回/守门批处理）。两个都是 sidecar，都走 ADR-002
//! 同一套 NDJSON；区别在于这个不裁决任何权限，也不碰文件系统。

mod events;
mod json;
mod md5;
mod protocol;
mod simhash;

use json::Json;
use protocol::{Engine, ENGINE_NAME, ENGINE_VERSION, PROTOCOL_VERSION};
use std::io::{self, BufRead, Write};
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mode = args.first().map(|s| s.as_str()).unwrap_or("serve");
    let code = match mode {
        "--version" | "-V" => {
            println!("{} {} (protocol {})", ENGINE_NAME, ENGINE_VERSION, PROTOCOL_VERSION);
            0
        }
        "--selftest" => selftest(),
        "--bench" => bench(),
        "serve" | "--serve" => serve(),
        "-h" | "--help" => {
            println!("{} {} — see engine/README.md", ENGINE_NAME, ENGINE_VERSION);
            0
        }
        other => {
            eprintln!("unknown mode: {}", other);
            2
        }
    };
    std::process::exit(code);
}

// ---------------------------------------------------------------- serve

fn serve() -> i32 {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let mut engine = Engine::new();

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        if line.trim().is_empty() {
            continue;
        }
        let frame = match protocol::parse_frame(&line) {
            Ok(f) => f,
            Err(e) => {
                // 畸形帧：回一条错误响应，**不杀会话**（与 ace_serve 同口径）
                let err = Json::obj()
                    .set("v", Json::num(PROTOCOL_VERSION))
                    .set("type", Json::str("resp"))
                    .set("id", Json::str(""))
                    .set("ok", Json::Bool(false))
                    .set(
                        "error",
                        Json::obj()
                            .set("code", Json::str(e.code))
                            .set("message", Json::str(e.message))
                            .set("http_like", Json::str("400")),
                    );
                if write_frame(&mut out, &err).is_err() {
                    break;
                }
                continue;
            }
        };
        let resp = engine.handle(&frame);
        if write_frame(&mut out, &resp).is_err() {
            break;
        }
        if engine.shutdown {
            break;
        }
    }
    0
}

/// 整行一次写出并 flush：分行写会让对面读到半个 JSON（ace_serve 的同一条理由）。
fn write_frame(out: &mut impl Write, frame: &Json) -> io::Result<()> {
    out.write_all(frame.dump().as_bytes())?;
    out.write_all(b"\n")?;
    out.flush()
}

// ---------------------------------------------------------------- selftest

/// 自检：**不依赖 Python、不依赖网络**，只验引擎自己的契约。
/// 对拍 Python 的事交给 `tools/xcheck.py`（那边能同时看到两侧真值）。
fn selftest() -> i32 {
    // 期望值来自 Python core/archive.py 的真实输出
    const VECTORS: &[(&str, &str)] = &[
        ("", "a2e4822a98337283"),
        ("a", "0c85baeecaed082f"),
        ("abc", "d52e1207ca6bbecd"),
        ("hello world", "5001c008011042e0"),
        ("帮我看看 core/archive.py", "6aa567b6b3084a94"),
        ("中文测试", "0902890072a0e086"),
        ("SimHash 中文 test_1", "082b8825d4820080"),
    ];

    let mut pass = 0usize;
    let mut fail = 0usize;
    let mut check = |name: &str, ok: bool| {
        if ok {
            pass += 1;
            println!("  ok    {}", name);
        } else {
            fail += 1;
            println!("  FAIL  {}", name);
        }
    };

    println!("[engine selftest] {} {}", ENGINE_NAME, ENGINE_VERSION);

    // 1) SimHash 与 Python 逐条对齐（含中文）
    for (text, expect_hex) in VECTORS {
        let got = simhash::hex16(simhash::simhash(text));
        check(
            &format!("simhash 对齐 python: {} ({} bytes utf8)", sanitize(text), text.len()),
            got == *expect_hex,
        );
    }

    // 2) 分词顺序与 Python 一致
    check(
        "tokenize 顺序: 先拉丁词，再中文段+二元组",
        simhash::tokenize("帮我看看 core/archive.py")
            == vec!["w:core", "w:archive", "w:py", "c:帮我看看", "b:帮我", "b:我看", "b:看看"],
    );

    // 3) 协议：版本必填、且坏版本不炸进程
    check(
        "parse_frame 缺 v 要拒",
        protocol::parse_frame(r#"{"type":"req","id":"1","method":"stats"}"#).is_err(),
    );
    check(
        "parse_frame v=\"abc\" 要拒（不是裸 panic）",
        protocol::parse_frame(r#"{"v":"abc","type":"req","id":"1","method":"stats"}"#).is_err(),
    );

    // 4) 召回语义：无交集不注入
    let mut e = Engine::new();
    let init = Json::obj()
        .set("v", Json::num(1))
        .set("type", Json::str("req"))
        .set("id", Json::str("1"))
        .set("method", Json::str("initialize"))
        .set("params", Json::obj());
    check("initialize 成功", e.handle(&init).get("ok").unwrap().as_bool() == Some(true));
    let build = Json::obj()
        .set("v", Json::num(1))
        .set("type", Json::str("req"))
        .set("id", Json::str("2"))
        .set("method", Json::str("index.build"))
        .set(
            "params",
            Json::obj().set(
                "entries",
                Json::Arr(vec![
                    Json::obj().set("id", Json::str("a")).set("text", Json::str("archive simhash")),
                    Json::obj().set("id", Json::str("b")).set("text", Json::str("unrelated english")),
                ]),
            ),
        );
    e.handle(&build);
    let rec = Json::obj()
        .set("v", Json::num(1))
        .set("type", Json::str("req"))
        .set("id", Json::str("3"))
        .set("method", Json::str("recall"))
        .set(
            "params",
            Json::obj()
                .set("query", Json::str("archive simhash"))
                .set("session", Json::str("default"))
                .set("top_k", Json::num(5)),
        );
    let items = e.handle(&rec);
    let items = items.get("result").unwrap().get("items").unwrap().as_arr().unwrap();
    check("召回只出有交集的条目", items.len() == 1
        && items[0].get("id").unwrap().as_str() == Some("a"));

    // 6) 元处理切片①：事件流索引 —— 吃原始行、坏行不中止、重复与缺口要报出来
    let mk = |id: &str, method: &str, params: Json| {
        Json::obj()
            .set("v", Json::num(1))
            .set("type", Json::str("req"))
            .set("id", Json::str(id))
            .set("method", Json::str(method))
            .set("params", params)
    };
    let load = mk(
        "4",
        "events.load",
        Json::obj().set(
            "lines",
            Json::Arr(vec![
                Json::str(r#"{"seq":1,"kind":"session/start","ts":"t","model":"m"}"#),
                Json::str(r#"{"seq":2,"kind":"tool/call","ts":"t","tool":"file_read","params":{}}"#),
                Json::str(r#"{"seq":2,"kind":"tool/call","ts":"t","tool":"file_read","params":{}}"#),
                Json::str(r#"{"seq":7,"kind":"tool/result","ts":"t","tool":"file_read","status":"403"}"#),
                Json::str("不是 JSON"),
            ]),
        ),
    );
    let lr = e.handle(&load);
    let lres = lr.get("result").unwrap();
    check(
        "events.load 吃原始行，坏行计入 skipped（不中止加载）",
        lres.get("accepted").unwrap().as_f64() == Some(4.0)
            && lres.get("skipped").unwrap().as_f64() == Some(1.0),
    );
    let st = e.handle(&mk("5", "events.stats", Json::obj()));
    let sres = st.get("result").unwrap();
    let seq = sres.get("seq").unwrap();
    check(
        "events.stats 报出 seq 重复与缺口（此前 seq_contiguous 没有生产消费者）",
        seq.get("duplicates").unwrap().as_arr().unwrap().len() == 1
            && seq.get("gaps").unwrap().as_arr().unwrap().len() == 1
            && seq.get("monotonic").unwrap().as_bool() == Some(false),
    );
    check(
        "events.stats 认得重复行（体积账的分子）",
        sres.get("duplicate_lines").unwrap().as_f64() == Some(1.0),
    );
    let vf = e.handle(&mk("6", "events.verify", Json::obj()));
    let vres = vf.get("result").unwrap();
    check(
        "events.verify 为坏行/重复报问题（ok=false 而不是静默）",
        vres.get("ok").unwrap().as_bool() == Some(false)
            && !vres.get("problems").unwrap().as_arr().unwrap().is_empty(),
    );

    println!("[engine selftest] pass {} / fail {}", pass, fail);    if fail == 0 {
        println!("ALL GREEN");
        0
    } else {
        println!("FAILED");
        1
    }
}

/// 控制台只打 ASCII：Windows 控制台可能是 cp936，中文会让标签自己变乱码
/// （`ace.cmd` 那条教训）。中文用例只报长度与结果。
fn sanitize(text: &str) -> String {
    if text.chars().all(|c| c.is_ascii()) {
        text.to_string()
    } else {
        format!("<{} chars non-ascii>", text.chars().count())
    }
}

// ---------------------------------------------------------------- bench

/// 作业格式（stdin 一份 JSON）：
/// {"texts":[...],"queries":[...],"session":"default","top_k":3,"iterations":100}
fn bench() -> i32 {
    let mut buf = String::new();
    if io::stdin().read_line(&mut buf).is_err() {
        eprintln!("--bench 需要从 stdin 读一份 JSON 作业");
        return 2;
    }
    let job = match Json::parse(buf.trim()) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("作业不是合法 JSON: {}", e);
            return 2;
        }
    };
    let texts: Vec<String> = job
        .get("texts")
        .and_then(|v| v.as_arr())
        .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let queries: Vec<String> = job
        .get("queries")
        .and_then(|v| v.as_arr())
        .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let session = job.get("session").and_then(|v| v.as_str()).unwrap_or("default").to_string();
    let top_k = job.get("top_k").and_then(|v| v.as_usize()).unwrap_or(3);
    let iterations = job.get("iterations").and_then(|v| v.as_usize()).unwrap_or(100).max(1);

    let n = texts.len();
    let t0 = Instant::now();
    let index = simhash::Index::build(
        texts
            .into_iter()
            .enumerate()
            .map(|(i, t)| (i.to_string(), t, 1.0, session.clone()))
            .collect(),
    );
    let build_ms = t0.elapsed().as_secs_f64() * 1000.0;

    // 指纹吞吐（Python 侧最贵的一步：每 token 一次 md5 + 64 次累加）
    let fp_text: String = index
        .entries
        .iter()
        .map(|e| e.text.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    let t1 = Instant::now();
    let fp_rounds = 200usize;
    for _ in 0..fp_rounds {
        std::hint::black_box(simhash::simhash(&fp_text));
    }
    let fp_ms = t1.elapsed().as_secs_f64() * 1000.0 / fp_rounds as f64;

    let qlist = if queries.is_empty() {
        vec![fp_text.clone()]
    } else {
        queries
    };
    let t2 = Instant::now();
    let mut hits_total = 0usize;
    for i in 0..iterations {
        let q = &qlist[i % qlist.len()];
        let hits = index.recall(q, "", &session, top_k, false);
        hits_total += hits.len();
    }
    let recall_ms = t2.elapsed().as_secs_f64() * 1000.0;

    let out = Json::obj()
        .set("engine", Json::str(ENGINE_NAME))
        .set("version", Json::str(ENGINE_VERSION))
        .set("entries", Json::num(n))
        .set("iterations", Json::num(iterations))
        .set("build_ms", Json::num(round3(build_ms)))
        .set("fingerprint_ms", Json::num(round3(fp_ms)))
        .set("fingerprint_chars", Json::num(fp_text.chars().count() as f64))
        .set("recall_total_ms", Json::num(round3(recall_ms)))
        .set("recall_per_call_ms", Json::num(round3(recall_ms / iterations as f64)))
        .set("hits_total", Json::num(hits_total));
    println!("{}", out.dump());
    0
}

fn round3(x: f64) -> f64 {
    (x * 1000.0).round() / 1000.0
}
