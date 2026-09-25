/**
 * 界面层测试 —— 用**假引擎**喂事件把界面跑起来。
 *
 * 为什么不去起真的 Python：那样测的是"引擎能不能跑"，而这里要测的是
 * "界面拿到事件之后画得对不对"。分开之后，界面测试是毫秒级、可穷举的，
 * 不需要模型、不需要 API key，CI 上也不会因为引擎慢而抖。
 *
 * 引擎那一侧由 Python 的 `test_all.py [69]` 负责（真子进程、真往返）。
 */

import { describe, expect, it, vi } from 'vitest';
import { render } from 'ink-testing-library';

import { App, type AceClientLike } from '../src/App.js';
import { I18n } from '../src/i18n.js';
import type {
  AceEvent,
  ConfigData,
  GrantDecision,
  HomeData,
  SessionsData,
  TasksData,
} from '../src/protocol/types.js';

/**
 * 假引擎：能推事件、能记录被调用的方法。
 *
 * **刻意镜像真 `AceClient` 的缓冲语义**：首个 `event` 订阅者到来之前先攒着，
 * 订阅时按原顺序补发。不镜像的话，测试会默认"事件推出去就有人收"，
 * 而真实情形是界面挂载晚于引擎启动 —— 于是测试全绿、线上丢事件。
 */
class FakeClient implements AceClientLike {
  readonly listeners = new Map<string, Array<(...args: any[]) => void>>();
  readonly calls: Array<{ method: string; args: unknown[] }> = [];
  private buffer: AceEvent[] = [];
  private buffering = true;

  on(event: string, listener: (...args: any[]) => void): this {
    const list = this.listeners.get(event) ?? [];
    list.push(listener);
    this.listeners.set(event, list);
    if (event === 'event' && this.buffering) {
      this.buffering = false;
      const pending = this.buffer;
      this.buffer = [];
      for (const ev of pending) this.deliver(ev);
    }
    return this;
  }

  /** 测试侧推一条事件。没人订阅时先攒着（与真客户端同）。 */
  push(ev: AceEvent): void {
    if (this.buffering) {
      this.buffer.push(ev);
      return;
    }
    this.deliver(ev);
  }

  private deliver(ev: AceEvent): void {
    for (const fn of this.listeners.get('event') ?? []) fn(ev);
  }

  async send(text: string): Promise<unknown> {
    this.calls.push({ method: 'send', args: [text] });
    return {};
  }
  async command(line: string): Promise<unknown> {
    this.calls.push({ method: 'command', args: [line] });
    return {};
  }
  async answerPermission(decision: GrantDecision, feedback?: string): Promise<unknown> {
    this.calls.push({ method: 'answerPermission', args: [decision, feedback] });
    return {};
  }
  async answerChoice(payload: {
    values?: string[];
    accepted?: boolean;
    text?: string;
    cancelled?: boolean;
  }): Promise<unknown> {
    this.calls.push({ method: 'answerChoice', args: [payload] });
    return {};
  }
  /** 主页内容（默认给一份最小可用结构；用例可以覆盖它）。 */
  home: HomeData = {
    title: { version: '3.41.0', model: 'deepseek', permission: 'readonly' },
    sections: [
      {
        key: 'resume',
        title_key: 'home_sec_resume',
        items: [
          {
            action: 'resume_last',
            label_key: 'home_resume_last',
            value: '',
            hint_key: 'home_resume_last_hint',
            enabled: true,
          },
        ],
      },
    ],
  };
  async requestHome(): Promise<HomeData> {
    this.calls.push({ method: 'requestHome', args: [] });
    return this.home;
  }
  /** 任务树（默认给一棵两层的树；用例可以覆盖）。 */
  tasks: TasksData = {
    tree: {
      text: '目标 [R1/3] 把前端做完',
      status: 'in_progress',
      note: '',
      children: [
        { text: '#1 补全菜单', status: 'done', note: '', children: [] },
        { text: '#2 任务树', status: 'in_progress', note: '', children: [] },
      ],
    },
  };
  async requestTasks(): Promise<TasksData> {
    this.calls.push({ method: 'requestTasks', args: [] });
    return this.tasks;
  }
  /** 界面侧开关（默认 vim 关；用例可以覆盖 `config.vim`）。 */
  config: ConfigData = { vim: false, lang: 'zh', permission: 'readonly' };
  async requestConfig(): Promise<ConfigData> {
    this.calls.push({ method: 'requestConfig', args: [] });
    return this.config;
  }
  /** 可引用的历史会话（`@session` 候选）。 */
  sessions: SessionsData = {
    sessions: [
      { path: '/x/1000.jsonl', when: '昨天 14:20', turns: 3, label: '缓存穿透那次' },
      { path: '/x/0900.jsonl', when: '前天 09:10', turns: 8, label: '重构执行层' },
    ],
  };
  async requestSessions(): Promise<SessionsData> {
    this.calls.push({ method: 'requestSessions', args: [] });
    return this.sessions;
  }
  async interrupt(): Promise<unknown> {
    this.calls.push({ method: 'interrupt', args: [] });
    return {};
  }
  async shutdown(): Promise<void> {
    this.calls.push({ method: 'shutdown', args: [] });
  }
}

