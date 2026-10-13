import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@/shared/api/errors';
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
    <div
      style={{
        minHeight: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <Card style={{ width: '100%', maxWidth: 400 }}>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          食堂健康管理系统
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 24 }}>
          营养核算 · 采购预测 · 决策支持
        </Typography.Paragraph>

        <Form<LoginPayload> layout="vertical" onFinish={handleFinish} requiredMark={false}>
          <Form.Item
            name="username"
            label="登录名"
            rules={[{ required: true, message: '请输入登录名' }]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item
            name="password"
            label="口令"
            rules={[{ required: true, message: '请输入口令' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              autoComplete="current-password"
              size="large"
            />
          </Form.Item>

          {errorText ? (
            <Typography.Paragraph type="danger" style={{ marginBottom: 12 }}>
              {errorText}
            </Typography.Paragraph>
          ) : null}

          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loginMutation.isPending}
          >
            登录
          </Button>
        </Form>

        {import.meta.env.DEV ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: 20, marginBottom: 0 }}>
            演示账号：recorder / canteen / school，口令 canteen@2026
          </Typography.Paragraph>
        ) : null}
      </Card>
    </div>
  );
}
