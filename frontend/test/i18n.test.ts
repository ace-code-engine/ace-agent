/**
 * i18n 测试 —— 重点是「跟 Python 共用同一份字典」这件事真的成立。
 *
 * 共用文件的价值全在"如果没读上就等于没共用"：读不到时 `t()` 会一路降级到键名，
 * 界面不会崩，但会满屏 `fullscreen_hint` 这种字符串 —— 一个**安静**的失败。
 * 所以这里直接断言字典载入了、键数与 `.py` 侧一致。
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { DEFAULT_LANG, I18n, SUPPORTED, loadDict, localesDir } from '../src/i18n.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

describe('字典载入', () => {
  it('默认语言是 zh（与 ui/i18n.py 的 DEFAULT_LANG 一致）', () => {
    const src = readFileSync(join(ROOT, 'ui', 'i18n.py'), 'utf-8');
    const m = src.match(/DEFAULT_LANG\s*=\s*"([a-z]+)"/);
    expect(m).not.toBeNull();
    expect(m![1]).toBe(DEFAULT_LANG);
  });

  it('三种语言与 ui/i18n.py 的 SUPPORTED 一致', () => {
    const src = readFileSync(join(ROOT, 'ui', 'i18n.py'), 'utf-8');
    const block = src.match(/SUPPORTED\s*=\s*\(([^)]*)\)/)?.[1] ?? '';
    const py = [...block.matchAll(/"([a-z]+)"/g)].map((m) => m[1]!).sort();
    expect([...SUPPORTED].sort()).toEqual(py);
  });

  it('locales 目录指向仓库根级的那一份（不是副本）', () => {
    expect(localesDir().replace(/\\/g, '/')).toMatch(/\/locales$/);
    expect(loadDict('zh').fullscreen_hint).toBeTruthy();
  });

  it('三语字典都真的载入了（没读上会退化成空字典）', () => {
    const i18n = new I18n();
    for (const lang of SUPPORTED) {
      expect(i18n.dictSize(lang), lang).toBeGreaterThan(500);
    }
  });

  it('三语键数一致', () => {
    const i18n = new I18n();
    const sizes = SUPPORTED.map((l) => i18n.dictSize(l));
    expect(new Set(sizes).size).toBe(1);
  });
});

describe('翻译与降级', () => {
  it('取到的是人话，不是键名', () => {
    const i18n = new I18n('zh');
    expect(i18n.t('fullscreen_hint')).not.toBe('fullscreen_hint');
  });

  it('占位符替换', () => {
    const i18n = new I18n('zh');
    expect(i18n.t('perm_request_title', { tool: 'file_write' })).toContain('file_write');
  });

  it('未知键**原样返回键名**（一眼看得出缺翻译，比空白强）', () => {
    const i18n = new I18n('zh');
    expect(i18n.t('这个键不存在_zzz')).toBe('这个键不存在_zzz');
  });

  it('缺参数时返回未格式化的原文，不抛', () => {
    const i18n = new I18n('zh');
    const got = i18n.t('perm_request_title');
    expect(typeof got).toBe('string');
    expect(got.length).toBeGreaterThan(0);
  });

  it('切换语言真的换掉文案', () => {
    const i18n = new I18n('zh');
    const zh = i18n.t('perm_opt_once');
    i18n.setLanguage('en');
    const en = i18n.t('perm_opt_once');
    expect(zh).not.toBe(en);
  });

  it('非法语言被拒，保持原语言', () => {
    const i18n = new I18n('zh');
    i18n.setLanguage('klingon' as never);
    expect(i18n.language).toBe('zh');
  });
});

describe('为前端新增的键确实就位', () => {
  it.each([
    'perm_opt_once_hint',
    'perm_opt_session_hint',
    'perm_opt_deny_hint',
    'perm_deny_feedback_prompt',
    'perm_dialog_hint',
    'footer_permission',
    'input_busy_hint',
  ])('%s 三语都有', (key) => {
    for (const lang of SUPPORTED) {
      const dict = loadDict(lang);
      expect(dict[key], `${lang}.${key}`).toBeTruthy();
    }
  });
});
