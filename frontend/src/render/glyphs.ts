/**
 * 字形降级 —— 控制台画不出来的字符换成 ASCII 替身。
 *
 * ## 为什么必须有这一层（实机可见）
 *
 * 中文 Windows 控制台的代码页是 **936（GBK）**，下面这些字**印不出来**：
 * `❯`（提示符）`✓` `✗`（工具三态）`◐◓◑◒`（spinner）`▶`（任务树）`⚠` …
 * 不降级的话，屏幕上那些位置是**乱码或方框** —— 用户看到的就是"界面坏了"，
 * 而且不会有任何报错。
 *
 * Python 侧一直有这套（`core/ace_io.glyph()` + `ASCII_FALLBACK`），**前端漏接了**。
 *
 * ## 为什么表由引擎给，而不是前端自己算
 *
 * 前端是 Node，**判断不了"cp936 能不能编码这个字"** —— Node 只内建 utf8/latin1
 * 编码器，没有任意 legacy 编码的 encoder。只有引擎那边（`ace_io`）知道
 * 当前控制台编码、并且有那张人工维护的替身表。
 *
 * 所以：`initialize` 时引擎把 `{原字: 替身}` 发过来，这里存着，组件用 `g()` 取。
 * 表为空 = 这台终端画得出全部（UTF-8 终端就是这样）。
 */

let SUBS: Record<string, string> = {};

/** 由 `index.tsx` 在握手后调一次。传 undefined / 空表 = 不降级。 */
export function setGlyphs(map: Record<string, string> | undefined | null): void {
  SUBS = map && typeof map === 'object' ? { ...map } : {};
}

/** 取该显示的字形：这台终端画得出就原样，画不出就换替身。 */
export function g(ch: string): string {
  return SUBS[ch] ?? ch;
}

/**
 * 整串过一遍替换。
 *
 * 多数地方（任务树的连接线、logo 的块状字符、Markdown 的引用线）一行里混着好几个字形，
 * 逐个 `g()` 太碎；在**渲染点**整串过一次更省事，也不容易漏。
 * 表为空时是恒等函数，开销可忽略。
 */
export function gstr(s: string): string {
  if (!s || Object.keys(SUBS).length === 0) return s;
  let out = '';
  for (const ch of s) out += SUBS[ch] ?? ch;
  return out;
}

/** 给测试用：当前生效的替身表。 */
export function glyphMap(): Record<string, string> {
  return { ...SUBS };
}
