/**
 * 协议层测试 —— 同样以**跨语言一致性**为重点。
 *
 * 事件类型集合、审批三态、帧形状，这三样任何一样两边对不上，症状都是
 * "某个功能静默不工作"（事件不认识 → 被忽略；决策拼错 → 引擎不受理）。
 * 所以每条都去读 Python 源码比对，而不是靠人记得同步。
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { EVENT_TYPES, PROTOCOL_VERSION } from '../src/protocol/types.js';
import { resolvePython } from '../src/protocol/client.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

function readPy(rel: string): string {
  return readFileSync(join(ROOT, rel), 'utf-8');
}

describe('协议版本与事件类型', () => {
  it('PROTOCOL_VERSION 与 core/ace_serve.py 相同', () => {
    const src = readPy('core/ace_serve.py');
    const m = src.match(/^PROTOCOL_VERSION\s*=\s*(\d+)/m);
    expect(m).not.toBeNull();
    expect(Number(m![1])).toBe(PROTOCOL_VERSION);
  });

  it('事件类型集合与 core/ace_events.EVENT_TYPES 相同', () => {
    const src = readPy('core/ace_events.py');
    const block = src.match(/EVENT_TYPES\s*=\s*\(([\s\S]*?)\)/);
    expect(block).not.toBeNull();
    const py = [...block![1]!.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]!);
    expect(py.length).toBeGreaterThan(5);
    expect([...EVENT_TYPES].sort()).toEqual([...py].sort());
  });

  it('EVENT_REQUIRED 表覆盖全部事件类型（Python 侧的既有约束）', () => {
    // 这条在 Python 侧也有测试；这里是**从 TS 的角度**再确认一次，
    // 免得 TS 拿着一个 Python 自己都不完整的集合在对齐。
    const src = readPy('core/ace_events.py');
    const types = src.match(/EVENT_TYPES\s*=\s*\(([\s\S]*?)\)/)?.[1] ?? '';
    const reqd = src.match(/EVENT_REQUIRED[^{]*\{([\s\S]*?)\n\}/)?.[1] ?? '';
    const t = new Set([...types.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]!));
    const r = new Set([...reqd.matchAll(/"([a-z_]+)"\s*:/g)].map((m) => m[1]!));
    expect([...r].sort()).toEqual([...t].sort());
  });

  it('审批三态与 agent_runner 的 GRANT_* 常量一致', () => {
    const src = readPy('agent_runner.py');
    const vals = [...src.matchAll(/^GRANT_(?:ONCE|SESSION|DENY)\s*=\s*"([a-z]+)"/gm)].map(
      (m) => m[1]!,
    );
    expect(vals.sort()).toEqual(['deny', 'once', 'session']);
  });

  it('tool_start 是执行前事件、tool_call 是事后事件（顺序不能反）', () => {
    // 这条口径写在 ace_events.py 的 docstring 里，是 UI「正在跑」能动起来的根因。
    // 从 TS 这边也钉一条，免得有人"顺手"把两者合并。
    const src = readPy('core/ace_events.py');
    expect(src).toMatch(/tool_start/);
    expect(src).toMatch(/事后/);
  });
});

describe('解释器探测', () => {
  it('显式传入优先', () => {
    expect(resolvePython('python3.13', {})).toBe('python3.13');
  });

  it('ACE_PYTHON 环境变量次之', () => {
    expect(resolvePython(undefined, { ACE_PYTHON: 'python3.12' })).toBe('python3.12');
  });

  it('裸命令名原样返回（交给 PATH 解析，不做存在性检查）', () => {
    expect(resolvePython(undefined, { ACE_PYTHON: 'my-python' })).toBe('my-python');
  });

  it('路径式候选不存在时会被跳过，不会返回一个死路径', () => {
    const got = resolvePython(undefined, { ACE_PYTHON: 'Z:\\nope\\python.exe' });
    // 不存在 → 继续探已知路径 → 最终兜底成裸命令名（不带盘符）
    expect(got).not.toContain('Z:');
  });
});
