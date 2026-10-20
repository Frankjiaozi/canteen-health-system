import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppProviders } from '@/app/providers';
import { AppRouter } from '@/app/router';
import { StartupGate } from '@/features/intro/StartupGate';
import { UpdatePrompt } from '@/shared/components/UpdatePrompt';
import '@/styles/global.css';
import '@/styles/ink-theme.css';

const container = document.getElementById('root');

if (!container) {
  throw new Error('未找到挂载节点 #root');
}

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      {/* 挂在最外层：登录页、管理端与公开大屏都该收到新版本提示 */}
      <UpdatePrompt />
      <StartupGate>
        <AppRouter />
      </StartupGate>
    </AppProviders>
  </StrictMode>,
);
