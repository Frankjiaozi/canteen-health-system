import { describe, expect, it } from 'vitest';
import { parseBlocks, parseInline } from './markdown';

describe('加粗拆分', () => {
  it('把 **加粗** 与普通文本分开', () => {
    expect(parseInline('结论：**盐超标**，注意。')).toEqual([
      { text: '结论：', bold: false },
      { text: '盐超标', bold: true },
      { text: '，注意。', bold: false },
    ]);
  });

  it('没有加粗时整段原样返回', () => {
    expect(parseInline('就是一句话')).toEqual([{ text: '就是一句话', bold: false }]);
  });
});

describe('块解析', () => {
  it('小标题、加粗段落与列表各归各的', () => {
    const blocks = parseBlocks(
      ['## 结论', '', '**盐**合格。', '', '- 食盐 2.2 克', '- 烹调油 7.4 克'].join('\n'),
    );

    expect(blocks.map((block) => block.kind)).toEqual(['heading', 'paragraph', 'list']);
    expect(blocks[0]).toMatchObject({ kind: 'heading', level: 2, segments: [{ text: '结论' }] });
    expect(blocks[2]).toMatchObject({ kind: 'list' });
    if (blocks[2].kind === 'list') {
      expect(blocks[2].items).toHaveLength(2);
      expect(blocks[2].items[1][0].text).toBe('烹调油 7.4 克');
    }
  });

  it('表格要吃掉分隔行，只留表头与数据', () => {
    const blocks = parseBlocks(
      ['| 指标 | 人均 | 标准 |', '|---|---|---|', '| 食盐 | 2.20 | ≤5 |'].join('\n'),
    );

    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({
      kind: 'table',
      header: ['指标', '人均', '标准'],
      rows: [['食盐', '2.20', '≤5']],
    });
  });

  it('只有一行表格时不当成表格——别硬做出一张空表', () => {
    const blocks = parseBlocks('| 只有一行 |');

    expect(blocks[0].kind).toBe('paragraph');
  });

  it('换行不丢：一行行的普通文字合成一段，段间空行才断开', () => {
    const blocks = parseBlocks('第一行\n第二行\n\n新的一段');

    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toMatchObject({ kind: 'paragraph' });
    if (blocks[0].kind === 'paragraph') {
      expect(blocks[0].segments[0].text).toBe('第一行 第二行');
    }
  });

  it('认不出来的东西原样显示，不猜', () => {
    const blocks = parseBlocks('```json\n{"a": 1}\n```');

    expect(blocks.every((block) => block.kind === 'paragraph')).toBe(true);
  });
});