const i18n = new I18n('zh');
const noColor = (): string | undefined => undefined;

/**
 * 挂载 App 并**等一拍**再返回。
 *
 * 那个 `await tick()` 不是保险起见：`render()` 返回时 Ink 还没把输入监听挂上，
 * 紧接着 `stdin.write` 的按键会直接落空（症状是"界面在、但打不进字"）。
 * 让它成为 setup 的一部分，而不是每个用例各自记得加 —— 这是最容易漏、又最难查的一类。
 */
async function setup(init: { config?: ConfigData; home?: HomeData } = {}) {
  const client = new FakeClient();
  // **必须在挂载前**把假数据摆好：App 挂载时就去拉 config / home，
  // 挂载后再设的话它已经拿到默认值了（踩过：横幅一直显示空配置）。
  if (init.config) client.config = init.config;
  if (init.home) client.home = init.home;
  const tree = render(<App client={client} t={(k, p) => i18n.t(k, p)} colorOf={noColor} />);
  await tick();
  return { client, ...tree };
}

/** 等一拍，让 Ink 把重渲染冲刷到 lastFrame。 */
const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 20));

describe('转写区渲染', () => {
  it('用户消息与最终回复都上屏', async () => {
    const { client, lastFrame, unmount } = await setup();
    client.push({ type: 'user_message', ts: 1, text: '你好' });
    client.push({ type: 'final', ts: 2, text: '你也好' });
    await tick();
    const frame = lastFrame() ?? '';
    expect(frame).toContain('你好');
    expect(frame).toContain('你也好');
    unmount();
  });

  it('工具卡片带状态字形与工具名', async () => {
    const { client, lastFrame, unmount } = await setup();
    client.push({ type: 'tool_start', ts: 1, tool: 'file_write', target: 'note.md' });
    await tick();
    expect(lastFrame() ?? '').toContain('file_write');
    expect(lastFrame() ?? '').toContain('note.md');

    client.push({
      type: 'tool_result',
      ts: 2,
      tool: 'file_write',
      status: 'SUCCESS',
      elapsed: 0.4,
      message: '',
    });
    await tick();
    expect(lastFrame() ?? '').toContain('✓');
    unmount();
  });

  it('状态行显示权限档与模型', async () => {
    const { client, lastFrame, unmount } = await setup();
    client.push({
      type: 'session_start',
      ts: 1,
      version: '3.41.0',
      permission: 'readonly',
      sandbox: 'off',
      project_root: '/proj',
      model: 'deepseek-v4-flash',
    });
    await tick();
    const frame = lastFrame() ?? '';
    expect(frame).toContain('readonly');
    expect(frame).toContain('deepseek-v4-flash');
    unmount();
  });
});

