/**
 * diff 渲染 —— 逐条照抄 `ui/ace_diff.py` 的口径。
 *
 * 为什么"改动可见"比"命令可见"更要紧（那边文件头写的）：跑错一条命令当场就知道，
 * 改错一行往往几天后才发现。
 *
 * 三条从 Python 侧带过来的判据，都不是随便定的：
 *   1. `looksLikeDiff` **刻意保守** —— 要求 `@@` 或 `---`/`+++` 成对出现。
 *      工具输出里以 `+`/`-` 开头的行很常见（表格、列表、密码学），只按首字符判断
 *      会把普通输出误染成 diff。
 *   2. **文件头不计入增删** —— 否则每个 diff 都"删了一行、加了一行"，数字失去意义。
 *   3. **文件头按 dim 而非红绿** —— 它们不是"删了这行、加了那行"。
 *
 * 纯函数：不碰 Ink、不读宽度（宽度由调用方截断），所以可穷举测。
 */

/** 与 `ace_diff.MAX_DIFF_LINES` 一致。 */
export const MAX_DIFF_LINES = 200;

/** 主题 token 名（不是 ANSI 名）—— 由调用方喂给 `color()`。 */
export type DiffToken = 'success' | 'error' | 'info' | 'dim';

export interface DiffStat {
  added: number;
  removed: number;
  files: string[];
}

export function looksLikeDiff(text: unknown): boolean {
  if (typeof text !== 'string' || !text) return false;
  const lines = text.split(/\r?\n/);
  if (lines.some((l) => l.startsWith('@@'))) return true;
  const hasOld = lines.some((l) => l.startsWith('--- '));
  const hasNew = lines.some((l) => l.startsWith('+++ '));
  return hasOld && hasNew;
}

export function summarizeDiff(text: string): DiffStat {
  let added = 0;
  let removed = 0;
  const files: string[] = [];
  for (const ln of (text ?? '').split(/\r?\n/)) {
    if (ln.startsWith('+++ ') || ln.startsWith('--- ')) {
      const name = ln.slice(4).trim();
      if (name && name !== '/dev/null' && !files.includes(name)) {
        files.push(name.split('\t')[0]!);
      }
      continue;
    }
    if (ln.startsWith('@@')) continue;
    if (ln.startsWith('+')) added++;
    else if (ln.startsWith('-')) removed++;
  }
  return { added, removed, files };
}

/** 行首标记：`+` / `-` / `@` / ` ` / `?`（不是 diff 行）。 */
export function diffMarker(line: string): string {
  if (!line) return '?';
  const ch = line[0]!;
  return '+-@ '.includes(ch) ? ch : '?';
}

export function colorName(line: string): DiffToken {
  if (line.startsWith('--- ') || line.startsWith('+++ ')) return 'dim';
  switch (diffMarker(line)) {
    case '+':
      return 'success';
    case '-':
      return 'error';
    case '@':
      return 'info';
    default:
      return 'dim';
  }
}

export interface DiffLine {
  text: string;
  token: DiffToken;
}

/**
 * diff 文本 → 待渲染行 + 颜色 token。
 *
 * 超过 `maxLines` 时截断并**追加一行说明**（不冒充完整）—— 静默截断会让用户
 * 以为"就改了这些"。
 */
export function colorizeDiff(text: string, maxLines: number = MAX_DIFF_LINES): DiffLine[] {
  if (!text) return [];
  const lines = text.split(/\r?\n/);
  const capped = lines.length > maxLines;
  const shown = lines.slice(0, maxLines);
  const out: DiffLine[] = shown.map((l) => ({ text: l, token: colorName(l) }));
  if (capped) {
    out.push({ text: `… 还有 ${lines.length - maxLines} 行`, token: 'dim' });
  }
  return out;
}

/** 一行统计 `+3 -1`；无改动返回空串（让调用方不显示）。 */
export function statText(text: string): string {
  const s = summarizeDiff(text);
  if (!s.added && !s.removed) return '';
  return `+${s.added} -${s.removed}`;
}

export interface DiffHunk {
  header: string;
  added: number;
  removed: number;
}

export interface DiffFile {
  path: string;
  added: number;
  removed: number;
  hunks: DiffHunk[];
}

/**
 * 按文件切开 diff（两级视图的第一级）。
 *
 * 为什么要两级：一次改 5 个文件时几百行全铺出来，用户连"改了哪些文件"都看不出来。
 *
 * 路径取 `+++ ` 那行：删除文件时 `--- ` 是 `/dev/null`，拿它当路径会得到一个
 * 不存在的"文件名"。`b/` / `a/` 前缀要剥掉。
 */
export function splitByFile(text: string): DiffFile[] {
  const out: DiffFile[] = [];
  let cur: DiffFile | null = null;
  let hunk: DiffHunk | null = null;
  let seenNew = false;

  const newSection = (): DiffFile => {
    const sec: DiffFile = { path: '', added: 0, removed: 0, hunks: [] };
    out.push(sec);
    return sec;
  };

  for (const ln of (text ?? '').split(/\r?\n/)) {
    if (ln.startsWith('diff --git ') || (ln.startsWith('--- ') && seenNew)) {
      cur = newSection();
      hunk = null;
      seenNew = false;
    } else if (cur === null) {
      cur = newSection();
    }

    if (ln.startsWith('+++ ')) {
      let name = ln.slice(4).trim().split('\t')[0]!;
      if (name && name !== '/dev/null') {
        for (const px of ['b/', 'a/']) {
          if (name.startsWith(px)) {
            name = name.slice(px.length);
            break;
          }
        }
        cur.path = name;
      }
      seenNew = true;
      continue;
    }
    if (ln.startsWith('--- ')) continue;

    if (ln.startsWith('@@')) {
      hunk = { header: ln.trim(), added: 0, removed: 0 };
      cur.hunks.push(hunk);
      continue;
    }
    if (ln.startsWith('+')) {
      cur.added++;
      if (hunk) hunk.added++;
    } else if (ln.startsWith('-')) {
      cur.removed++;
      if (hunk) hunk.removed++;
    }
  }
  return out.filter((s) => s.path || s.hunks.length);
}
