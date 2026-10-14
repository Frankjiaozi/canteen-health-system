import {
  BarChartOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  CoffeeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FormOutlined,
  LineChartOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { App, Avatar, Button, Layout, Menu, Space, Tag, Tooltip, Typography } from 'antd';
import type { ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useCurrentUser, useLogout } from '@/features/auth/hooks/useAuth';
import { OfflineNotice } from '@/shared/components/OfflineNotice';
import { SYSTEM_MODULES } from '@/shared/config/modules';
import { ApiError } from '@/shared/api/errors';

const { Header, Sider, Content } = Layout;

const MODULE_ICONS: Record<string, ReactNode> = {
  '/admin': <DashboardOutlined />,
  '/admin/ingredients': <DatabaseOutlined />,
  '/admin/dishes': <CoffeeOutlined />,
  '/admin/collection': <FormOutlined />,
  '/admin/dashboard': <BarChartOutlined />,
  '/admin/forecast': <LineChartOutlined />,
  '/admin/recommendation': <BulbOutlined />,
};

export function AdminLayout() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: user } = useCurrentUser();
  const logoutMutation = useLogout();

  const menuItems = SYSTEM_MODULES.filter((module) => module.requiresAuth).map((module) => ({
    key: module.path,
    icon: MODULE_ICONS[module.path],
    label: module.title,
  }));

  const handleLogout = async () => {
    try {
      await logoutMutation.mutateAsync();
      void navigate('/login', { replace: true });
    } catch (error) {
      void message.error(error instanceof ApiError ? error.message : '退出失败，请稍后重试');
    }
  };

  return (
    <Layout style={{ minHeight: '100%' }}>
      <Sider breakpoint="lg" collapsedWidth={0} theme="light">
        <div style={{ padding: '20px 16px 12px' }}>
          <Typography.Text strong>知味 · 校园智慧膳食平台</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => void navigate(key)}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: '#fff',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            paddingInline: 16,
          }}
        >
          <Typography.Text type="secondary">营养核算 · 采购预测 · 决策支持</Typography.Text>

          <Space size={12} wrap>
            <Tooltip title="免登录打开的食堂公开大屏">
              <Button
                icon={<DesktopOutlined />}
                onClick={() => window.open('/display', '_blank', 'noopener')}
              >
                公开大屏
              </Button>
            </Tooltip>
            {user ? (
              <Space size={8}>
                <Avatar size="small">{user.display_name.slice(0, 1)}</Avatar>
                <Typography.Text>{user.display_name}</Typography.Text>
                <Tag color="blue">{user.role_label}</Tag>
              </Space>
            ) : (
              <Tag icon={<ClockCircleOutlined />}>加载中</Tag>
            )}
            <Button
              icon={<LogoutOutlined />}
              loading={logoutMutation.isPending}
              onClick={() => void handleLogout()}
            >
              退出
            </Button>
          </Space>
        </Header>

        <Content style={{ padding: 16 }}>
          <OfflineNotice />
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