describe('授权对话框', () => {
  it('有审批请求时弹框，三个选项都在', async () => {
    const { client, lastFrame, unmount } = await setup();
    client.push({ type: 'permission_request', ts: 1, tool: 'file_write', reason: '需要写权限' });
    await tick();
    const frame = lastFrame() ?? '';
    expect(frame).toContain('file_write');
    expect(frame).toContain('1.');
    expect(frame).toContain('2.');
    expect(frame).toContain('3.');
    unmount();
  });

  it('按 1 → 递上 once', async () => {
    const { client, stdin, unmount } = await setup();
    client.push({ type: 'permission_request', ts: 1, tool: 'file_write', reason: 'r' });
    await tick();
    stdin.write('1');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerPermission', args: ['once', undefined] });
    unmount();
  });

  it('按 2 → 递上 session', async () => {
    const { client, stdin, unmount } = await setup();
    client.push({ type: 'permission_request', ts: 1, tool: 'file_write', reason: 'r' });
    await tick();
    stdin.write('2');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerPermission', args: ['session', undefined] });
    unmount();
  });

  it('按 Esc → 递上 deny（Esc 即拒绝，与全局口径一致）', async () => {
    const { client, stdin, unmount } = await setup();
    client.push({ type: 'permission_request', ts: 1, tool: 'file_write', reason: 'r' });
    await tick();
    stdin.write('\u001b'); // ESC
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerPermission', args: ['deny', undefined] });
    unmount();
  });

  it('按 3 → 递上 deny', async () => {
    const { client, stdin, unmount } = await setup();
    client.push({ type: 'permission_request', ts: 1, tool: 'file_write', reason: 'r' });
    await tick();
    stdin.write('3');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerPermission', args: ['deny', undefined] });
    unmount();
  });

  it('答完框就消失', async () => {
    const { client, stdin, lastFrame, unmount } = await setup();
    client.push({ type: 'permission_request', ts: 1, tool: 'file_write', reason: 'r' });
    await tick();
    expect(lastFrame() ?? '').toContain('1.');
    stdin.write('1');
    await tick();
    expect(lastFrame() ?? '').not.toContain('1. ');
    unmount();
  });
});

describe('输入通道选择', () => {
  it('`/` 开头走 command.exec，其余走 user.message', async () => {
    const { client, stdin, unmount } = await setup();
    stdin.write('/model');
    await tick();
    stdin.write('\r');
    await tick();
    expect(client.calls.some((c) => c.method === 'command' && c.args[0] === '/model')).toBe(true);

    stdin.write('帮我看下');
    await tick();
    stdin.write('\r');
    await tick();
    expect(client.calls.some((c) => c.method === 'send' && c.args[0] === '帮我看下')).toBe(true);
    unmount();
  });
});

describe('健壮性', () => {
  it('引擎报错时把错误显示出来，而不是静默不动', async () => {
    const client = new FakeClient();
    client.send = vi.fn(async () => {
      throw Object.assign(new Error('引擎忙'), { code: 'E_BUSY' });
    });
    const { stdin, lastFrame, unmount } = render(
      <App client={client} t={(k, p) => i18n.t(k, p)} colorOf={noColor} />,
    );
    await tick(); // 等 Ink 挂上输入监听（见 setup 的说明）
    stdin.write('hello');
    await tick();
    stdin.write('\r');
    await tick();
    expect(lastFrame() ?? '').toContain('引擎忙');
    unmount();
  });

  it('不认识的事件不把界面打崩', async () => {
    const { client, lastFrame, unmount } = await setup();
    client.push({ type: '某个未来事件', ts: 1, payload: { x: 1 } });
    await tick();
    expect(lastFrame()).toBeTruthy();
    unmount();
  });
});

