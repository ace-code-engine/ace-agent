/**
 * 终端显示宽度 —— 逐条对齐 `ui/ace_text.py`。
 *
 * ## 为什么不能直接用 `.length`
 *
 * JS 的 `str.length` 数的是**码点**，终端数的是**列**。一个汉字占两列、组合符占零列。
 * 用 `.length` 排版的话：卡片右边框对不齐、截断会把汉字劈成半个、并排两栏的右栏
 * 会随中文说明的长度左右漂。这些错都不会报异常，只会让界面**看着歪**。
 *
 * ## 与 Python 侧的差别（必须知道）
 *
 * 那边用 `unicodedata.east_asian_width()`；JS 没有这个 API，只能**列区间**。
 * 区间照 Unicode 的 East_Asian_Width=W/F 抄（CJK、谚文、全角标点、多数 emoji）。
 * 区间表可能跟不上 Unicode 新增字符 —— 所以有**差分测试**：扫一遍码点，与真 Python
 * 逐个比对 `char_width`，不一致的就报出来。（`test/text.test.ts`）
 *
 * 口径刻意与那边一致的两条近似：
 *   - **Ambiguous（A）类按 1 列**（含省略号 `…`）—— 极窄限宽下可能差 1 列，可接受；
 *   - 不做 wcwidth 级别的完整实现（零依赖是硬约束）。
 */

