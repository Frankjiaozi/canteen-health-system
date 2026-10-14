import {
  AppstoreOutlined,
  BarChartOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  CoffeeOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  ExperimentOutlined,
  FormOutlined,
  LineChartOutlined,
  LogoutOutlined,
  ScheduleOutlined,
} from '@ant-design/icons';
import { App, Avatar, Button, Layout, Menu, Space, Tag, Tooltip, Typography } from 'antd';
import type { ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useCurrentUser, useLogout } from '@/features/auth/hooks/useAuth';
import { usePendingCount, useSyncOfflineQueue } from '@/features/collection/hooks/useOfflineQueue';
import { OfflineNotice } from '@/shared/components/OfflineNotice';
import { findNavGroupKey, HOME_NAV, NAV_GROUPS, type NavGroup } from '@/shared/config/navigation';
import { ApiError } from '@/shared/api/errors';

const { Header, Sider, Content } = Layout;

/** 叶子项的图标。分组另有图标，两者分开写，免得「数据看板」与「基础数据」撞图。 */
const LEAF_ICONS: Record<string, ReactNode> = {
  '/admin': <BarChartOutlined />,
  '/admin/ingredients': <DatabaseOutlined />,
  '/admin/dishes': <CoffeeOutlined />,
  '/admin/seasonings': <DatabaseOutlined />,
  '/admin/collection': <FormOutlined />,
  '/admin/calibration': <ExperimentOutlined />,
  '/admin/forecast': <LineChartOutlined />,
  '/admin/recommendation': <BulbOutlined />,
};

const GROUP_ICONS: Record<string, ReactNode> = {
  basics: <AppstoreOutlined />,
  routine: <ScheduleOutlined />,
};

function toMenuItem(group: NavGroup) {
  return {
    key: group.key,
    icon: GROUP_ICONS[group.key],
    label: group.title,
    children: group.children.map((leaf) => ({
      key: leaf.path,
      icon: LEAF_ICONS[leaf.path],
      label: leaf.title,
    })),
  };
}

export function AdminLayout() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: user } = useCurrentUser();
  const logoutMutation = useLogout();
  const activeGroup = findNavGroupKey(location.pathname);
  // 待同步的采集单挂在应用外壳上补交：录入员停在任何管理页都会自动补上
  useSyncOfflineQueue();
  const pendingCount = usePendingCount();

  const menuItems = [
    { key: HOME_NAV.path, icon: LEAF_ICONS[HOME_NAV.path], label: HOME_NAV.title },
    ...NAV_GROUPS.map(toMenuItem),
  ];

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
          // 换页面时重建菜单，让 defaultOpenKeys 按当前页重算一次。
          // 比在 effect 里同步状态干净：也省掉「用户点开另一组又跳走」这类边界
          key={location.pathname}
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          // 只展开当前页所在的分组：一进来把两组都摊开，跟没分组差不了多少
          defaultOpenKeys={activeGroup === null ? [] : [activeGroup]}
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
          <OfflineNotice pendingCount={pendingCount} />
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