describe('首屏横幅', () => {
  const CFG: ConfigData = {
    version: '3.41.0',
    model: 'deepseek-v4-flash',
    permission: 'readonly',
    folder: 'ace',
  };

  it('渲染 logo（块状图）+ 产品名与版本', async () => {
    const { lastFrame, unmount } = await setup({ config: CFG });
    const frame = lastFrame() ?? '';
    // logo 是块状字符（█ ╔ ═ 这些），画出来才有"品牌感"
    expect(frame).toContain('█');
    expect(frame).toContain('ACE · AI Code Engine');
    expect(frame).toContain('v3.41.0');
    unmount();
  });

  it('右栏跟着给出「环境」与「位置」：模型 · 权限 / 目录', async () => {
    const { lastFrame, unmount } = await setup({ config: CFG });
    const frame = lastFrame() ?? '';
    expect(frame).toContain('deepseek-v4-flash');
    expect(frame).toContain('readonly');
    expect(frame).toContain('ace');
    unmount();
  });

  it('**发了第一条消息之后横幅就不在了**（它是开场，不是常驻头部）', async () => {
    const { client, lastFrame, unmount } = await setup({ config: CFG });
    expect(lastFrame() ?? '').toContain('ACE · AI Code Engine');

    client.push({ type: 'user_message', ts: 1, text: '你好' });
    await tick();
    expect(lastFrame() ?? '').not.toContain('ACE · AI Code Engine');
    unmount();
  });

  it('右栏缺值时不留空行（版本/模型都没有也不崩）', async () => {
    const { lastFrame, unmount } = await setup({ config: {} });
    const frame = lastFrame() ?? '';
    expect(frame).toContain('█'); // logo 还在
    expect(frame).toContain('ACE · AI Code Engine');
    unmount();
  });

  it('身份与环境**只出现一次**（横幅与主页别重复说同一件事）', async () => {
    const { lastFrame, unmount } = await setup({ config: CFG });
    const frame = lastFrame() ?? '';
    expect(frame.split('readonly').length - 1).toBe(1);
    unmount();
  });
});

describe('主页', () => {
  it('没有消息时渲染主页（分区标题 + 条目）', async () => {
    const { client, lastFrame, unmount } = await setup();
    const frame = lastFrame() ?? '';
    expect(client.calls.some((c) => c.method === 'requestHome')).toBe(true);
    expect(frame).toContain(i18n.t('home_sec_resume')); // 分区标题
    expect(frame).toContain(i18n.t('home_resume_last')); // 条目
    // 身份与环境归横幅，主页不该再打一遍（见 Home.tsx 顶部说明）
    expect(frame).not.toContain('ACE 3.41.0');
    unmount();
  });

  it('**条目文案里的占位符被真的替换掉**（`{when}` 这类不该原样上屏）', async () => {
    const { lastFrame, unmount } = await setup({
      home: {
        title: {},
        sections: [
          {
            key: 'resume',
            title_key: 'home_sec_resume',
            items: [
              {
                action: 'resume_last',
                label_key: 'home_resume_last',
                value: '',
                hint_key: '',
                enabled: true,
                fmt: { when: '昨天', turns: 3 },
              },
            ],
          },
        ],
      },
    });
    const frame = lastFrame() ?? '';
    expect(frame).not.toContain('{when}');
    expect(frame).not.toContain('{turns}');
    expect(frame).toContain('昨天');
    unmount();
  });

  it('**有消息之后主页就不再渲染**（它是开场，不是常驻仪表盘）', async () => {
    const { client, lastFrame, unmount } = await setup();
    await tick();
    expect(lastFrame() ?? '').toContain(i18n.t('home_sec_resume'));

    client.push({ type: 'user_message', ts: 1, text: '你好' });
    await tick();
    expect(lastFrame() ?? '').not.toContain(i18n.t('home_sec_resume'));
    unmount();
  });

  it('主页取不到时不显示空壳，也不崩', async () => {
    const client = new FakeClient();
    client.requestHome = async () => {
      throw Object.assign(new Error('取不到'), { code: 'E_INTERNAL' });
    };
    const { lastFrame, unmount } = render(
      <App client={client} t={(k, p) => i18n.t(k, p)} colorOf={noColor} />,
    );
    await tick();
    const frame = lastFrame() ?? '';
    // 既没有分区标题（不是空壳），也没有崩（还能渲染出输入行）
    expect(frame).not.toContain(i18n.t('home_sec_resume'));
    expect(frame).toContain('❯');
    unmount();
  });
});

