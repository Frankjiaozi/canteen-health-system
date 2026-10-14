import { IdcardOutlined, LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@/shared/api/errors';
import { useCurrentUser, useRegister } from '../hooks/useAuth';
import type { RegisterPayload } from '../types';

type RegisterForm = RegisterPayload & { confirm_password: string };

export function RegisterPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: currentUser } = useCurrentUser();
  const registerMutation = useRegister();
  const [errorText, setErrorText] = useState<string | null>(null);
  const from =
    (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/admin';

  if (currentUser) return <Navigate to={from} replace />;

  const handleFinish = async (values: RegisterForm) => {
    setErrorText(null);
    try {
      await registerMutation.mutateAsync({
        username: values.username.trim().toLowerCase(),
        display_name: values.display_name.trim(),
        password: values.password,
      });
      void navigate(from, { replace: true });
    } catch (error) {
      setErrorText(error instanceof ApiError ? error.message : '注册失败，请稍后重试');
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
      <Card style={{ width: '100%', maxWidth: 440 }}>
        <Typography.Text type="secondary">知味 · 校园智慧膳食平台</Typography.Text>
        <Typography.Title level={3} style={{ marginTop: 8, marginBottom: 8 }}>
          创建账号
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 24 }}>
          注册成为食堂录入员，维护食材并记录每日供餐数据。
        </Typography.Paragraph>
        <Form<RegisterForm> layout="vertical" onFinish={handleFinish} requiredMark={false}>
          <Form.Item
            name="display_name"
            label="显示名称"
            rules={[
              { required: true, whitespace: true, message: '请输入显示名称' },
              { max: 64, message: '显示名称不能超过 64 个字符' },
              { pattern: /^[^\p{C}]+$/u, message: '显示名称不能包含控制字符' },
            ]}
          >
            <Input
              prefix={<IdcardOutlined />}
              placeholder="请输入姓名或昵称"
              autoComplete="nickname"
              size="large"
              maxLength={64}
            />
          </Form.Item>
          <Form.Item
            name="username"
            label="登录名"
            extra="3–32 位字母、数字或下划线，不区分大小写"
            rules={[
              { required: true, message: '请输入登录名' },
              {
                pattern: /^[a-zA-Z0-9_]{3,32}$/,
                transform: (value: string) => value?.trim(),
                message: '请使用 3–32 位字母、数字或下划线',
              },
            ]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" size="large" maxLength={32} />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            extra="至少 8 个字符，包含字母和数字"
            rules={[
              { required: true, message: '请输入密码' },
              {
                validator: (_, value?: string) => {
                  if (!value) return Promise.resolve();
                  if (
                    Array.from(value).length < 8 ||
                    !/\p{L}/u.test(value) ||
                    !/\p{N}/u.test(value)
                  ) {
                    return Promise.reject(new Error('密码至少 8 个字符，并同时包含字母和数字'));
                  }
                  if (new TextEncoder().encode(value).length > 72) {
                    return Promise.reject(new Error('密码过长，请缩短后重试'));
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} autoComplete="new-password" size="large" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator: (_, value?: string) => {
                  if (!value || getFieldValue('password') === value) return Promise.resolve();
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} autoComplete="new-password" size="large" />
          </Form.Item>
          {errorText ? (
            <Alert title={errorText} type="error" showIcon style={{ marginBottom: 16 }} />
          ) : null}
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={registerMutation.isPending}
          >
            注册并登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 20, marginBottom: 0, textAlign: 'center' }}>
          已有账号？{' '}
          <Link to="/login" state={location.state}>
            返回登录
          </Link>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
