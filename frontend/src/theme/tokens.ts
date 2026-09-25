/**
 * 语义主题 token —— **唯一真相源是 `ui/ace_theme.py`**。
 *
 * 为什么这份要跟 Python 那边逐字对齐：项目里原本就有三套色系各管各的
 * （`ace_theme.tc()` 返回 Rich 名 → `ace_layout.context_state_ansi` 返回裸 ANSI 名 →
 * `ace_fullscreen` 内联十六进制），三者之间没有任何转换层。Ink 前端如果再做第四套，
 * 就是四套并存 —— 换一次色要改四个地方，其中三个必然被漏掉。
 *
 * 所以这里的纪律是：**token 名与 ANSI 色名照抄 `ace_theme.py`**，TS 侧只多做一步
 * 「ANSI 色名 → hex」（Ink/chalk 认 hex，不认 Rich 的色名）。`test/tokens.test.ts`
 * 会直接读那个 .py 文件比对 token 名集合 —— 那边改名这边没跟，测试就红。
 */

/** 17 个语义 token，顺序与 `ui/ace_theme.py` 一致。 */
export const TOKENS = [
  'text',
  'dim',
  'accent',
  'border',
  'error',
  'success',
  'warn',
  'info',
  'user_bg',
  'tool_pending',
  'tool_ok',
  'tool_fail',
  'perm_ro',
  'perm_write',
  'perm_full',
  'goal_active',
  'goal_paused',
] as const;

export type Token = (typeof TOKENS)[number];

/**
 * ANSI 色名 → chalk 色名。
 *
 * ## 为什么**不能**转成十六进制（踩过）
 *
 * 第一版我把它转成了 xterm 的默认 16 色 hex（`ansiyellow → #808000`）。
 * 结果：黄色渲染成**橄榄绿**，提示符一片绿 —— 而且**所有颜色都不再跟随用户的终端主题**。
 *
 * 原因是 `ace_theme.py` 存的是「**色名**」不是「色值」：`ansiyellow` 的语义是
 * "用终端调色板里的 yellow"（多数主题配成亮黄），不是"用 #808000"。
 * Python 侧发的是色名，由终端决定实际 RGB；转成 hex 就把这个决定权抢走了。
 *
 * 所以这里映射到 **chalk 的色名**（`yellow` / `cyanBright`…）—— chalk 同样发
 * "用 3 号色"这种 SGR，终端照自己的调色板渲染。行为与 Python 侧一致。
 *
 * 只有 `bg:#RRGGBB` 那类**故意写死 RGB** 的底色 token 才用 hex（见 `bgFor`）。
 */
export const ANSI_CHALK: Record<string, string> = {
  ansiblack: 'black',
  ansired: 'red',
  ansigreen: 'green',
  ansiyellow: 'yellow',
  ansiblue: 'blue',
  ansimagenta: 'magenta',
  ansicyan: 'cyan',
  ansiwhite: 'white',
  ansibrightblack: 'gray', // chalk 的 gray == 亮黑（8 号色）
  ansibrightred: 'redBright',
  ansibrightgreen: 'greenBright',
  ansibrightyellow: 'yellowBright',
  ansibrightblue: 'blueBright',
  ansibrightmagenta: 'magentaBright',
  ansibrightcyan: 'cyanBright',
  ansibrightwhite: 'whiteBright',
};

/**
 * 双套调色板 —— 值逐条照抄 `ui/ace_theme.py` 的 `THEMES`。
 * 注释里保留 Python 那侧对每个 token 的中文说明，免得这边改色时不知道它管什么。
 */
