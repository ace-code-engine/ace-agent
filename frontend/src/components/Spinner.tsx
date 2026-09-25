/**
 * 等待指示器 —— 一轮跑动期间唯一在动的东西。
 *
 * 为什么它重要：没有它，界面在等待时**是死的**。用户分不清"它在想"和"它挂了"，
 * 而这两者的后续动作完全相反（等 vs 中断）。Python 侧同样有这个问题，
 * 而且它还有一个更糟的版本 —— 全屏路径下 spinner 的输出被整个丢掉，界面直接冻结。
 *
 * 动词按**阶段**选，而不是随机轮换：`waiting` 配"连接"、`reasoning` 配"思考"，
 * 随机轮换会让"现在到底卡在哪一步"这条信息消失。
 */

import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';

import { gstr } from '../render/glyphs.js';
import { frameAt, phaseInterval, type Phase } from '../render/spinner.js';

export interface SpinnerProps {
  phase: Phase | string;
  t: (key: string, params?: Record<string, string | number>) => string;
  color: (token: string) => string | undefined;
  /** 无动效：恒取第一帧。前庭敏感的用户用这个。 */
  reducedMotion?: boolean;
  /** 起始时刻（毫秒）。测试可以注入固定值。 */
  startedAt?: number;
}

/** 阶段 → 动词序号（`spin_verb_1..5`）。一一对应，稳定可断言。 */
export const PHASE_VERB: Record<string, number> = {
  waiting: 1,
  reasoning: 2,
  answering: 3,
  tool_args: 4,
  tool_running: 5,
};

export function verbKeyFor(phase: string | undefined): string {
  const n = PHASE_VERB[String(phase)] ?? 2;
  return `spin_verb_${n}`;
}

export function Spinner({
  phase,
  t,
  color,
  reducedMotion = false,
  startedAt,
}: SpinnerProps): React.ReactElement {
  const [elapsed, setElapsed] = useState(0);
  const start = React.useRef(startedAt ?? Date.now());

  useEffect(() => {
    // 帧间隔本身就是"多久动一下"，所以定时器跟着它走：慢阶段不必每秒醒 12 次。
    const ms = Math.max(50, Math.round(phaseInterval(phase) * 1000));
    const id = setInterval(() => {
      setElapsed((Date.now() - start.current) / 1000);
    }, ms);
    return () => clearInterval(id);
  }, [phase]);

  // 过 `g()`：cp936 下 `◐◓◑◒` 印不出来，spinner 会变成一串乱码
  const glyph = gstr(frameAt(phase, elapsed, reducedMotion));
  const secs = Math.floor(elapsed);

  return (
    <Box>
      <Text color={color('accent')}>{glyph} </Text>
      <Text color={color('dim')}>{t(verbKeyFor(phase))}</Text>
      {secs > 0 ? (
        <Text color={color('dim')}>
          {' '}
          {t('spin_elapsed', { secs })}
        </Text>
      ) : null}
    </Box>
  );
}
