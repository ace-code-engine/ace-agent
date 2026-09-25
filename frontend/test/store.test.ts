/**
 * 状态 reducer 测试。
 *
 * 事件驱动的界面，错全出在"到达顺序不按预想"上。这些用纯函数就能穷举 ——
 * 塞进组件里就只能靠手点，而手点覆盖不到这些顺序。
 */

import { describe, expect, it } from 'vitest';

import type { AceEvent } from '../src/protocol/types.js';
import {
  applyEvent,
  applyEvents,
  applyPermissionAnswer,
  initialState,
  type State,
} from '../src/state/store.js';

function ev(type: string, fields: Record<string, unknown> = {}): AceEvent {
  return { type, ts: 1, ...fields };
}

function run(...events: AceEvent[]): State {
  return applyEvents(initialState(), events);
}

describe('基本流转', () => {
  it('session_start 记下会话信息', () => {
    const s = run(
      ev('session_start', {
        version: '3.41.0',
        permission: 'readonly',
        sandbox: 'off',
        project_root: '/x',
        model: 'm',
      }),
    );
    expect(s.meta.version).toBe('3.41.0');
    expect(s.meta.permission).toBe('readonly');
    expect(s.meta.projectRoot).toBe('/x');
  });

  it('user_message 进转写区并置忙', () => {
    const s = run(ev('user_message', { text: '你好' }));
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({ kind: 'user', text: '你好' });
    expect(s.busy).toBe(true);
  });

  it('final 收尾并解除忙', () => {
    const s = run(ev('final', { text: '答', round: 1 }));
    expect(s.items[0]).toMatchObject({ kind: 'assistant', text: '答', streaming: false });
    expect(s.busy).toBe(false);
  });
});

describe('流式增量', () => {
  it('model_delta 追加到同一条还在流的助手消息上', () => {
    const s = run(
      ev('model_delta', { text: '你' }),
      ev('model_delta', { text: '好' }),
      ev('model_delta', { text: '。' }),
    );
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({ kind: 'assistant', text: '你好。', streaming: true });
  });

  it('**final 不重复追加**（流式渲染最经典的坑：回答出现两遍）', () => {
    const s = run(
      ev('model_delta', { text: '你好。' }),
      ev('final', { text: '你好。' }),
    );
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({ kind: 'assistant', text: '你好。', streaming: false });
  });

  it('final 比流式内容更完整时以 final 为准', () => {
    const s = run(ev('model_delta', { text: '你' }), ev('final', { text: '你好，世界。' }));
    expect(s.items[0]).toMatchObject({ text: '你好，世界。' });
  });

  it('没有流式时 final 自己开一条', () => {
    const s = run(ev('final', { text: '直接答' }));
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({ kind: 'assistant', streaming: false });
  });
});

describe('工具卡片', () => {
  it('tool_start 开一张"在跑"的卡，tool_result 把它收掉', () => {
    const s = run(
      ev('tool_start', { tool: 'file_write', target: 'a.txt' }),
      ev('tool_result', { tool: 'file_write', status: 'SUCCESS', elapsed: 0.3, message: 'ok' }),
    );
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({
      kind: 'tool',
      tool: 'file_write',
      target: 'a.txt',
      status: 'ok',
      elapsed: 0.3,
    });
    expect(s.meta.tools).toBe(1);
  });

  it('失败状态映射成 fail', () => {
    const s = run(
      ev('tool_start', { tool: 'terminal_exec' }),
      ev('tool_result', { tool: 'terminal_exec', status: '403', elapsed: 0.1, message: '拒' }),
    );
    expect(s.items[0]).toMatchObject({ status: 'fail' });
  });

  it('只有 tool_result（没收到 tool_start）时也补一张卡 —— 宁可多一张，别丢结果', () => {
    const s = run(ev('tool_result', { tool: 'file_read', status: 'SUCCESS', elapsed: 0.1 }));
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({ kind: 'tool', tool: 'file_read', status: 'ok' });
  });

  it('同一个工具连着跑两次：分别配对自己的卡', () => {
    const s = run(
      ev('tool_start', { tool: 'file_read', target: '1' }),
      ev('tool_result', { tool: 'file_read', status: 'SUCCESS', elapsed: 0.1 }),
      ev('tool_start', { tool: 'file_read', target: '2' }),
      ev('tool_result', { tool: 'file_read', status: '404', elapsed: 0.2 }),
    );
    expect(s.items).toHaveLength(2);
    expect(s.items[0]).toMatchObject({ target: '1', status: 'ok' });
    expect(s.items[1]).toMatchObject({ target: '2', status: 'fail' });
  });
});

describe('审批', () => {
  it('permission_request 置起待答状态（界面据此弹框）', () => {
    const s = run(ev('permission_request', { tool: 'file_write', reason: '需要写权限' }));
    expect(s.pendingPermission).toMatchObject({ tool: 'file_write', reason: '需要写权限' });
  });

  it('答完之后待答清掉，转写区留下"当时怎么答的"', () => {
    let s = run(ev('permission_request', { tool: 'file_write', reason: 'r' }));
    s = applyPermissionAnswer(s, 'once');
    expect(s.pendingPermission).toBeNull();
    const item = s.items.find((i) => i.kind === 'permission');
    expect(item).toMatchObject({ answered: 'once' });
  });

  it('没有待答时给答案不会崩，也不产生副作用', () => {
    const s = applyPermissionAnswer(initialState(), 'deny');
    expect(s.items).toHaveLength(0);
    expect(s.pendingPermission).toBeNull();
  });
});

describe('健壮性', () => {
  it('不认识的事件类型被忽略（协议会加新事件，旧前端不该崩）', () => {
    const s = run(ev('未来的新事件', { x: 1 }));
    expect(s.items).toHaveLength(0);
  });

  it('缺字段的事件不崩（拿不到就是空串 / undefined）', () => {
    const s = run(ev('tool_result', {}));
    expect(s.items).toHaveLength(1);
    expect(s.items[0]).toMatchObject({ kind: 'tool', tool: '' });
  });

  it('空 notice 不产生条目（引擎会 print 空行）', () => {
    expect(run(ev('notice', { text: '   ' })).items).toHaveLength(0);
  });

  it('**不修改入参**（React 靠引用比较决定重渲染）', () => {
    const before = initialState();
    const snapshot = JSON.stringify(before);
    applyEvent(before, ev('user_message', { text: 'x' }));
    expect(JSON.stringify(before)).toBe(snapshot);
  });

  it('session_end 记下轮数与工具数', () => {
    const s = run(ev('session_end', { rounds: 3, tools: 5, elapsed: 1 }));
    expect(s.meta.ended).toBe(true);
    expect(s.meta.rounds).toBe(3);
    expect(s.meta.tools).toBe(5);
  });
});
