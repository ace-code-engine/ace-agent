//! 最小 JSON —— 只覆盖协议需要的那部分，零依赖。
//!
//! 为什么不用 serde：本机 `cargo build --offline` 要能过（无 crates.io），
//! 且这个引擎的立场是「安全核心零依赖」。协议是 NDJSON，一帧一个对象，
//! 语法面很小 —— 自己写反而能把「不接受什么」写清楚。
//!
//! 有意的限制：
//! · 数字一律 f64 —— **指纹不要走数字**（64 位整数超出 f64 精度）。协议里
//!   指纹用 16 位十六进制字符串，见 `simhash::hex16`。
//! · 对象按插入顺序保存（`Vec`），序列化时保持顺序，便于逐字节比对帧。

use std::fmt::Write as _;

/// 数值入口：`f64` 本身没有覆盖 `usize`/`u64`/`i64` 的 `From`，
/// 而协议里计数字段（entries/iterations/tokens…）全是无符号整数。
/// 让调用点写 `Json::num(n)` 就够，不必每处 `as f64`。
pub trait IntoNum {
    fn into_num(self) -> f64;
}

impl IntoNum for f64 {
    fn into_num(self) -> f64 {
        self
    }
}
macro_rules! into_num_via_as {
    ($($t:ty),*) => {$(
        impl IntoNum for $t {
            fn into_num(self) -> f64 { self as f64 }
        }
    )*};
}
into_num_via_as!(i8, i16, i32, i64, isize, u8, u16, u32, u64, usize, f32);


#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

impl Json {
    pub fn obj() -> Json {
        Json::Obj(Vec::new())
    }

    pub fn str(s: impl Into<String>) -> Json {
        Json::Str(s.into())
    }

    pub fn num(n: impl IntoNum) -> Json {
        Json::Num(n.into_num())
    }

    /// 链式塞字段：`Json::obj().set("a", Json::num(1))`
    pub fn set(mut self, k: &str, v: Json) -> Json {
        if let Json::Obj(ref mut m) = self {
            m.retain(|(key, _)| key != k);
            m.push((k.to_string(), v));
        }
        self
    }

    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Obj(m) => m.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::Str(s) => Some(s.as_str()),
            _ => None,
        }
    }

    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Json::Num(n) => Some(*n),
            _ => None,
        }
    }

    pub fn as_usize(&self) -> Option<usize> {
        match self {
            Json::Num(n) if *n >= 0.0 && n.fract() == 0.0 => Some(*n as usize),
            _ => None,
        }
    }

    /// 整数读法（`seq` 这类计数字段）。负数保留 —— 调用方自己决定要不要拒。
    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Json::Num(n) if n.fract() == 0.0 => Some(*n as i64),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Json::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_arr(&self) -> Option<&Vec<Json>> {
        match self {
            Json::Arr(a) => Some(a),
            _ => None,
        }
    }

    // ---------------------------------------------------------------- 解析

    pub fn parse(s: &str) -> Result<Json, String> {
        let b = s.as_bytes();
        let mut p = Parser { b, i: 0 };
        p.ws();
        let v = p.value()?;
        p.ws();
        if p.i != b.len() {
            return Err(format!("尾随内容 @{}", p.i));
        }
        Ok(v)
    }

    // ---------------------------------------------------------------- 序列化

    /// `ensure_ascii = false` 口径（与 `core/ace_serve.py` 一致）：非 ASCII 原样输出。
    pub fn dump(&self) -> String {
        let mut out = String::new();
        self.write(&mut out);
        out
    }

    fn write(&self, out: &mut String) {
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(true) => out.push_str("true"),
            Json::Bool(false) => out.push_str("false"),
            Json::Num(n) => {
                if n.is_finite() {
                    if n.fract() == 0.0 && n.abs() < 1e15 {
                        let _ = write!(out, "{}", *n as i64);
                    } else {
                        let _ = write!(out, "{}", n);
                    }
                } else {
                    out.push_str("null");
                }
            }
            Json::Str(s) => write_str(s, out),
            Json::Arr(a) => {
                out.push('[');
                for (i, v) in a.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    v.write(out);
                }
                out.push(']');
            }
            Json::Obj(m) => {
                out.push('{');
                for (i, (k, v)) in m.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    write_str(k, out);
                    out.push(':');
                    v.write(out);
                }
                out.push('}');
            }
        }
    }
}

fn write_str(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

struct Parser<'a> {
    b: &'a [u8],
    i: usize,
}

impl<'a> Parser<'a> {
    fn ws(&mut self) {
        while self.i < self.b.len() && matches!(self.b[self.i], b' ' | b'\t' | b'\r' | b'\n') {
            self.i += 1;
        }
    }

    fn peek(&self) -> Option<u8> {
        self.b.get(self.i).copied()
    }

