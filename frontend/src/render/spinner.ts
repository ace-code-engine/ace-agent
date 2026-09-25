/**
 * 等待指示器的纯逻辑 —— **字形与帧间隔逐条照抄 `ui/ace_spinner.py`**。
 *
 * 为什么不能自己挑一套好看的：那边的注释写着「**速度本身是语义**」——
 * `waiting` 快（0.08s，等首字节，网络在动）、`reasoning` 慢（0.24s，模型在推）、
 * `tool_running` 中等（0.16s，工具在跑）。用户看速度就能大致判断"现在卡在哪一步"。
 * 两套前端用不同速度，这个信息就废了。`test/spinner.test.ts` 会读那个 .py 比对。
 *
 * 纯逻辑：不算时间、不订阅定时器（`elapsed` 由调用方传），所以可穷举测。
 */

export const PHASES = ['waiting', 'reasoning', 'answering', 'tool_args', 'tool_running'] as const;
export type Phase = (typeof PHASES)[number];

export const DEFAULT_PHASE: Phase = 'reasoning';

/** 帧序列 + 帧间隔（秒）。与 `ace_spinner._GLYPHS` 逐条一致。 */
export const GLYPHS: Record<Phase, { frames: string[]; interval: number }> = {
  waiting: { frames: ['·', '˙', '•', '˙'], interval: 0.08 },
  reasoning: { frames: ['◐', '◓', '◑', '◒'], interval: 0.24 },
  answering: { frames: ['◈', '◇', '◆', '◇'], interval: 0.12 },
  tool_args: { frames: ['▖', '▘', '▝', '▗'], interval: 0.1 },
  tool_running: { frames: ['▁', '▃', '▅', '▇', '▅', '▃'], interval: 0.16 },
};

export function normPhase(phase: string | undefined): Phase {
  return (PHASES as readonly string[]).includes(String(phase))
    ? (phase as Phase)
    : DEFAULT_PHASE;
}

export function framesFor(phase: string | undefined): string[] {
  return [...GLYPHS[normPhase(phase)].frames];
}

export function phaseInterval(phase: string | undefined): number {
  return GLYPHS[normPhase(phase)].interval;
}

/**
 * 当前该画哪一帧。
 *
 * `reducedMotion` 时**恒取第一帧** —— 不是"慢一点"，是完全不动。
 * 对前庭敏感的用户，缓慢旋转同样难受；降级要降到底，不能只降一半。
 */
export function frameAt(
  phase: string | undefined,
  elapsed: number,
  reducedMotion = false,
): string {
  const frames = framesFor(phase);
  if (reducedMotion) return frames[0]!;
  const idx = Math.floor(Math.max(0, elapsed) / phaseInterval(phase)) % frames.length;
  return frames[idx]!;
}
