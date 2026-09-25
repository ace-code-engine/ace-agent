/**
 * 状态行 —— "现在是什么状态"常驻一行。
 *
 * 与 Python 侧的 `ui/ace_layout.fit_status_line` 同一条口径：**宽度不够时先丢低优先级
 * 的分段**，而不是把整行截断成半句话。所以这里给每段标了优先级，按可用列宽裁剪。
 *
 * 权限档用 token 上色（只读蓝 / 可写黄 / 全权红）—— 这三档是产品契约里最要紧的一件事，
 * 它必须在任何宽度下都活着，所以优先级最高。
 */

import { Box, Text } from 'ink';
import React from 'react';

import { gstr } from '../render/glyphs.js';
import { displayWidth } from '../render/text.js';
import type { Meta } from '../state/store.js';

export interface StatusLineProps {
  meta: Meta;
  busy: boolean;
  color: (token: string) => string | undefined;
  width: number;
  t: (key: string, params?: Record<string, string | number>) => string;
}

interface Segment {
  name: string;
  text: string;
  priority: number; // 越小越先保留
  token?: string;
}

/** 权限档 → 语义 token。与 `ui/ace_theme.py` 的三个 perm_* token 对应。 */
export function permissionToken(permission: string | undefined): string {
  switch (permission) {
    case 'full':
      return 'perm_full';
    case 'write':
      return 'perm_write';
    default:
      return 'perm_ro';
  }
}

export function buildSegments(meta: Meta, busy: boolean, t: StatusLineProps['t']): Segment[] {
  const segs: Segment[] = [];
  // 权限排第一：它是"我现在有多大权力"的常驻答案，最不能丢。
  if (meta.permission) {
    segs.push({
      name: 'permission',
      text: t('footer_permission', { level: meta.permission }),
      priority: 1,
      token: permissionToken(meta.permission),
    });
  }
  if (busy) segs.push({ name: 'busy', text: t('status_busy'), priority: 2, token: 'dim' });
  if (meta.mock) segs.push({ name: 'mock', text: 'mock', priority: 3, token: 'warn' });
  if (meta.model) segs.push({ name: 'model', text: meta.model, priority: 10 });
  if (meta.sandbox && meta.sandbox !== 'off') {
    segs.push({ name: 'sandbox', text: t('footer_sandbox', { mode: meta.sandbox }), priority: 11, token: 'info' });
  }
  if (meta.tools > 0) {
    segs.push({ name: 'tools', text: t('footer_tools', { n: meta.tools }), priority: 20, token: 'dim' });
  }
  if (meta.version) segs.push({ name: 'version', text: `v${meta.version}`, priority: 30, token: 'dim' });
  return segs;
}

/** 按可用列宽裁剪分段：丢了谁就补一个 `+n`，不静默少东西。 */
export function fitSegments(segs: Segment[], width: number): Segment[] {
  let kept = [...segs].sort((a, b) => a.priority - b.priority);
  const render = (xs: Segment[]): string => xs.map((s) => s.text).join(' · ');

  // **按显示宽度比，不按码点**：分段里有中文（「权限 readonly」），
  // 用 `.length` 会把 8 个汉字当 8 列（实际 16 列），于是状态行在窄终端里
  // 顶出去被折行、把整个版面推歪 —— 而它恰恰是**常驻**的那一行。
  while (kept.length > 1 && displayWidth(render(kept)) > width) {
    // 丢优先级最低的那个（数组已按优先级排好，尾部就是最低的）
    kept = kept.slice(0, -1);
  }
  const dropped = segs.length - kept.length;
  const out = kept.map((s) => ({ ...s }));
  if (dropped > 0) {
    out.push({ name: 'more', text: `+${dropped}`, priority: 99, token: 'dim' });
  }
  // 还原成原来的语义顺序（裁剪顺序 ≠ 显示顺序）
  const order = new Map(segs.map((s, i) => [s.name, i]));
  return out.sort((a, b) => (order.get(a.name) ?? 99) - (order.get(b.name) ?? 99));
}

export function StatusLine({ meta, busy, color, width, t }: StatusLineProps): React.ReactElement {
  const segs = fitSegments(buildSegments(meta, busy, t), Math.max(10, width));
  return (
    <Box>
      <Text color={color('dim')}> </Text>
      {segs.map((s, i) => (
        <Text key={s.name}>
          {i > 0 ? <Text color={color('border')}>{gstr(' · ')}</Text> : null}
          <Text color={color(s.token ?? 'text')}>{s.text}</Text>
        </Text>
      ))}
    </Box>
  );
}