    fn value(&mut self) -> Result<Json, String> {
        match self.peek() {
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'"') => Ok(Json::Str(self.string()?)),
            Some(b't') => self.lit("true", Json::Bool(true)),
            Some(b'f') => self.lit("false", Json::Bool(false)),
            Some(b'n') => self.lit("null", Json::Null),
            Some(_) => self.number(),
            None => Err("意外的输入结束".into()),
        }
    }

    fn lit(&mut self, word: &str, v: Json) -> Result<Json, String> {
        if self.b[self.i..].starts_with(word.as_bytes()) {
            self.i += word.len();
            Ok(v)
        } else {
            Err(format!("期望 {} @{}", word, self.i))
        }
    }

    fn object(&mut self) -> Result<Json, String> {
        self.i += 1; // {
        let mut m = Vec::new();
        self.ws();
        if self.peek() == Some(b'}') {
            self.i += 1;
            return Ok(Json::Obj(m));
        }
        loop {
            self.ws();
            let k = self.string()?;
            self.ws();
            if self.peek() != Some(b':') {
                return Err(format!("对象缺冒号 @{}", self.i));
            }
            self.i += 1;
            self.ws();
            let v = self.value()?;
            m.push((k, v));
            self.ws();
            match self.peek() {
                Some(b',') => {
                    self.i += 1;
                }
                Some(b'}') => {
                    self.i += 1;
                    return Ok(Json::Obj(m));
                }
                _ => return Err(format!("对象缺 , 或 }} @{}", self.i)),
            }
        }
    }

    fn array(&mut self) -> Result<Json, String> {
        self.i += 1; // [
        let mut a = Vec::new();
        self.ws();
        if self.peek() == Some(b']') {
            self.i += 1;
            return Ok(Json::Arr(a));
        }
        loop {
            self.ws();
            a.push(self.value()?);
            self.ws();
            match self.peek() {
                Some(b',') => {
                    self.i += 1;
                }
                Some(b']') => {
                    self.i += 1;
                    return Ok(Json::Arr(a));
                }
                _ => return Err(format!("数组缺 , 或 ] @{}", self.i)),
            }
        }
    }

    fn string(&mut self) -> Result<String, String> {
        if self.peek() != Some(b'"') {
            return Err(format!("期望字符串 @{}", self.i));
        }
        self.i += 1;
        let mut buf: Vec<u8> = Vec::new();
        loop {
            let c = self.peek().ok_or("字符串未闭合")?;
            self.i += 1;
            match c {
                b'"' => {
                    return String::from_utf8(buf).map_err(|e| format!("非法 UTF-8: {}", e));
                }
                b'\\' => {
                    let e = self.peek().ok_or("转义未完成")?;
                    self.i += 1;
                    match e {
                        b'"' => buf.push(b'"'),
                        b'\\' => buf.push(b'\\'),
                        b'/' => buf.push(b'/'),
                        b'b' => buf.push(0x08),
                        b'f' => buf.push(0x0c),
                        b'n' => buf.push(b'\n'),
                        b'r' => buf.push(b'\r'),
                        b't' => buf.push(b'\t'),
                        b'u' => {
                            let cp = self.hex4()?;
                            // 代理对：\uD83D\uDE00 这类必须合并，否则中文/emoji 帧会被解坏
                            if (0xD800..0xDC00).contains(&cp) {
                                if self.peek() == Some(b'\\') {
                                    self.i += 1;
                                    if self.peek() == Some(b'u') {
                                        self.i += 1;
                                        let lo = self.hex4()?;
                                        let c = 0x10000
                                            + ((cp - 0xD800) << 10)
                                            + (lo.wrapping_sub(0xDC00));
                                        let ch = char::from_u32(c)
                                            .ok_or_else(|| format!("非法代理对 {:#x}", c))?;
                                        let mut tmp = [0u8; 4];
                                        buf.extend_from_slice(ch.encode_utf8(&mut tmp).as_bytes());
                                        continue;
                                    }
                                }
                                return Err("孤立的高代理".into());
                            }
                            let ch = char::from_u32(cp).ok_or("非法码点")?;
                            let mut tmp = [0u8; 4];
                            buf.extend_from_slice(ch.encode_utf8(&mut tmp).as_bytes());
                        }
                        other => return Err(format!("不认识的转义 \\{}", other as char)),
                    }
                }
                _ => buf.push(c),
            }
        }
    }

    fn hex4(&mut self) -> Result<u32, String> {
        if self.i + 4 > self.b.len() {
            return Err("\\u 需要 4 位十六进制".into());
        }
        let s = std::str::from_utf8(&self.b[self.i..self.i + 4]).map_err(|e| e.to_string())?;
        let v = u32::from_str_radix(s, 16).map_err(|_| format!("非法 \\u{}", s))?;
        self.i += 4;
        Ok(v)
    }

    fn number(&mut self) -> Result<Json, String> {
        let start = self.i;
        if self.peek() == Some(b'-') {
            self.i += 1;
        }
        while matches!(self.peek(), Some(c) if c.is_ascii_digit() || c == b'.' || c == b'e' || c == b'E' || c == b'+' || c == b'-')
        {
            self.i += 1;
        }
        if start == self.i {
            return Err(format!("期望值 @{}", self.i));
        }
        let s = std::str::from_utf8(&self.b[start..self.i]).map_err(|e| e.to_string())?;
        s.parse::<f64>()
            .map(Json::Num)
            .map_err(|e| format!("非法数字 {}: {}", s, e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_cjk() {
        let s = r#"{"v":1,"type":"req","params":{"text":"帮我看看 core/archive.py","n":3}}"#;
        let v = Json::parse(s).unwrap();
        assert_eq!(v.get("v").unwrap().as_f64(), Some(1.0));
        assert_eq!(
            v.get("params").unwrap().get("text").unwrap().as_str(),
            Some("帮我看看 core/archive.py")
        );
        assert_eq!(Json::parse(&v.dump()).unwrap(), v);
    }

    #[test]
    fn escapes_and_surrogates() {
        let v = Json::parse(r#""a\u4e2d\ud83d\ude00\n\t\"\\""#).unwrap();
        assert_eq!(v.as_str(), Some("a中😀\n\t\"\\"));
    }

    #[test]
    fn rejects_trailing_and_bad() {
        assert!(Json::parse("{}x").is_err());
        assert!(Json::parse("{\"a\":}").is_err());
        assert!(Json::parse("[1,]").is_err());
    }
}
