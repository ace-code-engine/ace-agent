/**
 * 端到端集成测试 —— **真的起 Python 引擎**，走真的管道、真的协议。
 *
 * 为什么这一层不能只靠假引擎：假引擎能证明"界面拿到事件画得对"，但证明不了
 * "事件真的产得出来"。协议两端对不上的症状（字段名拼错、事件类型漏登记、
 * 审批三态不一致）**只在真往返里才暴露**。
 *
 * 这一层刻意**不渲染 Ink** —— Ink 要有 TTY，CI 上通常没有；而这里要验的是
 * 管道与协议，不是绘制。绘制由 `app.test.tsx` 的假引擎覆盖。两边合起来才是完整的。
 *
 * 引擎不可用时（没 Python / 环境不对）**整组跳过**，而不是报一堆红 —— 但跳过会
 * 在输出里说清楚，不会假装通过。
 */

import { beforeAll, describe, expect, it } from 'vitest';

import { AceClient, resolvePython } from '../src/protocol/client.js';
import type { AceEvent } from '../src/protocol/types.js';

const PYTHON = resolvePython();

/**
 * 起一个引擎，跑完一轮，收齐事件。
 *
 * 收尾的**顺序**很关键，踩过一次：不能等 `session_end` 来决定"一轮跑完了没有" ——
 * 那个事件只在 `shutdown` 时才发，而 serve 模式是前端驱动的，它自己不会退。
 * 于是等 session_end 等于等一个永远不会来的信号，每个用例白等满超时。
 *
 * 正确的信号是 `send()` 的 Promise：它在**这一轮跑完**时就 resolve。
 */
async function runSession(
  trigger: string | null,
  opts: { answer?: 'once' | 'session' | 'deny'; extraArgs?: string[] } = {},
): Promise<{ events: AceEvent[]; gaps: number[]; exitOk: boolean; client: AceClient }> {
  const client = new AceClient({
    extraArgs: ['--mock', '--permission', 'readonly', ...(opts.extraArgs ?? [])],
  });
  const events: AceEvent[] = [];
  client.on('event', (ev: AceEvent) => events.push(ev));

  if (opts.answer) {
    const decision = opts.answer;
    // 引擎会在审批处**阻塞**等答案，所以监听必须在发消息之前就挂好。
    client.on('permission_request', () => {
      void client.answerPermission(decision, '集成测试').catch(() => undefined);
    });
  }

  await client.start(true);

  if (trigger !== null) {
    await client.send(trigger).catch(() => undefined);
  }

  // 收工：shutdown 之后引擎才会发 session_end（它写在 atexit 里）。
  const ended = new Promise<void>((resolve) => {
    client.on('session_end', () => resolve());
    client.on('exit', () => resolve());
  });
  const exitOk = await client.shutdown().then(
    () => true,
    () => false,
  );
  await Promise.race([ended, new Promise((r) => setTimeout(r, 15_000))]);

  return { events, gaps: client.seqGaps, exitOk, client };
}

let engineUsable = true;
beforeAll(async () => {
  // 探一次引擎能不能起来：起不来就整组跳过（并说明原因），
  // 而不是让二十条用例各自失败一遍、把真正的问题淹掉。
  try {
    const c = new AceClient({ extraArgs: ['--mock'] });
    await c.start(false);
    await c.shutdown();
  } catch (e) {
    engineUsable = false;
    // eslint-disable-next-line no-console
    console.warn(
      `[integration] 引擎起不来，跳过：${e instanceof Error ? e.message : String(e)}\n` +
        `           解释器探测结果：${PYTHON}`,
    );
  }
}, 120_000);

