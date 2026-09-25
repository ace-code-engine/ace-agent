/**
 * 转写区状态 —— **纯 reducer**，不碰 React、不碰进程。
 *
 * 为什么单拎出来：事件驱动的界面最容易出的错全在"事件到达顺序不按预想"上
 * （`tool_result` 先于 `tool_start`、`final` 之后又来一条 `notice`、同一个工具连着跑两次）。
 * 这些用一堆纯函数就能穷举测；塞进组件里就只能靠手点，而手点永远覆盖不到那些顺序。
 */

import type { AceEvent, ChoiceKind, GrantDecision } from '../protocol/types.js';
import { looksLikeDiff } from '../render/diff.js';
import type { Phase } from '../render/spinner.js';

export type ToolStatus = 'running' | 'ok' | 'fail';

export type Item =
  | { kind: 'user'; id: number; text: string }
  | { kind: 'assistant'; id: number; text: string; streaming: boolean; round?: number }
  | {
      kind: 'tool';
      id: number;
      tool: string;
      target?: string;
      status: ToolStatus;
      elapsed?: number;
      message?: string;
      exitCode?: number | null;
      /** 这次改动的 unified diff（写类工具才有）。工具卡片据此画 +/− 与统计。 */
      diff?: string;
    }
  | { kind: 'notice'; id: number; text: string }
  | { kind: 'error'; id: number; text: string }
  | { kind: 'permission'; id: number; tool: string; reason: string; answered?: GrantDecision };

export interface Meta {
  version?: string;
  model?: string;
  permission?: string;
  sandbox?: string;
  projectRoot?: string;
  mock?: boolean;
  /** 引擎报告的状态行分段（`status` 事件；未接则空）。 */
  statusSegments: string[];
  /** 会话是否已结束。 */
  ended: boolean;
  rounds: number;
  tools: number;
  /**
   * 当前阶段 —— 决定等待指示器画哪套字形与速度。
   *
   * 为什么让状态机来定而不是组件自己猜：**速度本身是语义**（见 `render/spinner.ts`）。
   * 组件拿不到"现在卡在哪一步"，只有事件流知道。
   */
  phase: Phase | '';
}

export interface State {
  items: Item[];
  meta: Meta;
  /** 正在等待答案的审批（有值 = 应弹授权框）。 */
  pendingPermission: { tool: string; reason: string; itemId: number } | null;
  /** 正在等待答案的选择（有值 = 应弹选择框）。同一时刻只会有一个。 */
  pendingChoice: {
    kind: ChoiceKind;
    title: string;
    options: string[];
    defaultValue: string;
    itemId: number;
  } | null;
  /** 是否正在跑一轮（用于输入框禁用 / spinner）。 */
  busy: boolean;
  /** 单调递增的条目 id。 */
  seq: number;
}

export function initialState(): State {
  return {
    items: [],
    meta: { statusSegments: [], ended: false, rounds: 0, tools: 0, phase: '' },
    pendingPermission: null,
    pendingChoice: null,
    busy: false,
    seq: 0,
  };
}

/**
 * 对联合类型做 Omit。内建的 `Omit` 作用在联合上会**塌缩成公共键**
 * （`Item` 各分支只有 `kind`/`id` 是共有的），于是 `{kind:'tool', tool:...}`
 * 就报"对象字面量不能指定已知属性" —— 这是 TS 的一个经典坑，必须分发。
 */
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;
type NewItem = DistributiveOmit<Item, 'id'>;

function push(state: State, item: NewItem): State {
  const id = state.seq + 1;
  return { ...state, seq: id, items: [...state.items, { ...item, id } as Item] };
}

/**
 * 把一个事件折进状态。**永不修改入参** —— 便于 React 做引用比较，
 * 也让"同一串事件跑两遍结果一致"这件事可断言。
 */
