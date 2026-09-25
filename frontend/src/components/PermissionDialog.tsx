/**
 * 授权对话框 —— 整个"前端在另一个进程"能成立的**唯一理由**。
 *
 * 引擎需要一个答案时会阻塞等 `permission.answer`。所以这个框弹出来的时候，
 * 那边是真的停住等着的：**不答就一直等**（超时 600s 后 fail-close 拒绝）。
 *
 * 三个选项的顺序与 `ui/ace_turn.PERMISSION_OPTIONS` 一致（once / session / deny）——
 * 方向键的顺序、数字键的编号，两边必须一样，否则同一个用户在两套界面里会按错。
 *
 * 「本会话允许」是一次真实的权力扩张，所以它**不长得像**「就这一次」：
 * 单独一行、带说明。这是 Python 侧写在注释里的口径，这里照样遵守。
 */

import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';

import type { GrantDecision } from '../protocol/types.js';
import { gstr } from '../render/glyphs.js';

export interface PermissionDialogProps {
  tool: string;
  reason: string;
  t: (key: string, params?: Record<string, string | number>) => string;
  color: (token: string) => string | undefined;
  /** 递答案。调用方负责发给引擎 —— 本组件不碰协议。 */
  onAnswer: (decision: GrantDecision, feedback?: string) => void;
  /** 引擎已断开 / 会话已结束：框不该还能按。 */
  disabled?: boolean;
}

/** 顺序 = 界面上 1/2/3 = 方向键顺序，与 `ui/ace_turn.PERMISSION_OPTIONS` 对齐。 */
const OPTIONS: Array<{ decision: GrantDecision; key: string; hintKey: string }> = [
  { decision: 'once', key: 'perm_opt_once', hintKey: 'perm_opt_once_hint' },
  { decision: 'session', key: 'perm_opt_session', hintKey: 'perm_opt_session_hint' },
  { decision: 'deny', key: 'perm_opt_deny', hintKey: 'perm_opt_deny_hint' },
];

export function PermissionDialog({
  tool,
  reason,
  t,
  color,
  onAnswer,
  disabled = false,
}: PermissionDialogProps): React.ReactElement {
  const [cursor, setCursor] = useState(0);
  const [feedback, setFeedback] = useState('');
  const [typingReason, setTypingReason] = useState(false);

  useInput(
    (input, key) => {
      if (disabled) return;

      // 打理由的模式：把按键收进 buffer，回车时随拒绝一起递回去。
      // 为什么值得有这个：拒绝时给一句"别动这个文件，它在发布分支上"，
      // 模型能当场换个做法，而不是原地重试同一件事。
      if (typingReason) {
        if (key.return) {
          setTypingReason(false);
          onAnswer('deny', feedback);
          return;
        }
        if (key.escape) {
          setTypingReason(false);
          setFeedback('');
          return;
        }
        if (key.backspace || key.delete) {
          setFeedback((f) => f.slice(0, -1));
          return;
        }
        if (input && !key.ctrl && !key.meta) setFeedback((f) => f + input);
        return;
      }

      if (key.upArrow) setCursor((c) => (c - 1 + OPTIONS.length) % OPTIONS.length);
      if (key.downArrow) setCursor((c) => (c + 1) % OPTIONS.length);

      // Esc = 拒绝。这是全局约定（对话里 Esc 也是中断），授权框里沿用同一条。
      if (key.escape) {
        onAnswer('deny');
        return;
      }
      // `n <理由>` 的口径：拒绝时允许附一句理由。
      if (input === 'n' || input === 'N') {
        setTypingReason(true);
        return;
      }
      if (key.return) {
        onAnswer(OPTIONS[cursor]!.decision);
        return;
      }
      const idx = '123'.indexOf(input);
      if (idx >= 0 && idx < OPTIONS.length) {
        onAnswer(OPTIONS[idx]!.decision);
      }
    },
    { isActive: !disabled },
  );

  const box = (s: string): string => s;

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={color('warn')} paddingX={1}>
      <Text color={color('warn')} bold>
        {gstr(box('⚠ '))}
        {t('perm_request_title', { tool })}
      </Text>
      {reason ? <Text color={color('dim')}>{t('perm_reason', { reason })}</Text> : null}

      {typingReason ? (
        <Text>
          <Text color={color('dim')}>{t('perm_deny_feedback_prompt')} </Text>
          <Text color={color('text')}>{feedback}</Text>
          <Text color={color('dim')}>{gstr('▌')}</Text>
        </Text>
      ) : (
        OPTIONS.map((o, i) => (
          <Text key={o.decision} color={cursor === i ? color('accent') : color('text')}>
            {gstr(cursor === i ? '❯ ' : '  ')}
            {i + 1}. {t(o.key)}
            <Text color={color('dim')}>
              {'  '}
              {t(o.hintKey)}
            </Text>
          </Text>
        ))
      )}

      <Text color={color('dim')}>
        {typingReason ? t('perm_deny_feedback_hint') : t('perm_dialog_hint')}
      </Text>
    </Box>
  );
}
