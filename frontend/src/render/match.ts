/**
 * 模糊匹配打分 —— 逐条照抄 `ui/ace_selector.py` 的 `match_score` / `match_positions`。
 *
 * 为什么要一致而不另写一套：选择器（`/model`）和补全菜单（`/`）**共用同一套评分**
 * 是 Python 侧刻意的设计（`ace_menu` 的 docstring 写明"与选择器同一套评分"）。
 * 两套前端各用各的排序，用户会看到"同一个查询在菜单里排第 3、在选择器里排第 1"，
 * 而没有任何理由。
 *
 * 排序直觉（六条，都是踩出来的）：
 *   - 空查询：等权（1）
 *   - 完全相等：+5000 置顶
 *   - 每命中一字符基础 10 分
 *   - **连续命中**每个 +8：`deep` 命中 `deepseek` 该排在命中 `d_e_e_p` 的前面
 *   - **词边界命中**每个 +6：`-v4` 里的 v 比词中间那个 v 值钱
 *   - 越靠前、越集中越值钱（减去首命中下标、减去命中跨度）
 */

/** 与 `ace_selector.SEPARATORS` 逐字一致。 */
export const SEPARATORS = ' \t-_/.:,()[]{}<>|';

/**
 * 子序列匹配：返回命中字符的下标（升序、去重）；不命中返回 `null`。
 *
 * 空查询返回 `[]` —— 表示"全部命中"，与"不命中 null"是**两件事**，
 * 调用方必须分开处理（混起来会让空查询把候选全滤掉）。
 *
 * 多词查询按空格拆分，**每个词都必须命中**（AND 语义）。
 */
export function matchPositions(item: string, query: string): number[] | null {
  const q = String(query ?? '').trim().toLowerCase();
  if (!q) return [];
  const text = String(item ?? '').toLowerCase();
  const hits: number[] = [];
  for (const term of q.split(/\s+/)) {
    let start = 0;
    for (const ch of term) {
      const idx = text.indexOf(ch, start);
      if (idx < 0) return null;
      hits.push(idx);
      start = idx + 1;
    }
  }
  return [...new Set(hits)].sort((a, b) => a - b);
}

export function matchScore(item: string, query: string): number {
  const q = String(query ?? '').trim().toLowerCase();
  if (!q) return 1;
  const pos = matchPositions(item, q);
  if (pos === null) return 0;
  const text = String(item ?? '').toLowerCase();
  let score = 10 * pos.length;
  for (let i = 0; i < pos.length; i++) {
    const idx = pos[i]!;
    if (i > 0 && idx === pos[i - 1]! + 1) score += 8; // 连续命中
    if (idx === 0 || SEPARATORS.includes(text[idx - 1]!)) score += 6; // 词边界
  }
  score -= pos[0]!; // 越靠前越好
  score -= pos[pos.length - 1]! - pos[0]!; // 越集中越好
  if (text === q) score += 5000; // 完全相等置顶
  return score;
}

export interface Scored {
  index: number;
  score: number;
}

/**
 * 过滤并排序：返回 `[{index, score}]`，评分为 0 的被滤除。
 *
 * 按评分降序，**同分保持原顺序** —— 所以空查询时结果顺序 == 原列表顺序。
 * JS 的 `Array.prototype.sort` 自 ES2019 起是稳定的，这里依赖这一点
 * （降序要在同分时保持原序，就不能用 `b.score - a.score` 之外的花样）。
 */
export function filterItems(items: string[], query: string): Scored[] {
  const scored: Scored[] = items.map((it, i) => ({ index: i, score: matchScore(it, query) }));
  scored.sort((a, b) => b.score - a.score);
  return scored.filter((s) => s.score > 0);
}
