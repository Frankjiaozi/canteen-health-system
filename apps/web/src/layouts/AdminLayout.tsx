import { AccountProfile, UserAvatar } from '@/features/auth/components/AccountProfile';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import {
  AppstoreOutlined,
  BarChartOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  CoffeeOutlined,
  CommentOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FormOutlined,
  LogoutOutlined,
  MenuOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useIsMutating, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Grid, Layout, Menu, Space, Tag, Tooltip } from 'antd';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AgentHeaderTitle } from '@/features/agent/components/AgentHeaderTitle';
import { AdminPageHeading } from '@/layouts/AdminPageHeading';
import { useCurrentUser, useLogout } from '@/features/auth/hooks/useAuth';
import { usePendingCount, useSyncOfflineQueue } from '@/features/collection/hooks/useOfflineQueue';
import { OfflineNotice } from '@/shared/components/OfflineNotice';
import { AGENT_NAV, findNavLeaf, HOME_NAV } from '@/shared/config/navigation';
import { ApiError } from '@/shared/api/errors';
import { BrandMark } from '@/shared/components/BrandMark';
import FadeContent from '@/shared/components/react-bits/FadeContent';
import './AdminLayout.css';
import './sidebar.css';

const { Header, Sider, Content } = Layout;

const MORE_PATHS = ['/admin/seasonings', '/admin/calibration'];

export function AdminLayout() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const busy = useIsMutating() > 0;
  const navigate = useNavigate();
  const location = useLocation();
  const { data: user } = useCurrentUser();
  const logoutMutation = useLogout();
  const isAgent = location.pathname === AGENT_NAV.path;
  const isHome = location.pathname === HOME_NAV.path;
  const navLeaf = findNavLeaf(location.pathname);
  const screens = Grid.useBreakpoint();
  const isMobile = screens.lg === false;
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const openProfile = () => {
    setMenuOpen(false);
    setProfileOpen(true);
  };
  // 待同步的采集单挂在应用外壳上补交：录入员停在任何管理页都会自动补上
  useSyncOfflineQueue();
  const pendingCount = usePendingCount();

  const [menuState, setMenuState] = useState(() => ({
    pathname: location.pathname,
    openKeys: MORE_PATHS.includes(location.pathname) ? ['more'] : [],
  }));
  // 切到子项（包括浏览器后退）时展开所在组；其余时候保留用户的展开/折叠选择。
  if (menuState.pathname !== location.pathname) {
    setMenuState({
      pathname: location.pathname,
      openKeys: MORE_PATHS.includes(location.pathname)
        ? Array.from(new Set([...menuState.openKeys, 'more']))
        : menuState.openKeys,
    });
  }

  const handleLogout = async () => {
    try {
      await logoutMutation.mutateAsync();
      void navigate('/login', { replace: true });
    } catch (error) {
      void message.error(error instanceof ApiError ? error.message : '退出失败，请稍后重试');
    }
  };

  const navigation = (
    <div className="zw-admin-nav zw-sidebar">
      <div className="zw-admin-brand" aria-label="知味校园智慧膳食平台">
        <BrandMark />
        <p className="zw-reference-motto">
          让每一餐更有滋味
          <br />
          也更有营养
        </p>
      </div>
      <Menu
        className="zw-admin-menu"
        mode="inline"
        selectedKeys={[location.pathname]}
        items={[
          { key: '/admin', icon: <BarChartOutlined />, label: '总览' },
          { key: '/admin/agent', icon: <CommentOutlined />, label: '膳食助手' },
          { key: '/admin/dishes', icon: <CoffeeOutlined />, label: '菜品与配方' },
          { key: '/admin/ingredients', icon: <DatabaseOutlined />, label: '食材库' },
          { key: '/admin/menu-plan', icon: <BulbOutlined />, label: '菜单与采购' },
          {
            key: '/admin/collection',
            icon: <FormOutlined />,
            label: canWriteBusinessData(user) ? '每日采集' : '供餐记录',
          },
          {
            key: 'more',
            icon: <AppstoreOutlined />,
            label: '更多工具',
            children: [
              { key: '/admin/seasonings', label: '调味料库' },
              { key: '/admin/calibration', label: '抽样纠偏' },
            ],
          },
        ]}
        openKeys={menuState.openKeys}
        onOpenChange={(openKeys) => setMenuState({ pathname: location.pathname, openKeys })}
        onClick={({ key }) => {
          setMenuOpen(false);
          if (key !== location.pathname) void navigate(key);
        }}
        style={{ borderInlineEnd: 'none' }}
      />
      {user && (
        <button
          type="button"
          className="zw-account-entry"
          aria-label="查看我的账号"
          onClick={openProfile}
        >
          <UserAvatar user={user} />
          <span>
            <strong title={user.display_name}>{user.display_name}</strong>
            <small>
              {user.role_label} · {canWriteBusinessData(user) ? '可维护' : '只读'}
            </small>
          </span>
        </button>
      )}
      <svg className="zw-reference-landscape" viewBox="0 610 185 300" aria-hidden="true">
        <image href="/design/ink-reference.png" width="1586" height="992" />
      </svg>
    </div>
  );

  return (
    <Layout className={`zw-admin-shell${isHome ? ' zw-reference-shell' : ''}`}>
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
        <Sider className="zw-admin-sider" theme="light" width={178}>
          {navigation}
        </Sider>
      )}

      {user && (
        <AccountProfile
          user={user}
          open={profileOpen}
          onClose={() => setProfileOpen(false)}
          onLogout={() => void handleLogout()}
          loggingOut={logoutMutation.isPending}
        />
      )}
      <Layout>
        <Header className="zw-admin-header">
          {isHome && (
            <svg className="zw-reference-top-art" viewBox="1380 0 206 40" aria-hidden="true">
              <image href="/design/ink-reference.png" width="1586" height="992" />
            </svg>
          )}
          {isMobile && (
            <Button
              className="zw-admin-menu-toggle"
              type="text"
              icon={<MenuOutlined />}
              aria-label="打开导航"
              onClick={() => setMenuOpen(true)}
            />
          )}
          {isHome ? (
            <AdminPageHeading
              title="今日膳食概览"
              tagline={new Date().toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                weekday: 'long',
              })}
            />
          ) : isAgent ? (
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
                <button
                  className="zw-account-heading-button"
                  onClick={openProfile}
                  aria-label="查看我的账号"
                >
                  <UserAvatar user={user} size={30} />
                </button>
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
          <OfflineNotice pendingCount={canWriteBusinessData(user) ? pendingCount : 0} />
          {user && !canWriteBusinessData(user) && (
            <div className="zw-role-notice">
              {user.role_label} · 只读查看，修改与发布操作由录入员或食堂管理员完成。
            </div>
          )}
          <FadeContent
            key={location.pathname}
            trigger="mount"
            duration={0.42}
            initialOpacity={0.35}
          >
            <Outlet />
          </FadeContent>
        </Content>
      </Layout>
    </Layout>
  );
}
