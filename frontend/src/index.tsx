#!/usr/bin/env node
/**
 * 入口 —— 起引擎、握手、把界面挂上。
 *
 * 所有"碰外部世界"的动作都在这里（读 argv、读环境、起进程、渲染），
 * 组件层保持纯粹。这样界面部分能在测试里被假事件驱动，不必起 Python。
 */

import { Box, Text, render } from 'ink';
import React from 'react';

import { App } from './App.js';
import { I18n, SUPPORTED, type Lang } from './i18n.js';
import { AceClient } from './protocol/client.js';
import { setGlyphs } from './render/glyphs.js';
import type { BuildMenuOptions } from './render/menu.js';
import { colorFor, detectTheme, type Token } from './theme/tokens.js';

interface Args {
  projectRoot?: string;
  mock: boolean;
  lang?: Lang;
  stream: boolean;
  message?: string;
  python?: string;
  help: boolean;
}

function parseArgs(argv: string[]): Args {
  const out: Args = { mock: false, stream: true, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    const next = (): string | undefined => argv[++i];
    switch (a) {
      case '--project-root':
        out.projectRoot = next();
        break;
      case '--mock':
        out.mock = true;
        break;
      case '--lang': {
        const v = next();
        if (v && (SUPPORTED as readonly string[]).includes(v)) out.lang = v as Lang;
        break;
      }
      case '--no-stream':
        out.stream = false;
        break;
      case '--message':
      case '-m':
        out.message = next();
        break;
      case '--python':
        out.python = next();
        break;
      case '--help':
      case '-h':
        out.help = true;
        break;
      default:
        // 不认识的参数：**不静默忽略**。静默忽略的症状是"这个开关怎么没生效"，
        // 而用户会以为是功能坏了。
        if (a.startsWith('-')) {
          process.stderr.write(`不认识的参数：${a}（用 --help 看用法）\n`);
          process.exit(2);
        }
    }
  }
  return out;
}

/**
 * 渲染期错误的兜底 —— **没有它，"闪退"是静默的**。
 *
 * Ink 遇到未捕获的渲染错误会卸载整棵树、`waitUntilExit` 随即 resolve，
 * 于是进程正常退出、终端上一片干净 —— 用户看到的就是"卡一下然后窗口没了"，
 * 拿不到任何线索。有了边界，错误会留在屏幕上、细节打到 stderr。
 */
class Boundary extends React.Component<
  { children: React.ReactNode },
  { err: Error | null }
> {
  override state: { err: Error | null } = { err: null };

  static getDerivedStateFromError(err: Error): { err: Error } {
    return { err };
  }

  override componentDidCatch(err: Error): void {
    process.stderr.write(
      `\n[前端] 界面渲染出错：\n${err?.stack ?? String(err)}\n` +
        `（这是前端的 bug，不是模型的输出问题。请把这段贴给维护者。）\n`,
    );
  }

  override render(): React.ReactNode {
    if (this.state.err) {
      return (
        <Box flexDirection="column">
          <Text color="red">{'界面渲染出错（细节已打到 stderr）'}</Text>
          <Text color="gray">{String(this.state.err.message ?? this.state.err)}</Text>
          <Text color="gray">{'按 Ctrl+C 退出；把 stderr 那段贴给维护者。'}</Text>
        </Box>
      );
    }
    return this.props.children;
  }
}