export const PALETTES: Record<'dark' | 'light', Record<Token, string>> = {
  dark: {
    text: 'ansibrightwhite', // 正文
    dim: 'ansibrightblack', // 次要 / 弱化
    accent: 'ansiyellow', // 强调（标题 / 高亮）
    border: 'ansibrightblack', // 边框 / 分隔线
    error: 'ansired', // 错误
    success: 'ansigreen', // 成功
    warn: 'ansiyellow', // 警告
    info: 'ansicyan', // 信息
    user_bg: 'bg:#2b2b3c', // 用户消息底色
    tool_pending: 'ansiblue', // 工具三态 · 执行中
    tool_ok: 'ansigreen', // 工具三态 · 成功
    tool_fail: 'ansired', // 工具三态 · 失败
    perm_ro: 'ansiblue', // 权限 · 只读
    perm_write: 'ansiyellow', // 权限 · 可写
    perm_full: 'ansired', // 权限 · 全权
    goal_active: 'ansigreen', // 目标 · 进行中
    goal_paused: 'ansiyellow', // 目标 · 暂停
  },
  light: {
    text: 'ansiblack',
    dim: 'ansibrightblack',
    accent: 'ansiblue', // 浅底上比黄色清晰
    border: 'ansibrightblack',
    error: 'ansibrightred', // 浅底上增强对比
    success: 'ansigreen',
    warn: 'ansimagenta', // 浅底上黄字不可读
    info: 'ansiblue',
    user_bg: 'bg:#eef0f6',
    tool_pending: 'ansiblue',
    tool_ok: 'ansigreen',
    tool_fail: 'ansibrightred',
    perm_ro: 'ansiblue',
    perm_write: 'ansimagenta',
    perm_full: 'ansibrightred',
    goal_active: 'ansigreen',
    goal_paused: 'ansimagenta',
  },
};

export type ThemeName = 'dark' | 'light';

/**
 * 检测当前主题。优先级与 `ace_theme.detect_theme()` 逐条一致：
 * ① `ACE_THEME` 显式指定 → ② `COLORFGBG` 推断（背景色号 ≥ 8 视为浅色）→ ③ 默认 dark。
 *
 * 刻意不在 TS 侧自己发明判据：两边对"现在是深色还是浅色"必须给出同一个答案，
 * 否则同一个终端里 Python 画的和 Ink 画的会是两套配色。
 */
export function detectTheme(env: Record<string, string | undefined> = process.env): ThemeName {
  const explicit = (env.ACE_THEME ?? '').trim().toLowerCase();
  if (explicit === 'dark' || explicit === 'light') return explicit;
  const fgbg = (env.COLORFGBG ?? '').trim();
  if (fgbg) {
    const bg = fgbg.split(';').pop()?.trim() ?? '';
    if (/^\d+$/.test(bg)) return Number(bg) >= 8 ? 'light' : 'dark';
  }
  return 'dark';
}

/**
 * 取一个 token 在当前主题下的**前景**色名（喂给 Ink 的 `color`）。
 *
 * 返回的是 chalk 色名（`'yellow'`/`'cyanBright'`…），**不是 hex** ——
 * 让终端用自己的调色板渲染（见 `ANSI_CHALK` 上方那段）。
 * 未知 token、或本身就是底色 token，返回 undefined（= 终端默认色，不抛）。
 */
export function colorFor(token: Token | string, theme: ThemeName): string | undefined {
  const name = (PALETTES[theme] as Record<string, string>)[token];
  if (name === undefined || name.startsWith('bg:')) return undefined;
  return ANSI_CHALK[name];
}

/**
 * 取一个 token 的**背景**色（喂给 Ink 的 `backgroundColor`）。
 *
 * 只有 `bg:#RRGGBB` 那类 token 有值 —— 那些是**故意写死 RGB** 的
 * （用户消息底色不能跟着终端主题变，否则浅色主题上会糊成一片）。
 */
export function bgFor(token: Token | string, theme: ThemeName): string | undefined {
  const name = (PALETTES[theme] as Record<string, string>)[token];
  if (name === undefined || !name.startsWith('bg:')) return undefined;
  return name.slice(3);
}

/** 底色类 token（`bg:#RRGGBB` 那些）真正的用途是背景，不是前景。 */
export function isBackgroundToken(token: Token | string): boolean {
  for (const theme of ['dark', 'light'] as const) {
    const v = (PALETTES[theme] as Record<string, string>)[token];
    if (v !== undefined) return v.startsWith('bg:');
  }
  return false;
}
