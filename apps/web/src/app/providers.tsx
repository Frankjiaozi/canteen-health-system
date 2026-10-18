import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import { useState, type ReactNode } from 'react';

dayjs.locale('zh-cn');

/**
 * 全局 Provider 装配层。
 *
 * 顺序约定：QueryClient（服务端状态） → ConfigProvider（主题与中文语言包） → AntdApp（message/modal 上下文）。
 * 新增全局能力（如权限上下文、离线状态）时在此处插入，不要在页面里各自包一层。
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 30_000,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={zhCN}
        // 关掉「两个汉字的按钮自动插入空格」：界面文案与源码保持一致，
        // 截图、端到端断言、复制出去的文案都不会莫名其妙多一个空格
        button={{ autoInsertSpace: false }}
        theme={{
          components: {
            Menu: {
              itemSelectedBg: '#e7eee5',
              itemSelectedColor: '#244d3b',
              itemHoverBg: '#f1f5ef',
            },
          },
          token: {
            colorPrimary: '#315c4c',
            colorLink: '#315c4c',
            borderRadius: 6,
          },
        }}
      >
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