const HELP = `ACE 前端（TypeScript + Ink）

用法：
  npm start -- [选项]

选项：
  --project-root <dir>  项目根目录（含 ai_code.py）。默认取本仓库根。
  --mock                引擎离线跑（不需要 API key）
  --lang zh|en|ja       界面语言（默认 zh，与 Python 侧一致）
  --message, -m <text>  启动后立刻发一句
  --python <path>       Python 解释器（默认自动探测；ACE_PYTHON 环境变量优先）
  --no-stream           不要流式增量（只收 final）
  --help, -h            显示这段
`;

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(HELP);
    return 0;
  }

  const i18n = new I18n(args.lang);
  const theme = detectTheme();
  const colorOf = (token: string): string | undefined => colorFor(token as Token, theme);

  // Ink 需要真终端（raw 模式）。不是 TTY 时它会**抛一段 React 堆栈** —— 用户看到的是
  // 一坨红字，而原因其实是"你在管道里跑"。这里提前拦住并说清楚，顺带指一条明路。
  // （Python 侧的同款处理：全屏在终端太小时回退 REPL，并如实说明。）
  if (!process.stdin.isTTY) {
    process.stderr.write(
      i18n.t('frontend_needs_tty') + '\n\n' + i18n.t('frontend_needs_tty_hint') + '\n',
    );
    return 2;
  }

  const client = new AceClient({
    ...(args.projectRoot !== undefined ? { projectRoot: args.projectRoot } : {}),
    ...(args.python !== undefined ? { pythonPath: args.python } : {}),
    extraArgs: args.mock ? ['--mock'] : [],
  });

  let caps;
  try {
    caps = await client.start(args.stream);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    process.stderr.write(`\n引擎没能启动：${msg}\n`);
    // 把引擎的 stderr 原样带出来 —— 真正的原因几乎总在那里（缺依赖、路径不对、
    // 解释器是那个 Store 存根）。不打印的话用户只看到"没能启动"，无从下手。
    if (client.stderrText.trim()) {
      process.stderr.write(`\n引擎 stderr：\n${client.stderrText.trim()}\n`);
    }
    client.close();
    return 1;
  }

  // 字形降级表：引擎按**当前控制台编码**算好的。必须在 render 之前设好，
  // 否则首屏那一帧就已经印出控制台画不出的字了（cp936 下提示符会变成乱码）。
  setGlyphs(caps.glyphs);

  // 补全菜单的候选来自握手：命令表由引擎给（那是唯一真相源），
  // 描述与分组是 **i18n 键**，由前端自己查字典 —— 这样 `/lang` 切换后菜单会跟着变。
  const menuOptions: BuildMenuOptions = {
    commands: caps.commands ?? {},
    groupOf: (name) => caps.command_groups?.[name] ?? 'group_more',
    translate: (k) => i18n.t(k),
  };

  const app = render(
    <Boundary>
      <App
        client={client}
        t={(k, p) => i18n.t(k, p)}
        colorOf={colorOf}
        menuOptions={menuOptions}
        {...(args.message !== undefined ? { initialMessage: args.message } : {})}
      />
    </Boundary>,
  );

  const onSignal = (): void => {
    // `shutdown()` 是幂等的，所以信号与 Ink 的按键那条路同时走到这里也不会打架
    void client.shutdown().finally(() => process.exit(0));
  };
  process.on('SIGINT', onSignal);
  process.on('SIGTERM', onSignal);

  await app.waitUntilExit();
  await client.shutdown();
  return 0;
}

// 全局兜底：**任何未捕获的错误都必须留下痕迹**。
//
// 没有这两个处理器时，一个 promise 被 reject 而没人接、或一个回调里抛出去，
// Node 会直接把进程带走 —— 终端上一片干净，用户只看到"闪退"，无从查起。
// 这里先把话打出来，再退出；`uncaughtException` 之后进程状态已不可信，不硬撑。
process.on('unhandledRejection', (e: unknown) => {
  process.stderr.write(
    `\n[前端] 未处理的 Promise 拒绝：\n${e instanceof Error ? e.stack ?? e.message : String(e)}\n`,
  );
});
process.on('uncaughtException', (e: unknown) => {
  process.stderr.write(
    `\n[前端] 未捕获的异常：\n${e instanceof Error ? e.stack ?? e.message : String(e)}\n`,
  );
  process.exit(1);
});

main()
  .then((code) => process.exit(code))
  .catch((e: unknown) => {
    process.stderr.write(`前端异常退出：${e instanceof Error ? e.stack ?? e.message : String(e)}\n`);
    process.exit(1);
  });
