//! SimHash 与记忆召回 —— `core/archive.py` 的逐位等价实现。
//!
//! ## 兼容契约（重要）
//!
//! 对齐的是 **ACE 当前实现**，不是上游 `aitoolkit-main/Toolkit/核心代码/Archive.py`：
//!
//! | | 上游原版 | ACE 现行（本文件对齐） |
//! |---|---|---|
//! | 分词 | `jieba.cut` 或逐字符 | `w:` 拉丁词 · `c:` 中文整段 · `b:` 中文二元组 |
//! | 取哈希 | `int(md5hex, 16)`（128 位取低位） | `int.from_bytes(md5(tok)[:8], "big")`（前 8 字节大端） |
//! | 权重 | 词频 | 每 token ±1（重复 token 自然累加） |
//!
//! 走错任何一条，已落的 `.agent_memory.json` 指纹就全部失配 —— 那是**持久化数据**
//! （`MemoryEntry.simhash`），不是可重建的缓存。所以这里有已知向量测试，
//! 另有 `engine/tools/xcheck.py` 与 Python `core/archive.py` 逐条对拍。

use crate::md5;
use std::collections::HashSet;

pub const SIMHASH_BITS: u32 = 64;

/// 与 `core/archive.py:_tokenize` 同口径、同顺序：先拉丁词，再中文段与其二元组。
///
/// `lru_cache` 在 Python 侧做的那层缓存，在引擎里由「索引构建时算一次」取代。
pub fn tokenize(text: &str) -> Vec<String> {
    let lowered = text.to_lowercase();
    let mut tokens: Vec<String> = Vec::new();

    // ① [a-z0-9_]+ —— 注意是**降级后**的 ASCII 小写/数字/下划线，其它字符都是分隔符
    let mut run = String::new();
    for c in lowered.chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' {
            run.push(c);
        } else if !run.is_empty() {
            tokens.push(format!("w:{}", run));
            run.clear();
        }
    }
    if !run.is_empty() {
        tokens.push(format!("w:{}", run));
    }

    // ② [\u4e00-\u9fff]+ —— 中文段整段一个 token，再补相邻二元组
    let chars: Vec<char> = text.chars().collect();
    let mut i = 0usize;
    while i < chars.len() {
        if is_cjk(chars[i]) {
            let start = i;
            while i < chars.len() && is_cjk(chars[i]) {
                i += 1;
            }
            let seg: String = chars[start..i].iter().collect();
            tokens.push(format!("c:{}", seg));
            let sc: Vec<char> = seg.chars().collect();
            for k in 0..sc.len().saturating_sub(1) {
                tokens.push(format!("b:{}{}", sc[k], sc[k + 1]));
            }
        } else {
            i += 1;
        }
    }

    if tokens.is_empty() {
        tokens.push("empty".to_string());
    }
    tokens
}

#[inline]
fn is_cjk(c: char) -> bool {
    ('\u{4e00}'..='\u{9fff}').contains(&c)
}

/// 64 位 SimHash 指纹（与 `core/archive.py:simhash` 逐位一致）。
pub fn simhash(text: &str) -> u64 {
    let mut weights = [0i32; SIMHASH_BITS as usize];
    for tok in tokenize(text) {
        let h = md5::hash64(&tok);
        for (i, w) in weights.iter_mut().enumerate() {
            if (h >> i) & 1 == 1 {
                *w += 1;
            } else {
                *w -= 1;
            }
        }
    }
    let mut fp = 0u64;
    for (i, w) in weights.iter().enumerate() {
        if *w > 0 {
            fp |= 1u64 << i;
        }
    }
    fp
}

#[inline]
pub fn hamming(a: u64, b: u64) -> u32 {
    (a ^ b).count_ones()
}

#[inline]
pub fn similarity(a: u64, b: u64) -> f64 {
    1.0 - hamming(a, b) as f64 / SIMHASH_BITS as f64
}

/// 协议里的指纹一律走 16 位十六进制：64 位整数超出 JSON 数字（f64）的精度。
#[inline]
pub fn hex16(fp: u64) -> String {
    format!("{:016x}", fp)
}

/// 主题相似度：token 集包含系数（对短中文比位差稳定，与 Python 同式）。
pub fn text_similarity_tokens(a: &HashSet<String>, b: &HashSet<String>) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let inter = a.intersection(b).count();
    inter as f64 / a.len().min(b.len()) as f64
}

pub fn text_similarity(a: &str, b: &str) -> f64 {
    let ta: HashSet<String> = tokenize(a).into_iter().collect();
    let tb: HashSet<String> = tokenize(b).into_iter().collect();
    text_similarity_tokens(&ta, &tb)
}

/// 与 Python `round(x, 4)` 同口径（响应里直接给这个值，便于逐字节对拍）。
#[inline]
pub fn round4(x: f64) -> f64 {
    (x * 10000.0).round() / 10000.0
}

// ---------------------------------------------------------------- 记忆索引

