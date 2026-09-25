/**
 * vim 子集的**差分测试** —— 同一批 `(文本, 光标, 键序列)` 同时喂给 Python 与 TS，
 * 逐条比对 `(文本, 光标, 模式, note, 寄存器)`。
 *
 * ## 为什么非要做差分，而不是写几十条我自己的断言
 *
 * 我自己的断言只能证明"我的实现符合我以为的语义"；而 vim 键位是**肌肉记忆**，
 * 用户按 `ciw` 期望删掉光标下的词 —— 如果我把它理解成别的范围，他不会看到错误，
 * 只会看到**自己刚写的一段被删错**（而且没有撤销栈可退）。
 * 只有跟真实现逐条对答案，才能证明"两边一样"，而不是"我抄得挺像"。
 *
 * 语料覆盖：motions / 操作符+motion / 文本对象 / 单键操作 / 计数 / 模式切换 / 边界 / 非法键。
 */

import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  MOTIONS,
  TEXT_OBJECTS,
  VimError,
  VimLineEditor,
  parseCommand,
  textObject,
  wordSpans,
} from '../src/render/vim.js';
import { resolvePython } from '../src/protocol/client.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PY = resolvePython();

/** [文本, 起始光标, 键序列] */
type Case = [string, number, string[]];

const CASES: Case[] = [
  // —— 纯 motion ——
  ['hello world', 0, ['l', 'l']],
  ['hello world', 6, ['h']],
  ['hello world', 0, ['w']],
  ['hello world', 6, ['w']],
  ['hello world', 0, ['b']],
  ['hello world', 11, ['b']],
  ['hello world', 0, ['e']],
  ['hello world', 0, ['0']],
  ['hello world', 5, ['$']],
  ['hello world', 5, ['g', 'g']],
  ['hello world', 5, ['G']],
  ['hello world', 0, ['3', 'w']],
  ['甲乙 丙丁 戊', 0, ['w']],

  // —— 操作符 + motion ——
  ['hello world', 0, ['d', 'w']],
  ['hello world', 6, ['d', 'w']],
  ['hello world', 5, ['d', '$']],
  ['hello world', 5, ['d', '0']],
  ['hello world', 5, ['d', 'h']],
  ['hello world', 5, ['d', 'l']],
  ['hello world', 0, ['d', '2', 'w']],
  ['hello world', 0, ['2', 'd', 'w']],
  ['hello world', 5, ['c', 'w']],
  ['hello world', 0, ['y', 'w']],
  ['hello world', 0, ['c', '$']],

  // —— 单键操作 ——
  ['hello', 0, ['x']],
  ['hello', 4, ['x']],
  ['hello', 2, ['D']],
  ['hello', 2, ['C']],
  ['hello', 0, ['3', 'x']],
  ['hello', 0, ['d', 'd']],
  ['hello', 0, ['y', 'y']],
  ['hello', 0, ['c', 'c']],
  ['hello', 3, ['2', 'd', 'd']],

  // —— 文本对象 ——
  ['say "hi" now', 5, ['d', 'i', '"']],
  ['say "hi" now', 5, ['d', 'a', '"']],
  ['say "hi" now', 5, ['c', 'i', '"']],
  ['say (a b) end', 5, ['d', 'i', '(']],
  ['say (a b) end', 5, ['d', 'a', '(']],
  ['hello world', 2, ['d', 'i', 'w']],
  ['hello world', 2, ['d', 'a', 'w']],
  ['hello world', 2, ['c', 'i', 'w']],
  ['hello world', 0, ['y', 'i', 'w']],
  ['no quotes here', 5, ['d', 'i', '"']], // 找不到对象：不该删东西
  ['one', 0, ['d', 'i', 'p']],
  ['one', 0, ['d', 'a', 'p']],

  // —— 模式切换 ——
  ['hello', 0, ['i']],
  ['hello', 0, ['i', 'Escape']],
  ['hello', 0, ['A']],
  ['hello', 0, ['A', 'Escape']],
  ['hello', 3, ['I']],
  ['hello', 0, ['d', 'w', 'i']], // 删除后进插入
  ['hello world', 0, ['c', 'w', 'Escape']],

  // —— 非法 / 不完整 ——
  ['hello', 0, ['z', 'z']],
  ['hello', 0, ['d']], // 停在 pending
  ['hello', 0, ['d', '2']],
  ['hello', 0, ['y']],
  ['hello', 0, ['d', 'q']],

  // —— 边界 ——
  ['', 0, ['h']],
  ['', 0, ['l']],
  ['', 0, ['d', 'w']],
  ['', 0, ['x']],
  ['a', 0, ['x']],
  ['a', 1, ['h']],
  ['a', 5, ['h']], // 光标越界（夹住）
  ['hello', 99, ['d', '$']],
  ['', 0, ['i', 'Escape']],
  ['   ', 0, ['w']],
  ['   ', 0, ['d', 'w']],
];

