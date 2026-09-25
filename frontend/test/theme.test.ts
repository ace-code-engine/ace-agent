/**
 * 主题层测试 —— 重点是**跨语言一致性**。
 *
 * 项目里原本就有三套色系各管各的（`ace_theme.tc()` 返回 Rich 名 →
 * `ace_layout.context_state_ansi` 返回裸 ANSI 名 → `ace_fullscreen` 内联十六进制）。
 * Ink 前端是第四套。防它漂的办法不是"写文档提醒"，是**直接读那个 .py 文件比对** ——
 * 那边改了 token 名这边没跟，这些用例就红。
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  PALETTES,
  TOKENS,
  bgFor,
  colorFor,
  detectTheme,
  isBackgroundToken,
} from '../src/theme/tokens.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** 从 `ui/ace_theme.py` 的 `THEMES` 里取出 dark 调色板的 token 名。 */
function pythonTokens(): string[] {
  const src = readFileSync(join(ROOT, 'ui', 'ace_theme.py'), 'utf-8');
  const dark = src.split('"dark"')[1] ?? '';
  const body = dark.split('"light"')[0] ?? '';
  return [...body.matchAll(/^\s*"([a-z_]+)"\s*:/gm)].map((m) => m[1]!);
}

describe('主题 token 与 Python 侧一致', () => {
  it('token 名集合与 ui/ace_theme.py 完全相同', () => {
    const py = pythonTokens();
    expect(py.length).toBeGreaterThan(10);
    expect([...TOKENS].sort()).toEqual([...py].sort());
  });

  it('dark / light 两套调色板的 token 集合相同', () => {
    expect(Object.keys(PALETTES.dark).sort()).toEqual(Object.keys(PALETTES.light).sort());
  });

  it('17 个 token 一个不少', () => {
    expect(TOKENS.length).toBe(17);
    expect(new Set(TOKENS).size).toBe(17);
  });
});

describe('主题值与 Python 侧一致', () => {
  /** 从 .py 里抠出 dark 的 {token: ansiname}。 */
  function pythonPalette(theme: 'dark' | 'light'): Record<string, string> {
    const src = readFileSync(join(ROOT, 'ui', 'ace_theme.py'), 'utf-8');
    const block = src.split(`"${theme}":`)[1]?.split('},')[0] ?? '';
    const out: Record<string, string> = {};
    for (const m of block.matchAll(/"([a-z_]+)"\s*:\s*"([^"]+)"/g)) {
      out[m[1]!] = m[2]!;
    }
    return out;
  }

  it('dark 调色板逐条相同（改了这边没改那边会红）', () => {
    expect(pythonPalette('dark')).toEqual(PALETTES.dark);
  });

  it('light 调色板逐条相同', () => {
    expect(pythonPalette('light')).toEqual(PALETTES.light);
  });
});

describe('色值解析', () => {
  it('**前景 token 解析成 chalk 色名，不是 hex**（否则会钉死终端调色板）', () => {
    // 这一条守的是一个真踩过的坑：第一版把色名转成了 xterm 默认 16 色 hex
    // （ansiyellow → #808000），结果黄色渲染成橄榄绿、提示符一片绿，
    // 而且所有颜色不再跟随用户的终端主题。
    for (const token of TOKENS) {
      if (isBackgroundToken(token)) continue;
      const c = colorFor(token, 'dark');
      expect(c, `dark/${token}`).toBeTruthy();
      expect(c, `dark/${token} 不该是 hex`).not.toMatch(/^#/);
    }
  });

  it('底色 token 走 `bgFor`（那些是故意写死 RGB 的），`colorFor` 对它返回 undefined', () => {
    expect(isBackgroundToken('user_bg')).toBe(true);
    expect(bgFor('user_bg', 'dark')).toMatch(/^#[0-9a-f]{6}$/i);
    expect(colorFor('user_bg', 'dark')).toBeUndefined();
  });

  it('前景 token 的 `bgFor` 也是 undefined（两边不越界）', () => {
    expect(bgFor('text', 'dark')).toBeUndefined();
    expect(isBackgroundToken('text')).toBe(false);
  });

  it('未注册的 token 两边都给 undefined（= 终端默认色），不抛', () => {
    expect(colorFor('不存在的token', 'dark')).toBeUndefined();
    expect(bgFor('不存在的token', 'dark')).toBeUndefined();
  });

  it('映射到的是 chalk 认得的色名（写错的色名会静默不着色）', () => {
    const known = new Set([
      'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white', 'gray',
      'redBright', 'greenBright', 'yellowBright', 'blueBright',
      'magentaBright', 'cyanBright', 'whiteBright',
    ]);
    for (const token of TOKENS) {
      if (isBackgroundToken(token)) continue;
      expect(known.has(colorFor(token, 'dark')!), `dark/${token}`).toBe(true);
    }
  });
});

describe('主题检测口径与 ace_theme.detect_theme 一致', () => {
  it('ACE_THEME 优先', () => {
    expect(detectTheme({ ACE_THEME: 'light', COLORFGBG: '15;0' })).toBe('light');
    expect(detectTheme({ ACE_THEME: 'dark', COLORFGBG: '0;15' })).toBe('dark');
  });

  it('COLORFGBG：背景色号 >= 8 视为浅色底', () => {
    expect(detectTheme({ COLORFGBG: '15;0' })).toBe('dark');
    expect(detectTheme({ COLORFGBG: '0;15' })).toBe('light');
  });

  it('都没有时默认深色', () => {
    expect(detectTheme({})).toBe('dark');
  });
});
