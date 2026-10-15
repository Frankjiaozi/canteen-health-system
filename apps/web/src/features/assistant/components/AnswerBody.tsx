import { Table, Typography } from 'antd';
import { parseBlocks, type InlineSegment } from '../lib/markdown';

const { Paragraph, Text, Title } = Typography;

function Inline({ segments }: { segments: InlineSegment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.bold ? (
          <Text key={index} strong>
            {segment.text}
          </Text>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/**
 * 助手回答的渲染：小标题、加粗、列表、表格，其余原样显示。

 * 表格用 antd 的 Table 而不是塞进一段文字：营养数据本来就该按列对齐看。
 */
export function AnswerBody({ text }: { text: string }) {
  const blocks = parseBlocks(text);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {blocks.map((block, index) => {
        if (block.kind === 'heading') {
          return (
            <Title key={index} level={5} style={{ margin: 0 }}>
              <Inline segments={block.segments} />
            </Title>
          );
        }
        if (block.kind === 'list') {
          return (
            <ul key={index} style={{ margin: 0, paddingInlineStart: 20 }}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <Inline segments={item} />
                </li>
              ))}
            </ul>
          );
        }
        if (block.kind === 'table') {
          return (
            <Table
              key={index}
              size="small"
              pagination={false}
              scroll={{ x: true }}
              rowKey={(_, rowIndex) => String(rowIndex)}
              dataSource={block.rows.map((cells) => ({ cells }))}
              columns={block.header.map((title, columnIndex) => ({
                title,
                dataIndex: ['cells', columnIndex],
                ellipsis: true,
              }))}
            />
          );
        }
        return (
          <Paragraph key={index} style={{ margin: 0 }}>
            <Inline segments={block.segments} />
          </Paragraph>
        );
      })}
    </div>
  );
}
