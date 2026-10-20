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
  ReloadOutlined,
  ScheduleOutlined,
} from '@ant-design/icons';
import { useIsMutating, useQueryClient } from '@tanstack/react-query';
import { App, Avatar, Button, Drawer, Grid, Layout, Menu, Space, Tag, Tooltip } from 'antd';
import { useState, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AgentHeaderTitle } from '@/features/agent/components/AgentHeaderTitle';
import { AdminPageHeading } from '@/layouts/AdminPageHeading';
import { useCurrentUser, useLogout } from '@/features/auth/hooks/useAuth';
import { usePendingCount, useSyncOfflineQueue } from '@/features/collection/hooks/useOfflineQueue';
import { OfflineNotice } from '@/shared/components/OfflineNotice';
import {
  AGENT_NAV,
  findNavLeaf,
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
  const queryClient = useQueryClient();
  const busy = useIsMutating() > 0;
  const navigate = useNavigate();
  const location = useLocation();
  const { data: user } = useCurrentUser();
  const logoutMutation = useLogout();
  const isAgent = location.pathname === AGENT_NAV.path;
  const navLeaf = findNavLeaf(location.pathname);
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
    <div className="zw-admin-nav">
      <div className="zw-admin-brand" aria-label="知味校园智慧膳食平台">
        <span className="zw-admin-brand-seal" aria-hidden="true">
          味
        </span>
        <div className="zw-admin-brand-copy">
          <strong>知味</strong>
          <small>校园智慧膳食平台</small>
        </div>
      </div>
      <Menu
        className="zw-admin-menu"
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        // 业务入口只有 6 个，默认全展开：分组的标题仍能建立层级，
        // 但不用让用户在首页多点一次才能找到模块
        defaultOpenKeys={NAV_GROUPS.map((group) => group.key)}
        onClick={({ key }) => {
          setMenuOpen(false);
          if (key !== location.pathname) void navigate(key);
        }}
        style={{ borderInlineEnd: 'none' }}
      />
      <div className="zw-admin-nav-foot" aria-hidden="true">
        <span>一餐一饭</span>
        <span>知味知营养</span>
      </div>
    </div>
  );

  return (
    <Layout className="zw-admin-shell">
      {isMobile ? (
        <Drawer
          title="知味 · 校园智慧膳食"
          placement="left"
          width={276}
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
        >
          {navigation}
        </Drawer>
      ) : (
        <Sider className="zw-admin-sider" theme="light" width={252}>
          {navigation}
        </Sider>
      )}

      <Layout>
        <Header className="zw-admin-header">
          {isMobile && (
            <Button
              className="zw-admin-menu-toggle"
              type="text"
              icon={<MenuOutlined />}
              aria-label="打开导航"
              onClick={() => setMenuOpen(true)}
            />
          )}
          {isAgent ? (
            <AgentHeaderTitle />
          ) : (
            <AdminPageHeading
              title={navLeaf?.title ?? HOME_NAV.title}
              tagline={navLeaf?.description}
            />
          )}

          {import.meta.env.VITE_DEMO_MODE === 'true' && (
            <Tag className="zw-admin-demo-badge" color="gold">
              独立演示 · 合成数据
            </Tag>
          )}

          <Space className="zw-admin-actions" size={10} wrap>
            {isAgent && (
              <Tooltip title="刷新结果">
                <Button
                  aria-label="刷新结果"
                  icon={<ReloadOutlined />}
                  disabled={busy}
                  onClick={() => void queryClient.invalidateQueries({ queryKey: ['agent'] })}
                />
              </Tooltip>
            )}
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
                <span className="zw-admin-user-copy">
                  <strong>{user.display_name}</strong>
                  <small>{user.role_label}</small>
                </span>
              </Space>
            ) : (
              <Tag icon={<ClockCircleOutlined />}>加载中</Tag>
            )}
            <Tooltip title="退出登录">
              <Button
                className="zw-admin-logout"
                aria-label="退出"
                icon={<LogoutOutlined />}
                loading={logoutMutation.isPending}
                onClick={() => void handleLogout()}
              >
                <span className="zw-admin-logout-label">退出</span>
              </Button>
            </Tooltip>
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
