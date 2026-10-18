import {
  AppstoreOutlined,
  BarChartOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  CoffeeOutlined,
  CommentOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  ExperimentOutlined,
  FormOutlined,
  LogoutOutlined,
  MenuOutlined,
  ScheduleOutlined,
} from '@ant-design/icons';
import {
  App,
  Avatar,
  Button,
  Drawer,
  Grid,
  Layout,
  Menu,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useState, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useCurrentUser, useLogout } from '@/features/auth/hooks/useAuth';
import { usePendingCount, useSyncOfflineQueue } from '@/features/collection/hooks/useOfflineQueue';
import { OfflineNotice } from '@/shared/components/OfflineNotice';
import {
  AGENT_NAV,
  findNavGroupKey,
  HOME_NAV,
  NAV_GROUPS,
  type NavGroup,
} from '@/shared/config/navigation';
import { ApiError } from '@/shared/api/errors';
import './AdminLayout.css';

const { Header, Sider, Content } = Layout;

/** 叶子项的图标。分组另有图标，两者分开写，免得「数据看板」与「基础数据」撞图。 */
const LEAF_ICONS: Record<string, ReactNode> = {
  '/admin': <BarChartOutlined />,
  '/admin/agent': <CommentOutlined />,
  '/admin/ingredients': <DatabaseOutlined />,
  '/admin/dishes': <CoffeeOutlined />,
  '/admin/seasonings': <DatabaseOutlined />,
  '/admin/collection': <FormOutlined />,
  '/admin/calibration': <ExperimentOutlined />,
  '/admin/menu-plan': <BulbOutlined />,
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
  const screens = Grid.useBreakpoint();
  const isMobile = screens.lg === false;
  const [menuOpen, setMenuOpen] = useState(false);
  // 待同步的采集单挂在应用外壳上补交：录入员停在任何管理页都会自动补上
  useSyncOfflineQueue();
  const pendingCount = usePendingCount();

  const menuItems = [
    { key: HOME_NAV.path, icon: LEAF_ICONS[HOME_NAV.path], label: HOME_NAV.title },
    { key: AGENT_NAV.path, icon: LEAF_ICONS[AGENT_NAV.path], label: AGENT_NAV.title },
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

  const navigation = (
    <>
      <div className="zw-admin-brand" aria-label="知味校园智慧膳食平台">
        <strong>知味</strong>
        <small>校园智慧膳食</small>
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
        onClick={({ key }) => {
          setMenuOpen(false);
          if (key !== location.pathname) void navigate(key);
        }}
        style={{ borderInlineEnd: 'none' }}
      />
    </>
  );

  return (
    <Layout className="zw-admin-shell" style={{ minHeight: '100%' }}>
      {isMobile ? (
        <Drawer
          title="知味 · 校园智慧膳食"
          placement="left"
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
        >
          {navigation}
        </Drawer>
      ) : (
        <Sider theme="light">{navigation}</Sider>
      )}

      <Layout>
        <Header
          className="zw-admin-header"
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
          {isMobile && (
            <Button
              className="zw-admin-menu-toggle"
              type="text"
              icon={<MenuOutlined />}
              aria-label="打开导航"
              onClick={() => setMenuOpen(true)}
            />
          )}
          <Typography.Text className="zw-admin-caption" type="secondary">
            营养核算 · 采购预测 · 决策支持
          </Typography.Text>

          {import.meta.env.VITE_DEMO_MODE === 'true' && (
            <Tag className="zw-admin-demo-badge" color="gold">
              独立演示 · 合成数据
            </Tag>
          )}

          <Space className="zw-admin-actions" size={12} wrap>
            <Tooltip title="免登录打开的食堂公开大屏">
              <Button
                className="zw-admin-display-button"
                aria-label="公开大屏"
                icon={<DesktopOutlined />}
                onClick={() => window.open('/display', '_blank', 'noopener')}
              >
                <span className="zw-admin-display-label">公开大屏</span>
              </Button>
            </Tooltip>
            {user ? (
              <Space className="zw-admin-user" size={8}>
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

        <Content className="zw-admin-content">
          <OfflineNotice pendingCount={pendingCount} />
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
