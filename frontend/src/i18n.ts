/**
 * 轻量国际化 —— **直接读根级 `locales/*.json`**，不复制一份文案过来。
 *
 * 为什么不复制：文案会漂。Python 那边改了一句中文，TS 这边没跟，用户就会在同一个
 * 产品里看到两种说法。共用一份文件的代价只是"读文件"，换来的是单一真相源。
 *
 * 降级口径与 `ui/i18n.py` **逐条一致**（不是"差不多"）：当前语言 → `zh`（默认语言）
 * → 原样返回键名。最后那一档是有意的：界面上出现 `fullscreen_hint` 这种字符串时，
 * 你一眼就知道是缺翻译 —— 比显示空白或 "TODO" 强。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const SUPPORTED = ['zh', 'en', 'ja'] as const;
export type Lang = (typeof SUPPORTED)[number];
/** 与 `ui/i18n.py` 的 `DEFAULT_LANG` 一致。 */
export const DEFAULT_LANG: Lang = 'zh';

export type Dict = Record<string, string>;

/** `<root>/locales`：本文件在 `<root>/frontend/src/`。 */
export function localesDir(): string {
  return join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'locales');
}

export function loadDict(lang: Lang, baseDir = localesDir()): Dict {
  try {
    const raw = readFileSync(join(baseDir, `${lang}.json`), 'utf-8');
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Dict;
    }
  } catch {
    // 读不到就留空字典：`t()` 会一路降级到键名，界面仍然可用（不会崩）。
  }
  return {};
}

/**
 * 翻译器。构造时把三份字典读进来缓存 —— 界面每帧都会调 `t()`，
 * 每帧读一次文件是没必要的。
 */
export class I18n {
  private dicts: Record<string, Dict> = {};
  private lang: Lang;

  constructor(lang: Lang = DEFAULT_LANG, baseDir = localesDir()) {
    for (const l of SUPPORTED) this.dicts[l] = loadDict(l, baseDir);
    this.lang = this.dicts[lang] && Object.keys(this.dicts[lang]).length
      ? lang
      : DEFAULT_LANG;
  }

  get language(): Lang {
    return this.lang;
  }

  setLanguage(lang: Lang): void {
    if (SUPPORTED.includes(lang)) this.lang = lang;
  }

  /**
   * 取一条文案并做 `{name}` 占位符替换。
   *
   * 格式化失败（缺参数、值里有花括号）时**返回未格式化的原文**而不是抛 —— 一条文案
   * 渲染失败不该让整个界面崩掉。这与 `ui/i18n.py` 的处理一致。
   */
  t(key: string, params?: Record<string, string | number>): string {
    const raw = this.lookup(key);
    if (!params) return raw;
    try {
      return raw.replace(/\{(\w+)\}/g, (whole, name: string) =>
        Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : whole,
      );
    } catch {
      return raw;
    }
  }

  private lookup(key: string): string {
    const cur = this.dicts[this.lang]?.[key];
    if (typeof cur === 'string' && cur.length > 0) return cur;
    const fallback = this.dicts[DEFAULT_LANG]?.[key];
    if (typeof fallback === 'string' && fallback.length > 0) return fallback;
    return key; // 缺翻译就露键名 —— 一眼看得出来，比空白强
  }

  /** 供测试用：确认某语言确实载入了（而不是回退成了空字典）。 */
  dictSize(lang: Lang): number {
    return Object.keys(this.dicts[lang] ?? {}).length;
  }
}