/** SGR 颜色/样式序列。与 `ace_text._ANSI_SGR` 同口径（只处理 ESC[...m 这一类）。 */
const ANSI_SGR = /\x1b\[[0-9;]*m/g;

export const ELLIPSIS = '…';

export function stripAnsi(text: string): string {
  return String(text ?? '').replace(ANSI_SGR, '');
}

/**
 * 零宽字符（与 `ace_text._ZERO_WIDTH` 同一类：零宽空格/连接符、双向控制符、BOM 等）。
 *
 * **必须写成 `\u` 转义，不能粘字面字符** —— 那一批里含 U+2028/U+2029（行分隔符），
 * 字面粘进来会把正则字面量当场截断，报的是"未终止的正则"（踩过）。
 * 漏没漏由 `test/text.test.ts` 的码点差分兜底。
 */
const ZERO_WIDTH_RE = /[\u200b-\u200f\u2060\ufeff]/;

/** 组合符（Mn / Me）——`\p{...}` 需要 u 标志，Node 支持。 */
const MARK_RE = /\p{Mn}|\p{Me}/u;

/**
 * East_Asian_Width = W/F 的码点区间。
 * 抄自 Unicode 的 EastAsianWidth.txt（宽 / 全角部分）。
 */
const WIDE_RANGES: ReadonlyArray<readonly [number, number]> = [
  // ↓↓↓ 由 scripts 从 Python 的 unicodedata 生成，**别手改** ↓↓↓
  // 手抄必错（第一版就抄窄了 emoji、抄宽了带圈数字），差分测试会当场抓。
  // 重新生成：见 test/text.test.ts 顶部说明。
  [0x1100, 0x115f],
  [0x231a, 0x231b],
  [0x2329, 0x232a],
  [0x23e9, 0x23ec],
  [0x23f0, 0x23f0],
  [0x23f3, 0x23f3],
  [0x25fd, 0x25fe],
  [0x2614, 0x2615],
  [0x2648, 0x2653],
  [0x267f, 0x267f],
  [0x2693, 0x2693],
  [0x26a1, 0x26a1],
  [0x26aa, 0x26ab],
  [0x26bd, 0x26be],
  [0x26c4, 0x26c5],
  [0x26ce, 0x26ce],
  [0x26d4, 0x26d4],
  [0x26ea, 0x26ea],
  [0x26f2, 0x26f3],
  [0x26f5, 0x26f5],
  [0x26fa, 0x26fa],
  [0x26fd, 0x26fd],
  [0x2705, 0x2705],
  [0x270a, 0x270b],
  [0x2728, 0x2728],
  [0x274c, 0x274c],
  [0x274e, 0x274e],
  [0x2753, 0x2755],
  [0x2757, 0x2757],
  [0x2795, 0x2797],
  [0x27b0, 0x27b0],
  [0x27bf, 0x27bf],
  [0x2b1b, 0x2b1c],
  [0x2b50, 0x2b50],
  [0x2b55, 0x2b55],
  [0x2e80, 0x2e99],
  [0x2e9b, 0x2ef3],
  [0x2f00, 0x2fd5],
  [0x2ff0, 0x303e],
  [0x3041, 0x3096],
  [0x3099, 0x30ff],
  [0x3105, 0x312f],
  [0x3131, 0x318e],
  [0x3190, 0x31e3],
  [0x31ef, 0x321e],
  [0x3220, 0x3247],
  [0x3250, 0x4dbf],
  [0x4e00, 0xa48c],
  [0xa490, 0xa4c6],
  [0xa960, 0xa97c],
  [0xac00, 0xd7a3],
  [0xf900, 0xfaff],
  [0xfe10, 0xfe19],
  [0xfe30, 0xfe52],
  [0xfe54, 0xfe66],
  [0xfe68, 0xfe6b],
  [0xff01, 0xff60],
  [0xffe0, 0xffe6],
  [0x16fe0, 0x16fe4],
  [0x16ff0, 0x16ff1],
  [0x17000, 0x187f7],
  [0x18800, 0x18cd5],
  [0x18d00, 0x18d08],
  [0x1aff0, 0x1aff3],
  [0x1aff5, 0x1affb],
  [0x1affd, 0x1affe],
  [0x1b000, 0x1b122],
  [0x1b132, 0x1b132],
  [0x1b150, 0x1b152],
  [0x1b155, 0x1b155],
  [0x1b164, 0x1b167],
  [0x1b170, 0x1b2fb],
  [0x1f004, 0x1f004],
  [0x1f0cf, 0x1f0cf],
  [0x1f18e, 0x1f18e],
  [0x1f191, 0x1f19a],
  [0x1f200, 0x1f202],
  [0x1f210, 0x1f23b],
  [0x1f240, 0x1f248],
  [0x1f250, 0x1f251],
  [0x1f260, 0x1f265],
  [0x1f300, 0x1f320],
  [0x1f32d, 0x1f335],
  [0x1f337, 0x1f37c],
  [0x1f37e, 0x1f393],
  [0x1f3a0, 0x1f3ca],
  [0x1f3cf, 0x1f3d3],
  [0x1f3e0, 0x1f3f0],
  [0x1f3f4, 0x1f3f4],
  [0x1f3f8, 0x1f43e],
  [0x1f440, 0x1f440],
  [0x1f442, 0x1f4fc],
  [0x1f4ff, 0x1f53d],
  [0x1f54b, 0x1f54e],
  [0x1f550, 0x1f567],
  [0x1f57a, 0x1f57a],
  [0x1f595, 0x1f596],
  [0x1f5a4, 0x1f5a4],
  [0x1f5fb, 0x1f64f],
  [0x1f680, 0x1f6c5],
  [0x1f6cc, 0x1f6cc],
  [0x1f6d0, 0x1f6d2],
  [0x1f6d5, 0x1f6d7],
  [0x1f6dc, 0x1f6df],
  [0x1f6eb, 0x1f6ec],
  [0x1f6f4, 0x1f6fc],
  [0x1f7e0, 0x1f7eb],
  [0x1f7f0, 0x1f7f0],
  [0x1f90c, 0x1f93a],
  [0x1f93c, 0x1f945],
  [0x1f947, 0x1f9ff],
  [0x1fa70, 0x1fa7c],
  [0x1fa80, 0x1fa88],
  [0x1fa90, 0x1fabd],
  [0x1fabf, 0x1fac5],
  [0x1face, 0x1fadb],
  [0x1fae0, 0x1fae8],
  [0x1faf0, 0x1faf8],
  [0x20000, 0x2fffd],
  [0x30000, 0x3fffd],
];

function inWide(cp: number): boolean {
  // 二分：区间表有序
  let lo = 0;
  let hi = WIDE_RANGES.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const [a, b] = WIDE_RANGES[mid]!;
    if (cp < a) hi = mid - 1;
    else if (cp > b) lo = mid + 1;
    else return true;
  }
  return false;
}

