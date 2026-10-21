import type { ReactNode } from 'react';
import '../pages/auth.css';

/** 登录与注册共用的单栏表单布局。 */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="zw-login zw-login-panel">
      <div className="zw-login-form-wrap">{children}</div>
    </main>
  );
}
