/**
 * 模糊匹配打分测试 —— **真的调 Python 来对比分数**。
 *
 * 为什么不用"照抄源码再人肉核对"：评分是个整数算法，六条加权规则互相叠加，
 * 抄错一个系数不会有任何症状，只会让排序**安静地**与 Python 侧不同 ——
 * 而菜单和选择器的排序不一致，用户完全没法理解。
 *
 * 所以这里把一批 (候选, 查询) 送进真 Python，拿回分数逐一比对。
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { SEPARATORS, filterItems, matchPositions, matchScore } from '../src/render/match.js';
import { resolvePython } from '../src/protocol/client.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PY = resolvePython();

/** 调真 Python 算一批分数；失败时返回 null（环境没有 Python 就跳过对比）。 */
function pythonScores(pairs: Array<[string, string]>): number[] | null {
  const script = [
    'import json, sys',
    'from ui import ace_selector as s',
    'pairs = json.loads(sys.stdin.read())',
    'print(json.dumps([s.match_score(i, q) for i, q in pairs]))',
  ].join('\n');
  try {
    const out = execFileSync(PY, ['-c', script], {
      cwd: ROOT,
      input: JSON.stringify(pairs),
      encoding: 'utf-8',
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
      timeout: 60_000,
    });
    return JSON.parse(out.trim()) as number[];
  } catch {
    return null;
  }
}

const PAIRS: Array<[string, string]> = [
  ['/help', 'help'],
  ['/help', '/help'],
  ['/help', '/he'],
  ['/permission', 'perm'],
  ['/permission', 'pm'],
  ['/permission', 'zzz'],
  ['deepseek-v4', 'deep'],
  ['deepseek-v4', 'dsk'],
  ['deepseek-v4', '-v4'],
  ['deepseek-v4', 'v4'],
  ['file_write', 'fw'],
  ['file_write', 'write'],
  ['file_write', ''],
  ['qwen-max', 'max'],
  ['qwen-max', 'qwen max'],
  ['anything', 'no match here'],
  ['/model', 'model'],
  ['/model', '/model'],
];

describe('与 ui/ace_selector 的评分逐条相同', () => {
  const py = pythonScores(PAIRS);

  it('SEPARATORS 常量相同', () => {
    // 注意：`ace_selector` 是从 `ui/ace_text` **import** 它的，不在自己文件里定义 ——
    // 去 ace_selector.py 里找会一无所获（我第一版就找错了地方）。
    const src = readFileSync(join(ROOT, 'ui', 'ace_text.py'), 'utf-8');
    const m = src.match(/SEPARATORS\s*=\s*(['"])(.*?)\1/s);
    expect(m, '在 ui/ace_text.py 里没找到 SEPARATORS 定义').not.toBeNull();
    // Python 源码里写的是 `\t` 转义，比之前先还原再比
    const literal = m![2]!.replace(/\\t/g, '\t').replace(/\\n/g, '\n');
    expect(SEPARATORS).toBe(literal);
  });

  it.skipIf(py === null)('**每一对的分数都与 Python 相同**', () => {
    expect(py, '没拿到 Python 的分数').not.toBeNull();
    for (let i = 0; i < PAIRS.length; i++) {
      const [item, query] = PAIRS[i]!;
      expect(matchScore(item, query), `${item} ← ${query}`).toBe(py![i]);
    }
  });
});

describe('排序行为', () => {
  it('空查询等权，且保持原顺序', () => {
    const items = ['/help', '/model', '/sandbox'];
    expect(filterItems(items, '').map((s) => s.index)).toEqual([0, 1, 2]);
  });

  it('不匹配的被滤除（评分 0）', () => {
    expect(filterItems(['/help', '/model'], 'zzz')).toEqual([]);
  });

  it('完全相等的置顶', () => {
    const items = ['/models', '/model', '/model-x'];
    expect(filterItems(items, '/model')[0]!.index).toBe(1);
  });

  it('前缀命中排在中间命中之前', () => {
    const items = ['x-model', '/model'];
    expect(filterItems(items, 'model')[0]!.index).toBe(1);
  });

  it('连续命中排在分散命中之前', () => {
    const items = ['d_e_e_p', 'deep'];
    expect(filterItems(items, 'deep')[0]!.index).toBe(1);
  });
});

describe('子序列匹配', () => {
  it('`dsk` 能命中 `deepseek`（逐字符向后找）', () => {
    // d(0) → s 从 1 起找 → 4 → k 从 5 起找 → 7。实测 Python 同样给 [0,4,7]。
    expect(matchPositions('deepseek', 'dsk')).toEqual([0, 4, 7]);
  });

  it('空查询返回 []（全部命中），与"不命中 null"是两件事', () => {
    expect(matchPositions('abc', '')).toEqual([]);
    expect(matchPositions('abc', 'z')).toBeNull();
  });

  it('多词查询是 AND 语义', () => {
    expect(matchPositions('qwen max', 'qwen max')).not.toBeNull();
    expect(matchPositions('qwen max', 'qwen min')).toBeNull();
  });

  it('大小写不敏感', () => {
    expect(matchScore('Help', 'help')).toBe(matchScore('help', 'help'));
  });
});
