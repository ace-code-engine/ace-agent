/**
 * 启动器守卫 —— 钉住 `ace.cmd` 调用本前端的**形态**。
 *
 * 为什么需要它：`ace` 这条路出过一次只有**真终端里才炸**的错 ——
 * tsx 是从**当前目录**找 `tsconfig.json` 的，不是从被调用文件的位置找。
 * 从仓库根调它 → 找不到 tsconfig → 退回经典 JSX 转换 → 第一次 `render()`
 * 就 `React is not defined`。而 `npm start` 一直是好的（那儿 cwd 就是 frontend），
 * 于是单元测试、类型检查、集成测试**全绿**，只有用户按下 `ace` 才看得见。
 *
 * 这类"测试全绿、真机才炸"的缺口，只能靠读启动脚本本身来堵。
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

const raw = readFileSync(join(ROOT, 'ace.cmd'), 'utf8');
const lines = raw.split(/\r?\n/);

/**
 * 调 tsx 的那一行。
 *
 * 按 `index.tsx` 定位，**不能**按 `tsx` + `cli.mjs` 找 —— 上面那条
 * `if not exist "...\tsx\dist\cli.mjs"` 的存在性检查两个词都有，会先被命中，
 * 于是断言全落在错的行上（这个坑本测试自己踩过一次）。
 */
const tsxLineIndex = lines.findIndex(
  (l) => l.includes('index.tsx') && l.trimStart().startsWith('node '),
);
const tsxLine = tsxLineIndex >= 0 ? lines[tsxLineIndex]! : '';

describe('ace.cmd · 批处理文件的两条硬约束', () => {
  it('行尾是 CRLF（LF-only 会让 cmd.exe 错位重读，把行片段当命令执行）', () => {
    const crlf = (raw.match(/\r\n/g) ?? []).length;
    const bareLf = (raw.match(/(?<!\r)\n/g) ?? []).length;
    expect(crlf).toBeGreaterThan(50);
    expect(bareLf).toBe(0);
  });

  it('纯 ASCII（多字节字符会让 cmd.exe 按字节偏移错位重读）', () => {
    // eslint-disable-next-line no-control-regex
    expect(/^[\x00-\x7f]*$/.test(raw)).toBe(true);
  });
});

describe('ace.cmd · 调起前端的形态', () => {
  it('确实存在调用 tsx 的那一行（说明前端真的被接上了）', () => {
    expect(tsxLineIndex).toBeGreaterThan(0);
    expect(tsxLine).toContain('index.tsx');
  });

  it('**在 frontend 目录下**调用 tsx —— 否则拿不到 tsconfig，JSX 转换会退化成经典模式', () => {
    const before = lines.slice(0, tsxLineIndex).join('\n');
    const after = lines.slice(tsxLineIndex + 1).join('\n');
    expect(before).toContain('pushd'); // 先切进 frontend
    expect(before).toContain('frontend');
    expect(after).toContain('popd'); // 用完切回来
  });

  it('tsx 那一行的路径是**相对于 frontend** 的（带 frontend\\ 前缀就用错了 cwd）', () => {
    expect(tsxLine).not.toMatch(/["']frontend[\\/]/);
  });

  it('「找不到 tsconfig」这个坑有注释留在原地（下一个人改这里时会看见）', () => {
    const before = lines.slice(Math.max(0, tsxLineIndex - 8), tsxLineIndex).join('\n');
    expect(before).toContain('tsconfig');
  });
});

describe('ace.cmd · 回退路径', () => {
  it('保留 Python 那条路（前端不可用时必须还能用）', () => {
    expect(raw).toContain('ai_code.py');
    expect(raw).toContain(':ace_python');
  });

  it('有强制走 Python 的开关（ACE_LEGACY_UI）', () => {
    expect(raw).toContain('ACE_LEGACY_UI');
  });

  it('前端依赖缺失时**说清楚**再回退，不静默', () => {
    expect(raw).toContain('node_modules');
    expect(raw).toMatch(/[Ff]alling back/);
  });
});