pub struct Entry {
    pub id: String,
    pub text: String,
    pub weight: f64,
    pub session: String,
    /// 建索引时算好一次。Python 侧每条记忆每轮都重建这个集合（O(N) 次/轮），
    /// 那是这套移植里最大的一处浪费。
    pub tokens: HashSet<String>,
}

#[derive(Default)]
pub struct Index {
    pub entries: Vec<Entry>,
}

pub struct Hit {
    pub index: usize,
    pub id: String,
    pub similarity: f64,
    pub score: f64,
}

impl Index {
    pub fn build(items: Vec<(String, String, f64, String)>) -> Index {
        let entries = items
            .into_iter()
            .map(|(id, text, weight, session)| Entry {
                tokens: tokenize(&text).into_iter().collect(),
                id,
                text,
                weight,
                session,
            })
            .collect();
        Index { entries }
    }

    pub fn clear(&mut self) {
        self.entries.clear();
    }

    pub fn sessions(&self) -> usize {
        self.entries
            .iter()
            .map(|e| e.session.as_str())
            .collect::<HashSet<_>>()
            .len()
    }

    pub fn total_tokens(&self) -> usize {
        self.entries.iter().map(|e| e.tokens.len()).sum()
    }

    /// 与 `MemoryArchive.get_memory` 同口径，逐条对齐：
    ///
    /// 1. 只取本会话的条目；
    /// 2. `exclude_last` 且会话内多于一条 → 去掉**最后一条**（刚写入的当前消息）；
    /// 3. 逐条 `text_similarity(entry.text, anchor) × weight`（anchor = query 或会话主题文本）；
    /// 4. 降序排序 —— Python 的 `list.sort` 是稳定的，这里也用稳定排序，
    ///    同分时保持插入序，否则同一份记忆在两个实现里的 top_k 顺序会不一样；
    /// 5. **先取 top_k 再 `score <= 0` 截断**（Python 是 `for ... in ranked[:top_k]: if score <= 0: break`，
    ///    顺序不能反：反了会把本该出局的负分条目算进来）。
    pub fn recall(
        &self,
        query: &str,
        anchor_text: &str,
        session: &str,
        top_k: usize,
        exclude_last: bool,
    ) -> Vec<Hit> {
        let anchor = if !query.is_empty() { query } else { anchor_text };
        let q: HashSet<String> = tokenize(anchor).into_iter().collect();

        // 保留原始下标：命中要回填 id，而 hot 路径上不想克隆文本
        let mut pool: Vec<usize> = self
            .entries
            .iter()
            .enumerate()
            .filter(|(_, e)| e.session == session)
            .map(|(i, _)| i)
            .collect();
        if exclude_last && pool.len() > 1 {
            pool.pop();
        }

        let mut ranked: Vec<(f64, f64, usize)> = pool
            .iter()
            .map(|&idx| {
                let e = &self.entries[idx];
                let sim = text_similarity_tokens(&e.tokens, &q);
                (sim * e.weight, sim, idx)
            })
            .collect();
        ranked.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

        ranked
            .into_iter()
            .take(top_k)
            .take_while(|(score, _, _)| *score > 0.0)
            .map(|(score, sim, idx)| Hit {
                index: idx,
                id: self.entries[idx].id.clone(),
                similarity: round4(sim),
                score: round4(score),
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 期望值由 Python `core/archive.py` 真实输出（不是手算）
    const VECTORS: &[(&str, u64)] = &[
        ("", 11737649648288100995),
        ("a", 902332835127167023),
        ("abc", 15361235203677470413),
        ("hello world", 5765100138621059808),
        ("帮我看看 core/archive.py", 7684662373562993300),
        ("中文测试", 649231931310923910),
        ("SimHash 中文 test_1", 588713872362438784),
    ];

    #[test]
    fn simhash_matches_python() {
        for (text, expect) in VECTORS {
            assert_eq!(simhash(text), *expect, "simhash({:?})", text);
        }
    }

    #[test]
    fn hex_is_16_chars() {
        for (text, expect) in VECTORS {
            assert_eq!(hex16(simhash(text)), format!("{:016x}", expect));
        }
    }

    #[test]
    fn tokenize_order_matches_python() {
        assert_eq!(tokenize(""), vec!["empty"]);
        assert_eq!(tokenize("hello world"), vec!["w:hello", "w:world"]);
        assert_eq!(
            tokenize("帮我看看 core/archive.py"),
            vec!["w:core", "w:archive", "w:py", "c:帮我看看", "b:帮我", "b:我看", "b:看看"]
        );
        assert_eq!(
            tokenize("中文测试"),
            vec!["c:中文测试", "b:中文", "b:文测", "b:测试"]
        );
    }

    #[test]
    fn similarity_bounds() {
        assert_eq!(similarity(0, 0), 1.0);
        assert_eq!(hamming(0, u64::MAX), 64);
        assert!(text_similarity("abc", "abc") == 1.0);
        assert!(text_similarity("中文测试", "完全不同的英文") == 0.0);
    }
}