/** 用 Python 跑一遍全部用例。 */
function pythonRun(cases: Case[]): string[][] | null {
  const script = [
    'import sys, json',
    'from ui import ace_vim as V',
    'cases = json.loads(sys.stdin.read())',
    'out = []',
    'for text, cur, keys in cases:',
    '    ed = V.VimLineEditor(text, cur, True)',
    '    for k in keys:',
    '        ed.feed(k)',
    '    out.append([ed.text, str(ed.cursor), ed.mode, ed.last_note, ed.register])',
    'print(json.dumps(out, ensure_ascii=False))',
  ].join('\n');
  try {
    const out = execFileSync(PY, ['-c', script], {
      cwd: ROOT,
      input: JSON.stringify(cases),
      encoding: 'utf-8',
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
      timeout: 120_000,
    });
    return JSON.parse(out.trim()) as string[][];
  } catch {
    return null;
  }
}

/** 用 TS 跑一遍全部用例（驱动方式与 Python 侧的 `feed` 逐键一致）。 */
function tsRun(cases: Case[]): string[][] {
  return cases.map(([text, cur, keys]) => {
    const ed = new VimLineEditor(text, cur, true);
    for (const k of keys) ed.feed(k);
    return [ed.text, String(ed.cursor), ed.mode, ed.lastNote, ed.register];
  });
}

describe('与 ui/ace_vim 逐条差分', () => {
  const py = pythonRun(CASES);

  it('语料本身够大且有效（否则下面的比对可能空转）', () => {
    expect(CASES.length).toBeGreaterThan(50);
  });

  it.skipIf(py === null)('**每一条用例的 (文本, 光标, 模式, note, 寄存器) 都相同**', () => {
    expect(py, '没拿到 Python 的结果').not.toBeNull();
    const mine = tsRun(CASES);
    expect(py!.length).toBe(CASES.length);
    const diffs: string[] = [];
    for (let i = 0; i < CASES.length; i++) {
      const [text, cur, keys] = CASES[i]!;
      if (JSON.stringify(mine[i]) !== JSON.stringify(py![i])) {
        diffs.push(
          `用例 ${i}: 文本=${JSON.stringify(text)} 光标=${cur} 键=${keys.join('')}\n` +
            `  Python=${JSON.stringify(py![i])}\n  TS    =${JSON.stringify(mine[i])}`,
        );
      }
    }
    expect(diffs.slice(0, 8).join('\n')).toBe('');
  });
});

describe('文本对象（纯函数）', () => {
  it('iw / aw：词内', () => {
    expect(textObject('hello world', 2, 'iw')).toEqual([0, 5]);
    expect(textObject('hello world', 2, 'aw')).toEqual([0, 6]); // a 含尾随空白
  });

  it('光标紧贴词尾也算在这个词上', () => {
    expect(textObject('hello world', 5, 'iw')).toEqual([0, 5]);
  });

  it('引号：i 不含引号、a 含', () => {
    expect(textObject('say "hi" now', 5, 'i"')).toEqual([5, 7]);
    expect(textObject('say "hi" now', 5, 'a"')).toEqual([4, 8]);
  });

  it('**没有成对符号时返回 null**（调用方给提示，不静默删错东西）', () => {
    expect(textObject('no quotes here', 5, 'i"')).toBeNull();
    expect(textObject('hello', 2, 'i(')).toBeNull();
  });

  it('ip / ap 在单行里等于全选', () => {
    expect(textObject('one', 0, 'ip')).toEqual([0, 3]);
  });

  it('认不出的对象返回 null', () => {
    expect(textObject('abc', 1, 'iz')).toBeNull();
    expect(textObject('abc', 1, 'i')).toBeNull();
  });
});

describe('词切分', () => {
  it('字母数字下划线一串算一个词', () => {
    expect(wordSpans('hello world')).toEqual([
      [0, 5],
      [6, 11],
    ]);
  });

  it('标点各算一段（中文按字切）', () => {
    expect(wordSpans('a,b')).toEqual([
      [0, 1],
      [1, 2],
      [2, 3],
    ]);
  });

  it('空白跳过', () => {
    expect(wordSpans('   ')).toEqual([]);
  });
});

describe('命令解析', () => {
  it('计数 × 操作符 × 计数', () => {
    expect(parseCommand('2d3w')).toEqual([6, 'd', 'w']);
  });

  it('`dd` 这类"操作符后面没跟目标"= 整行', () => {
    expect(parseCommand('dd')).toEqual([1, 'd', 'd']);
    expect(parseCommand('2yy')).toEqual([2, 'y', 'y']);
  });

  it('未绑定的动作/目标抛错', () => {
    expect(() => parseCommand('zz')).toThrow(VimError);
    expect(() => parseCommand('dq')).toThrow(VimError);
  });

  it('motion 与文本对象表与 Python 侧同名', () => {
    expect(Object.keys(MOTIONS).sort()).toEqual(['$', '0', 'G', 'b', 'e', 'gg', 'h', 'l', 'w']);
    expect(TEXT_OBJECTS).toHaveLength(14);
  });
});
