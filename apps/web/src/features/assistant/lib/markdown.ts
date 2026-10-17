/**
 * 助手回答的最小 Markdown 渲染。

 * 为什么自己做而不引库：模型实际只用四样东西——小标题、加粗、无序列表、表格，
 * 而表格恰恰是它展示营养数据的主要形式（引一个完整 markdown 库要连带处理
 * 链接、图片、HTML，反而多出安全与体积的考虑）。这里只认这四种，认不出来的
 * 一律当普通段落原样显示——**宁可少渲染，不要猜错**。
 */

export interface InlineSegment {
  text: string;
  bold: boolean;
}

export type Block =
  | { kind: 'heading'; level: number; segments: InlineSegment[] }
  | { kind: 'paragraph'; segments: InlineSegment[] }
  | { kind: 'list'; items: InlineSegment[][] }
  | { kind: 'table'; header: string[]; rows: string[][] };

const BULLET = /^\s*[-*]\s+/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const SEPARATOR_CELL = /^:?-{2,}:?$/;

/** 拆 `**加粗**` 与普通文本。不处理转义与嵌套——模型不会那样写，认不出就当普通文本。 */
export function parseInline(text: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  const parts = text.split(/\*\*(.+?)\*\*/g);
  parts.forEach((part, index) => {
    if (part === '') return;
    segments.push({ text: part, bold: index % 2 === 1 });
  });
  return segments.length > 0 ? segments : [{ text, bold: false }];
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map((cell) => cell.trim());
}

function isSeparatorRow(line: string): boolean {
  const cells = splitRow(line);
  return cells.length > 0 && cells.every((cell) => SEPARATOR_CELL.test(cell));
}

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (line.trim() === '') {
      index += 1;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({
        kind: 'heading',
        level: heading[1].length,
        segments: parseInline(heading[2].trim()),
      });
      index += 1;
      continue;
    }

    if (BULLET.test(line)) {
      const items: InlineSegment[][] = [];
      while (index < lines.length && BULLET.test(lines[index])) {
        items.push(parseInline(lines[index].replace(BULLET, '').trim()));
        index += 1;
      }
      blocks.push({ kind: 'list', items });
      continue;
    }

    if (line.trim().startsWith('|')) {
      const raw: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith('|')) {
        raw.push(lines[index]);
        index += 1;
      }
      const body = raw.filter((row) => !isSeparatorRow(row));
      if (body.length >= 2) {
        blocks.push({
          kind: 'table',
          header: splitRow(body[0]),
          rows: body.slice(1).map(splitRow),
        });
      } else {
        // 只有一行或全是分隔线：当成普通段落，别硬做成一张空表
        blocks.push({ kind: 'paragraph', segments: parseInline(raw.join(' ')) });
      }
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() !== '' &&
      !HEADING.test(lines[index]) &&
      !BULLET.test(lines[index]) &&
      !lines[index].trim().startsWith('|')
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ kind: 'paragraph', segments: parseInline(paragraph.join(' ')) });
  }

  return blocks;
}
