/**
 * 等待指示器测试 —— 重点是**与 Python 侧逐条一致**。
 *
 * 为什么字形与速度必须一致：`ui/ace_spinner.py` 的注释写着「**速度本身是语义**」——
 * `waiting` 0.08s（等首字节，网络在动）、`reasoning` 0.24s（模型在推）、
 * `tool_running` 0.16s（工具在跑）。用户看速度判断"卡在哪一步"。
 * 两套前端各转各的，这条信息就废了。所以这里直接读那个 .py 比对。
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PHASE,
  GLYPHS,
  PHASES,
  frameAt,
  framesFor,
  phaseInterval,
} from '../src/render/spinner.js';
import { PHASE_VERB, verbKeyFor } from '../src/components/Spinner.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

interface PyGlyph {
  frames: string[];
  interval: number;
}

function pythonGlyphs(): { phases: string[]; default: string; glyphs: Record<string, PyGlyph> } {
  const src = readFileSync(join(ROOT, 'ui', 'ace_spinner.py'), 'utf-8');

  // 注意：那行带类型注解（`PHASES: Tuple[str, ...] = (...)`），所以 `PHASES\s*=` 匹配不到。
  // 写成 `PHASES[^=\n]*=` 才稳。
  const phases = [
    ...(src.match(/PHASES[^=\n]*=\s*\(([^)]*)\)/)?.[1] ?? '').matchAll(/"(\w+)"/g),
  ].map((m) => m[1]!);
  const def = src.match(/DEFAULT_PHASE[^=\n]*=\s*"(\w+)"/)?.[1] ?? '';

  const block = src.match(/_GLYPHS[^{]*\{([\s\S]*?)\n\}/)?.[1] ?? '';
  const glyphs: Record<string, PyGlyph> = {};
  for (const m of block.matchAll(/"(\w+)":\s*\(\(([^)]*)\),\s*([\d.]+)\)/g)) {
    const frames = [...m[2]!.matchAll(/"([^"]*)"/g)].map((x) => x[1]!);
    glyphs[m[1]!] = { frames, interval: Number(m[3]!) };
  }
  return { phases, default: def, glyphs };
}

describe('与 ui/ace_spinner.py 一致', () => {
  const py = pythonGlyphs();

  it('阶段集合相同', () => {
    expect(py.phases.length).toBe(5);
    expect([...PHASES].sort()).toEqual([...py.phases].sort());
  });

  it('默认阶段相同', () => {
    expect(py.default).toBe(DEFAULT_PHASE);
  });

  it('**每个阶段的字形序列与帧间隔都逐条相同**', () => {
    // 先确认真的抓到了东西：抓不到时下面的循环一次都不进，这条会**空转通过** ——
    // 而这正是它要防的那类假绿。
    expect(py.phases.length, '从 .py 里没抓到阶段，下面的比对是空转的').toBe(5);
    expect(Object.keys(py.glyphs).length, '从 .py 里没抓到字形表').toBe(5);
    for (const phase of py.phases) {
      const mine = GLYPHS[phase as keyof typeof GLYPHS];
      expect(mine, `缺阶段 ${phase}`).toBeDefined();
      expect(mine.frames, `${phase} 字形`).toEqual(py.glyphs[phase]!.frames);
      expect(mine.interval, `${phase} 帧间隔`).toBeCloseTo(py.glyphs[phase]!.interval, 5);
    }
  });

  it('字形都是单宽、无 emoji（旧终端里 emoji 会画成方框）', () => {
    for (const phase of PHASES) {
      for (const f of GLYPHS[phase].frames) {
        expect([...f].length, `${phase}/${f}`).toBe(1);
        expect(f.codePointAt(0)!, `${phase}/${f} 不该是 emoji`).toBeLessThan(0x1f000);
      }
    }
  });
});

describe('帧推进', () => {
  it('按帧间隔推进', () => {
    expect(frameAt('reasoning', 0)).toBe('◐');
    expect(frameAt('reasoning', 0.24)).toBe('◓');
    expect(frameAt('reasoning', 0.48)).toBe('◑');
    expect(frameAt('reasoning', 0.96)).toBe('◐'); // 回到第一帧
  });

  it('不同阶段速度不同（这是语义，不是装饰）', () => {
    expect(phaseInterval('waiting')).toBeLessThan(phaseInterval('tool_running'));
    expect(phaseInterval('tool_running')).toBeLessThan(phaseInterval('reasoning'));
  });

  it('**无动效时恒取第一帧** —— 降级要降到底，只慢一半同样难受', () => {
    for (const t of [0, 0.5, 10, 999]) {
      expect(frameAt('reasoning', t, true)).toBe('◐');
    }
  });

  it('负时间不崩（时钟回拨 / 注入的假起始值）', () => {
    expect(framesFor('reasoning')).toContain(frameAt('reasoning', -5));
  });

  it('认不出的阶段退回默认，不抛', () => {
    expect(framesFor('不存在的阶段')).toEqual(GLYPHS[DEFAULT_PHASE].frames);
    expect(phaseInterval('不存在的阶段')).toBe(GLYPHS[DEFAULT_PHASE].interval);
  });

  it('undefined 也退回默认', () => {
    expect(framesFor(undefined)).toEqual(GLYPHS[DEFAULT_PHASE].frames);
  });
});

describe('阶段 → 动词', () => {
  it('五个阶段各有一个动词键，不重不漏', () => {
    const keys = PHASES.map((p) => PHASE_VERB[p]);
    expect(keys).toEqual([1, 2, 3, 4, 5]);
    for (const p of PHASES) expect(verbKeyFor(p)).toBe(`spin_verb_${PHASE_VERB[p]}`);
  });

  it('认不出的阶段有兜底（不返回 undefined 键名）', () => {
    expect(verbKeyFor('未知')).toBe('spin_verb_2');
    expect(verbKeyFor(undefined)).toBe('spin_verb_2');
  });
});
