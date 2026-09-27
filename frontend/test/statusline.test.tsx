/**
 * 状态行：**引擎分段优先**。
 *
 * 为什么值得单测这一层：底栏是"随时在眼前"的那一行，而它的数据有两个可能来源 ——
 * 引擎的 `status` 事件（权威：`/statusline` 配置、告警档都在那边）与前端的
 * `buildSegments` 自算（界面挂载早于第一个事件时的兜底）。**两份都存在**，
 * 所以"用哪一份"必须被钉住：两边各算一份就会出现"CLI 说 92%、前端说 40%"。
 *
 * 宽度裁剪（`fitSegments`）不在这里重复测 —— 那是它自己那条口径。
 */

import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';

import { StatusLine, levelToken, segmentsFromEngine } from '../src/components/StatusLine.js';
import type { StatusSegmentWire } from '../src/protocol/types.js';
import { initialState } from '../src/state/store.js';
import type { Meta } from '../src/state/store.js';

const noColor = (): string | undefined => undefined;
const t = (key: string, params?: Record<string, string | number>): string =>
  params ? `${key}:${Object.values(params).join(',')}` : key;

const seg = (
  name: string,
  text: string,
  priority = 50,
  level = 'info',
): StatusSegmentWire => ({ name, text, priority, level });

function metaWith(over: Partial<Meta>): Meta {
  return { ...initialState().meta, ...over };
}

describe('引擎分段优先', () => {
  it('有引擎分段时不再自算', () => {
    const out = render(
      <StatusLine
        meta={metaWith({
          permission: 'readonly',
          model: 'some-model',
          statusSegments: [seg('context', '上下文 92%', 20, 'warn')],
        })}
        busy={false}
        color={noColor}
        width={80}
        t={t}
      />,
    ).lastFrame() ?? '';
    expect(out).toContain('上下文 92%');
    // 自算那套若也上了屏，这里会看到 i18n 键名（假 t 把它拼成 "footer_permission:readonly"）
    expect(out).not.toContain('footer_permission');
    expect(out).not.toContain('some-model');
  });

  it('没有引擎分段时退回自算（界面挂载早于第一个事件，那一行不该是空的）', () => {
    const out = render(
      <StatusLine
        meta={metaWith({ permission: 'readonly', statusSegments: [] })}
        busy={false}
        color={noColor}
        width={80}
        t={t}
      />,
    ).lastFrame() ?? '';
    expect(out).toContain('footer_permission:readonly');
  });
});

describe('语义档 → 主题 token', () => {
  it('四档各落各的（danger 走 error，不是 perm_full）', () => {
    expect(levelToken('dim')).toBe('dim');
    expect(levelToken('warn')).toBe('warn');
    expect(levelToken('danger')).toBe('error');
    expect(levelToken('goal')).toBe('goal_active');
    expect(levelToken('info')).toBe('text');
    expect(levelToken('引擎以后新加的档')).toBe('text');
  });

  it('权限那一段按 meta.permission 上色 —— 那边 level 有重叠，只有 name 能区分', () => {
    // 引擎的 `class:footer-w` 同时被"可写权限"与"告警分段"复用，所以不能照 level 上色。
    const rows = [seg('permission', ' 权限:write ', 10, 'warn')];
    const tokens = ['readonly', 'write', 'full'].map(
      (p) => segmentsFromEngine(rows, metaWith({ permission: p }))[0].token,
    );
    expect(tokens).toEqual(['perm_ro', 'perm_write', 'perm_full']);
  });

  it('优先级原样带过来（裁剪顺序仍由前端按自己的列数决定）', () => {
    const rows = segmentsFromEngine([seg('a', ' A ', 7), seg('b', ' B ', 3)], metaWith({}));
    expect(rows.map((r) => r.priority)).toEqual([7, 3]);
    expect(rows.map((r) => r.text)).toEqual([' A ', ' B ']);
  });
});