describe('选择对话框', () => {
  const chooseReq = (kind: string, extra: Record<string, unknown> = {}): AceEvent => ({
    type: 'choice_request',
    ts: 1,
    kind,
    title: '选一个',
    ...extra,
  });

  it('choose：列出候选，回车把选中项递回去', async () => {
    const { client, stdin, lastFrame, unmount } = await setup();
    client.push(chooseReq('choose', { options: ['deepseek', 'qwen', 'zhipu'] }));
    await tick();
    expect(lastFrame() ?? '').toContain('deepseek');
    stdin.write('\r');
    await tick();
    expect(client.calls).toContainEqual({
      method: 'answerChoice',
      args: [{ values: ['deepseek'] }],
    });
    unmount();
  });

  it('choose：↓ 之后回车递的是第二项', async () => {
    const { client, stdin, unmount } = await setup();
    client.push(chooseReq('choose', { options: ['甲', '乙', '丙'] }));
    await tick();
    stdin.write('\u001b[B'); // ↓
    await tick();
    stdin.write('\r');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ values: ['乙'] }] });
    unmount();
  });

  it('choose：输入即筛选', async () => {
    const { client, stdin, lastFrame, unmount } = await setup();
    client.push(chooseReq('choose', { options: ['deepseek', 'qwen'] }));
    await tick();
    stdin.write('qwen');
    await tick();
    expect(lastFrame() ?? '').toContain('qwen');
    stdin.write('\r');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ values: ['qwen'] }] });
    unmount();
  });

  it('confirm：y 是同意', async () => {
    const { client, stdin, unmount } = await setup();
    client.push(chooseReq('confirm'));
    await tick();
    stdin.write('y');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ accepted: true }] });
    unmount();
  });

  it('confirm：**回车是"否"**（默认否，关掉/超时都不等于同意）', async () => {
    const { client, stdin, unmount } = await setup();
    client.push(chooseReq('confirm'));
    await tick();
    stdin.write('\r');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ accepted: false }] });
    unmount();
  });

  it('text：输入后回车把文本递回去', async () => {
    const { client, stdin, unmount } = await setup();
    client.push(chooseReq('text', { default: '' }));
    await tick();
    stdin.write('理由');
    await tick();
    stdin.write('\r');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ text: '理由' }] });
    unmount();
  });

  it('text：预填值可用', async () => {
    const { client, stdin, lastFrame, unmount } = await setup();
    client.push(chooseReq('text', { default: '预填内容' }));
    await tick();
    expect(lastFrame() ?? '').toContain('预填内容');
    stdin.write('\r');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ text: '预填内容' }] });
    unmount();
  });

  it('Esc → 取消（不是递一个空答案上去）', async () => {
    const { client, stdin, unmount } = await setup();
    client.push(chooseReq('choose', { options: ['甲'] }));
    await tick();
    stdin.write('\u001b');
    await tick();
    expect(client.calls).toContainEqual({ method: 'answerChoice', args: [{ cancelled: true }] });
    unmount();
  });

  it('答完框就消失', async () => {
    const { client, stdin, lastFrame, unmount } = await setup();
    client.push(chooseReq('choose', { options: ['甲', '乙'] }));
    await tick();
    expect(lastFrame() ?? '').toContain('甲');
    stdin.write('\r');
    await tick();
    expect(lastFrame() ?? '').not.toContain('❯ 甲');
    unmount();
  });
});
