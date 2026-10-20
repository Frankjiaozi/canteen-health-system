import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input } from 'antd';
import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@/shared/api/errors';
import { AuthShell } from '../components/AuthShell';
import { useCurrentUser, useLogin } from '../hooks/useAuth';
import type { LoginPayload } from '../types';

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: currentUser } = useCurrentUser();
  const loginMutation = useLogin();
  const [errorText, setErrorText] = useState<string | null>(null);

  const from =
    (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/admin';

  // 已登录用户直接放行，避免重复登录
  if (currentUser) {
    return <Navigate to={from} replace />;
  }

  const handleFinish = async (values: LoginPayload) => {
    setErrorText(null);
    try {
      await loginMutation.mutateAsync(values);
      void navigate(from, { replace: true });
    } catch (error) {
      setErrorText(error instanceof ApiError ? error.message : '登录失败，请稍后重试');
    }
  };

  return (
    <AuthShell>
      <span className="zw-kicker">膳食运营工作台</span>
      <h2>欢迎回来</h2>
      <p className="zw-login-lead">登录后继续今天的菜单、采集与核算。</p>

      <Form<LoginPayload> layout="vertical" onFinish={handleFinish} requiredMark={false}>
        <Form.Item
          name="username"
          label="登录名"
          rules={[{ required: true, message: '请输入登录名' }]}
        >
          <Input
            prefix={<UserOutlined />}
            placeholder="请输入登录名"
            autoComplete="username"
            size="large"
          />
        </Form.Item>
        <Form.Item name="password" label="口令" rules={[{ required: true, message: '请输入口令' }]}>
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="请输入口令"
            autoComplete="current-password"
            size="large"
          />
        </Form.Item>

        {errorText ? (
          <Alert title={errorText} type="error" showIcon style={{ marginBottom: 16 }} />
        ) : null}

        <Button
          className="zw-login-submit"
          type="primary"
          htmlType="submit"
          block
          size="large"
          loading={loginMutation.isPending}
        >
          登录
        </Button>
      </Form>

      <p className="zw-login-register">
        还没有账号？
        <Link to="/register" state={location.state}>
          立即注册
        </Link>
      </p>

      {import.meta.env.DEV ? (
        <p className="zw-login-demo">演示账号：recorder / canteen / school，口令 canteen@2026</p>
      ) : null}
    </AuthShell>
  );
}
