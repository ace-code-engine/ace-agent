/**
 * `tools/preview.ts` 的守门测试。
 *
 * 为什么一个"给人看的脚本"要有测试：它渲的是真组件，组件改名/改 props 之后它会崩，
 * 而**崩了没人知道** —— 那正是"接手第一件事是拿眼睛看一眼"这件事一直没有判据的原因。
 * 这几条断言只保证它还在跑、每帧有内容、几个关键画面确实出现了；
 * 好不好看仍然只能由人看（`npm run preview`）。
 */

import chalk from 'chalk';
import { describe, expect, it } from 'vitest';

import { buildPreviewFrames } from '../tools/preview.js';

describe('npm run preview', () => {
  it('跑完脚本，每一帧都有内容（空白帧 = 脚本或组件坏了）', async () => {
    const frames = await buildPreviewFrames(true);
    expect(frames.length).toBeGreaterThan(5);
    for (const f of frames) {
      expect(f.title.length).toBeGreaterThan(0);
      expect(f.frame.trim().length).toBeGreaterThan(0);
    }
  });

  it('关键画面都在：底栏分段 / 流式增量 / 工具卡片 / 审批框 / 任务树', async () => {
    const frames = await buildPreviewFrames(true);
    const all = frames.map((f) => f.frame).join('\n');
    // 底栏那一段来自引擎的 status 事件（H 系列新接的发射点）
    expect(all).toContain('上下文 12%');
    // 流式增量（model_delta）真的逐拍长出来了
    expect(all).toContain('我先读一下 README');
    // 工具卡片带 diff
    expect(all).toContain('README.md');
    expect(all).toContain('HooH · 互');
    // 审批框三态
    expect(all).toContain('rm -rf build/');
    // 任务树（Ctrl+T 之后的帧）
    expect(all).toContain('补全菜单');
  });

  it('`--plain` 与带色两版**文字完全一致**（剥色不该动内容）', async () => {
    const plain = await buildPreviewFrames(true);
    const colored = await buildPreviewFrames(false);
    expect(plain.map((f) => f.frame)).toEqual(
      colored.map((f) => f.frame.replace(/\u001b\[[0-9;?]*[ -/]*[@-~]/g, '')),
    );
    expect(plain.map((f) => f.frame).join('')).not.toMatch(/\u001b\[/);
  });

  it('颜色由 chalk 决定 —— 非 TTY 下没有 ANSI，这是**环境**不是脚本坏了', () => {
    // 记一笔：`ink-testing-library` 的 stdout 不是 TTY，chalk 于是把颜色关掉，
    // 所以 CI 里拿到的帧是**无色的**（排版照旧可验，配色不行）。
    // 要真的看配色，在启动 node **之前**设 FORCE_COLOR（chalk 在 import 时就定级了）：
    //     PowerShell:  $env:FORCE_COLOR=1; npm run preview
    //     bash:        FORCE_COLOR=1 npm run preview
    // 这一条只断言"两版文字一致"（上一用例），不假装能验颜色。
    expect(chalk.level).toBeTypeOf('number');
  });
});