/** 单字符占几列。0 = 组合符/零宽；2 = 东亚宽；1 = 其余。 */
export function charWidth(ch: string): number {
  if (!ch) return 0;
  if (ZERO_WIDTH_RE.test(ch) || MARK_RE.test(ch)) return 0;
  const cp = ch.codePointAt(0)!;
  return inWide(cp) ? 2 : 1;
}

/** 整串的可见显示宽度（列数）；ANSI 颜色码不计入。 */
export function displayWidth(text: string): number {
  let w = 0;
  // 按码点遍历（`for...of` 会正确处理代理对），否则 emoji 会被拆成两个半字符
  for (const ch of stripAnsi(text ?? '')) w += charWidth(ch);
  return w;
}

/**
 * 按**显示宽度**截断到 limit 列，超长时尾部换成省略号。
 *
 * 与 Python 侧逐条一致：
 *   - `limit <= 0` → 空串
 *   - **放得下省略号才加省略号**，放不下就硬切（宁短不超）
 *   - **绝不把双宽字符劈成一半**（累计到放不下就停）
 *   - ANSI 零宽且原样保留；截断处补复位码，避免颜色漏到下一行
 */
export function truncateWidth(text: string, limit: number, ellipsis = ELLIPSIS): string {
  const lim = Math.trunc(limit);
  if (lim <= 0) return '';
  const s = String(text ?? '');
  if (displayWidth(s) <= lim) return s;

  const ellW = displayWidth(ellipsis);
  const useEllipsis = lim > ellW;
  const budget = useEllipsis ? lim - ellW : lim;

  let out = '';
  let used = 0;
  let colored = false;
  // 逐段走：ANSI 序列零宽、原样保留；其余按字符累计
  const re = /\x1b\[[0-9;]*m|[\s\S]/gu;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    const tok = m[0]!;
    if (tok.startsWith('\x1b[')) {
      out += tok;
      colored = true;
      continue;
    }
    const w = charWidth(tok);
    if (used + w > budget) break;
    out += tok;
    used += w;
  }
  return out + (useEllipsis ? ellipsis : '') + (colored ? '\x1b[0m' : '');
}

/** 按显示宽度补空格到指定列（够宽就原样返回，不截断）。 */
export function padWidth(text: string, width: number): string {
  const s = String(text ?? '');
  const w = displayWidth(s);
  return w >= width ? s : s + ' '.repeat(width - w);
}

/**
 * 左右两栏并排 —— 照抄 `ace_panel.side_by_side`（首屏 logo + 版本说明用的就是它）。
 *
 * 右栏对齐到**左栏最宽行**；`width > 0` 时整行按列截断，防止长说明把行宽撑爆 ——
 * 首屏每多一列都可能触发终端折行，进而把整个面板推歪。
 */
export function sideBySide(
  left: readonly string[],
  right: readonly string[],
  gap = 3,
  width = 0,
): string[] {
  const lw = Math.max(0, ...left.map((x) => displayWidth(x)));
  const out: string[] = [];
  const height = Math.max(left.length, right.length);
  for (let i = 0; i < height; i++) {
    const l = left[i] ?? '';
    const r = right[i] ?? '';
    const pad = ' '.repeat(Math.max(0, lw - displayWidth(l) + gap));
    let line = r ? `${l}${pad}${r}` : l;
    if (width > 0) line = truncateWidth(line, width);
    out.push(line.replace(/\s+$/, ''));
  }
  return out;
}
