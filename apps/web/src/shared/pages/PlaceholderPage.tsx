import { Card, Empty, Typography } from 'antd';

interface PlaceholderPageProps {
  title: string;
  description?: string;
}

/**
 * 尚未实现的模块占位页。
 *
 * 刻意不做成「假数据页面」：界面明确说明功能未实现，
 * 比放一屏看起来能用其实是硬编码的数据要诚实得多。
 */
export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <Card title={title}>
      <Empty
        description={
          <span>
            <Typography.Text type="secondary">该模块尚未实现</Typography.Text>
            {description ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
                {description}
              </Typography.Paragraph>
            ) : null}
          </span>
        }
      />
    </Card>
  );
}
