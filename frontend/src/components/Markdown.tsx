/**
 * Markdown 渲染 —— 把 `render/markdown.ts` 产出的 Block 树画出来。
 *
 * 两条与 Python 侧对齐的取舍：
 *   1. **代码块不折行**：折了就分不清"这是代码里的换行"还是"终端折的"。
 *      宁可横向溢出由终端处理，也不擅自折。
 *   2. **引用/列表缩进用可见前缀**，不用纯空格 —— 纯空格在窄终端里一折行就归零，
 *      层级感全丢。
 */

import { Box, Text } from 'ink';
import React from 'react';

import { gstr } from '../render/glyphs.js';
import type { Block, Span } from '../render/markdown.js';

export interface MarkdownProps {
  blocks: Block[];
  color: (token: string) => string | undefined;
  /** 流式中：末尾画一个光标，让人知道"它还在说"而不是"卡住了"。 */
  streaming?: boolean;
}

function Spans({ spans, color }: { spans: Span[]; color: MarkdownProps['color'] }): React.ReactElement {
  return (
    <>
      {spans.map((s, i) => {
        if (s.code) {
          return (
            <Text key={i} color={color('info')}>
              {s.text}
            </Text>
          );
        }
        if (s.bold) {
          return (
            <Text key={i} bold color={color('text')}>
              {s.text}
            </Text>
          );
        }
        if (s.italic) {
          return (
            <Text key={i} italic color={color('dim')}>
              {s.text}
            </Text>
          );
        }
        return (
          <Text key={i} color={color('text')}>
            {s.text}
          </Text>
        );
      })}
    </>
  );
}

export function Markdown({ blocks, color, streaming = false }: MarkdownProps): React.ReactElement {
  return (
    <Box flexDirection="column">
      {blocks.map((b, i) => {
        const last = i === blocks.length - 1;
        return (
          <Box key={i} flexDirection="column">
            <BlockView block={b} color={color} cursor={streaming && last} />
          </Box>
        );
      })}
    </Box>
  );
}

function BlockView({
  block,
  color,
  cursor,
}: {
  block: Block;
  color: MarkdownProps['color'];
  cursor: boolean;
}): React.ReactElement {
  switch (block.kind) {
    case 'heading': {
      // h1/h2 加粗并上强调色；h3 以下只加粗 —— 全用强调色会让正文里的重点失去对比。
      const strong = block.level <= 2;
      return (
        <Text bold color={strong ? color('accent') : color('text')}>
          <Spans spans={block.spans} color={color} />
          {cursor ? <Text color={color('dim')}>{gstr('▌')}</Text> : null}
        </Text>
      );
    }

    case 'paragraph':
      return (
        <Text color={color('text')}>
          <Spans spans={block.spans} color={color} />
          {cursor ? <Text color={color('dim')}>{gstr('▌')}</Text> : null}
        </Text>
      );

    case 'list':
      return (
        <Box flexDirection="column">
          {block.items.map((it, i) => (
            <Text key={i} color={color('text')}>
              <Text color={color('dim')}>{block.ordered ? `${i + 1}. ` : '· '}</Text>
              <Spans spans={it} color={color} />
            </Text>
          ))}
        </Box>
      );

    case 'code':
      return (
        <Box flexDirection="column" borderStyle="round" borderColor={color('border')} paddingX={1}>
          {block.lang ? (
            <Text color={color('dim')}>{block.lang}</Text>
          ) : null}
          {block.lines.map((l, i) => (
            // wrap="truncate"：代码不折行（见文件头说明）
            <Text key={i} color={color('text')} wrap="truncate">
              {l || ' '}
            </Text>
          ))}
        </Box>
      );

    case 'quote':
      return (
        <Text color={color('dim')}>
          <Text color={color('border')}>{gstr('▏ ')}</Text>
          <Spans spans={block.spans} color={color} />
        </Text>
      );

    case 'hr':
      return (
        <Text color={color('border')}>{gstr('─'.repeat(20))}</Text>
      );

    default:
      return <Text> </Text>;
  }
}