export function applyEvent(state: State, ev: AceEvent): State {
  switch (ev.type) {
    case 'session_start': {
      return {
        ...state,
        meta: {
          ...state.meta,
          version: str(ev.version),
          model: str(ev.model),
          permission: str(ev.permission),
          sandbox: str(ev.sandbox),
          projectRoot: str(ev.project_root),
          mock: Boolean(ev.mock),
        },
      };
    }

    case 'user_message':
      return {
        ...push({ ...state, busy: true }, { kind: 'user', text: str(ev.text) }),
        meta: { ...state.meta, phase: 'reasoning' },
      };

    case 'model_delta': {
      // 流式增量：追加到"最后一条还在流的助手消息"上；没有就新开一条。
      const items = [...state.items];
      const last = items[items.length - 1];
      if (last && last.kind === 'assistant' && last.streaming) {
        items[items.length - 1] = { ...last, text: last.text + str(ev.text) };
        return { ...state, items };
      }
      return push(state, { kind: 'assistant', text: str(ev.text), streaming: true });
    }

    case 'final': {
      const text = str(ev.text);
      // 流式已经把正文拼好了：收尾时**要么补全、要么原样**，不能再追加一遍
      // （追加的后果是屏幕上出现两遍回答 —— 这是流式渲染最经典的踩坑）。
      const items = [...state.items];
      const last = items[items.length - 1];
      if (last && last.kind === 'assistant' && last.streaming) {
        const merged = last.text.length >= text.length ? last.text : text;
        items[items.length - 1] = {
          ...last,
          text: merged,
          streaming: false,
          round: num(ev.round) ?? last.round,
        };
        return { ...state, items, busy: false };
      }
      return { ...push(state, { kind: 'assistant', text, streaming: false, round: num(ev.round) }), busy: false };
    }

    case 'tool_start':
      return {
        ...push(state, {
          kind: 'tool',
          tool: str(ev.tool),
          target: str(ev.target) || undefined,
          status: 'running',
        }),
        meta: { ...state.meta, phase: 'tool_running' },
      };

    case 'tool_result': {
      const tool = str(ev.tool);
      const status: ToolStatus = str(ev.status) === 'SUCCESS' ? 'ok' : 'fail';
      const diff = extractDiff(ev.data);
      const items = [...state.items];
      // 从后往前找**同名且还在跑**的那张卡：工具是串行执行的，所以最近一张就是它。
      // 找不到（例如没收到 tool_start）就补一张 —— 宁可界面多一张卡，也别把结果丢了。
      for (let i = items.length - 1; i >= 0; i--) {
        const it = items[i]!;
        if (it.kind === 'tool' && it.status === 'running' && it.tool === tool) {
          items[i] = {
            ...it,
            status,
            elapsed: num(ev.elapsed),
            message: str(ev.message),
            exitCode: ev.exit_code === null || ev.exit_code === undefined ? null : num(ev.exit_code) ?? null,
            diff,
          };
          return { ...state, items, meta: { ...state.meta, tools: state.meta.tools + 1 } };
        }
      }
      return {
        ...push(state, {
          kind: 'tool',
          tool,
          status,
          elapsed: num(ev.elapsed),
          message: str(ev.message),
          exitCode: ev.exit_code === null || ev.exit_code === undefined ? null : num(ev.exit_code) ?? null,
          diff,
        }),
        meta: { ...state.meta, tools: state.meta.tools + 1 },
      };
    }

    case 'permission_request': {
      const tool = str(ev.tool);
      const reason = str(ev.reason);
      const next = push(state, { kind: 'permission', tool, reason });
      return {
        ...next,
        pendingPermission: { tool, reason, itemId: next.seq },
      };
    }

    case 'choice_request': {
      const kind = (['choose', 'confirm', 'text'].includes(str(ev.kind))
        ? str(ev.kind)
        : 'choose') as ChoiceKind;
      const title = str(ev.title);
      const next = push(state, { kind: 'notice', text: title });
      return {
        ...next,
        pendingChoice: {
          kind,
          title,
          options: Array.isArray(ev.options) ? ev.options.map(str) : [],
          defaultValue: str(ev.default),
          itemId: next.seq,
        },
      };
    }

    case 'notice': {
      const text = str(ev.text);
      if (!text.trim()) return state;
      return push(state, { kind: 'notice', text });
    }

    case 'status':
      return {
        ...state,
        meta: {
          ...state.meta,
          statusSegments: Array.isArray(ev.segments) ? ev.segments.map(str) : [],
        },
      };

    case 'model_request':
      return { ...state, busy: true, meta: { ...state.meta, rounds: Math.max(state.meta.rounds, num(ev.round) ?? 0) } };

    case 'session_end':
      return {
        ...state,
        busy: false,
        meta: {
          ...state.meta,
          ended: true,
          phase: '',
          rounds: num(ev.rounds) ?? state.meta.rounds,
          tools: num(ev.tools) ?? state.meta.tools,
        },
      };

    default:
      // 不认识的事件类型：**不报错也不显示**。协议会加新事件，旧前端遇到新的
      // 应该忽略并继续 —— 而不是崩掉或往屏幕上打一行内部类型名。
      return state;
  }
}

/** 把审批答案记下来：授权框据此关掉，转写区留一条"当时怎么答的"。 */
export function applyPermissionAnswer(
  state: State,
  decision: GrantDecision,
): State {
  if (!state.pendingPermission) return state;
  const { itemId } = state.pendingPermission;
  const items = state.items.map((it) =>
    it.id === itemId && it.kind === 'permission' ? { ...it, answered: decision } : it,
  );
  return { ...state, items, pendingPermission: null };
}

/** 答完选择框：待答清掉，并顺手把已答状态清空（与授权那条同口径）。 */
export function applyChoiceAnswer(state: State): State {
  if (!state.pendingChoice) return state;
  return { ...state, pendingChoice: null };
}

export function applyEvents(state: State, events: AceEvent[]): State {
  return events.reduce(applyEvent, state);
}

// ---------------------------------------------------------------- 取值助手

/**
 * 从 `tool_result.data` 里取 diff。
 *
 * 两道闸：必须是字符串，且必须**看起来像 unified diff**（`looksLikeDiff`）。
 * 第二道不能省 —— 工具输出里以 `+`/`-` 开头的行很常见，直接当 diff 画会把
 * 一张表格染成一屏红绿。
 */
function extractDiff(data: unknown): string | undefined {
  if (!data || typeof data !== 'object') return undefined;
  const raw = (data as Record<string, unknown>).diff;
  if (typeof raw !== 'string' || !raw) return undefined;
  return looksLikeDiff(raw) ? raw : undefined;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : v === undefined || v === null ? '' : String(v);
}

function num(v: unknown): number | undefined {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : undefined;
}
