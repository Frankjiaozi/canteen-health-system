import { Card, Table, Tag, Typography } from 'antd';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { SYSTEM_MODULES } from '@/shared/config/modules';

export function AdminHomePage() {
  const { data: user } = useCurrentUser();

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card>
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          {user ? `${user.display_name}，欢迎回来` : '欢迎'}
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          系统把食堂每天的采购与投料数据，变成每道菜的营养数据和第二天的采购与菜单决策，
          并把学生餐的营养构成公示在食堂的公开大屏上。
        </Typography.Paragraph>
      </Card>

      <Card title="模块进度">
        <Table
          rowKey="path"
          size="small"
          pagination={false}
          dataSource={SYSTEM_MODULES}
          columns={[
            { title: '模块', dataIndex: 'title', width: 140 },
            { title: '说明', dataIndex: 'description' },
            {
              title: '登录',
              dataIndex: 'requiresAuth',
              width: 90,
              render: (requiresAuth: boolean) =>
                requiresAuth ? <Tag>需登录</Tag> : <Tag color="green">免登录</Tag>,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 110,
              render: (status: string) =>
                status === 'ready' ? (
                  <Tag color="success">已可用</Tag>
                ) : (
                  <Tag color="default">建设中</Tag>
                ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