describe.skipIf(!engineUsable)('真引擎 · 基本往返', () => {
  it('握手拿到能力，事件流首尾正确', async () => {
    const { events, client } = await runSession('现在几点');
    const types = events.map((e) => e.type);
    expect(types[0]).toBe('session_start');
    expect(types).toContain('user_message');
    expect(types).toContain('model_request');
    expect(types).toContain('final');
    expect(types).toContain('session_end');
    expect(client.capabilities?.protocol).toBe(1);
    expect(client.capabilities?.server?.name).toBe('ace');
  }, 120_000);

  it('seq 单调且无缺口（丢帧会被发现）', async () => {
    const { events, gaps } = await runSession('现在几点');
    expect(gaps).toEqual([]);
    expect(events.length).toBeGreaterThan(4);
  }, 120_000);

  it('tool_start 出现在 tool_call 之前（驱动"正在跑"的根因）', async () => {
    const { events } = await runSession('现在几点');
    const types = events.map((e) => e.type);
    const start = types.indexOf('tool_start');
    const call = types.indexOf('tool_call');
    expect(start).toBeGreaterThanOrEqual(0);
    expect(call).toBeGreaterThanOrEqual(0);
    expect(start).toBeLessThan(call);
  }, 120_000);
});

describe.skipIf(!engineUsable)('真引擎 · 授权往返（这个前端存在的理由）', () => {
  it('readonly 下的写操作触发审批，且**事件先于答案**', async () => {
    const { events } = await runSession('帮我改代码，往笔记里加一行', { answer: 'once' });
    const perms = events.filter((e) => e.type === 'permission_request');
    expect(perms.length).toBeGreaterThan(0);
    expect(perms[0]).toMatchObject({ tool: expect.any(String), reason: expect.any(String) });
  }, 120_000);

  it('递上去的答案是 once → 引擎说「已临时授权」', async () => {
    const { events } = await runSession('帮我改代码，往笔记里加一行', { answer: 'once' });
    const notices = events
      .filter((e) => e.type === 'notice')
      .map((e) => String(e.text ?? ''))
      .join('\n');
    expect(notices).toContain('已临时授权');
  }, 120_000);

  it('递上去的答案是 deny → 引擎说「已拒绝授权」', async () => {
    const { events } = await runSession('帮我改代码，往笔记里加一行', { answer: 'deny' });
    const notices = events
      .filter((e) => e.type === 'notice')
      .map((e) => String(e.text ?? ''))
      .join('\n');
    expect(notices).toContain('已拒绝授权');
  }, 120_000);

  it('递上去的答案是 session → 引擎说「已授权本次会话」', async () => {
    const { events } = await runSession('帮我改代码，往笔记里加一行', { answer: 'session' });
    const notices = events
      .filter((e) => e.type === 'notice')
      .map((e) => String(e.text ?? ''))
      .join('\n');
    expect(notices).toContain('本次会话');
  }, 120_000);

  it('**三种决策产生三种不同的引擎行为** —— 这才叫答案真的送达了', async () => {
    // **串行**跑，不要 Promise.all：这条要验的是"三种决策 → 三种行为"，
    // 并发不是它的考点。而整个套件本来就在并发起 Python 子进程 —— 再加三个
    // 同时跑的引擎，机器一紧张就有一条赶不上内部超时，于是偶尔少一种行为、
    // 报 `expected 2 to be 3`。那种红是负载造成的，不是产品问题，
    // 但它会消耗掉别人对这条测试的信任（"那条老红"），所以按顺序跑。
    const once = await runSession('帮我改代码，往笔记里加一行', { answer: 'once' });
    const deny = await runSession('帮我改代码，往笔记里加一行', { answer: 'deny' });
    const session = await runSession('帮我改代码，往笔记里加一行', { answer: 'session' });
    const noticesOf = (r: { events: AceEvent[] }): string =>
      r.events
        .filter((e) => e.type === 'notice')
        .map((e) => String(e.text ?? ''))
        .join('\n');
    const a = noticesOf(once);
    const b = noticesOf(deny);
    const c = noticesOf(session);
    expect(new Set([a, b, c]).size).toBe(3);
  }, 300_000);
});
