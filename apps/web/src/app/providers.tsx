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
  const [reduceMotion] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );
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
          token: {
            motion: !reduceMotion,
            colorPrimary: '#607c5c',
            colorLink: '#506c4e',
            colorSuccess: '#3d7a58',
            colorWarning: '#b07b32',
            colorError: '#ad4f3e',
            colorText: '#273a31',
            colorTextSecondary: '#5f7166',
            colorTextTertiary: '#647268',
            colorBorder: '#ddd9cc',
            colorBorderSecondary: '#ece8dc',
            colorBgLayout: '#f5eedf',
            colorBgContainer: '#fffcf6',
            colorBgElevated: '#fffcf8',
            fontFamily:
              '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", sans-serif',
            fontSize: 14,
            borderRadius: 12,
            borderRadiusLG: 20,
            controlHeight: 38,
            boxShadow: '0 1px 2px rgba(34, 49, 42, 0.04)',
            boxShadowSecondary: '0 18px 48px rgba(34, 49, 42, 0.12)',
          },
          components: {
            Layout: {
              siderBg: '#f1eee5',
              headerBg: 'rgba(246, 244, 237, 0.92)',
              bodyBg: '#f6f4ed',
            },
            Menu: {
              itemBg: 'transparent',
              subMenuItemBg: 'transparent',
              itemColor: '#485d51',
              itemHoverBg: 'rgba(47, 90, 72, 0.07)',
              itemSelectedBg: '#dde4d1',
              itemSelectedColor: '#354c38',
              itemHeight: 40,
              itemBorderRadius: 12,
              itemMarginInline: 12,
              itemMarginBlock: 2,
              groupTitleColor: '#8b9183',
              groupTitleFontSize: 11,
              iconSize: 15,
            },
            Button: {
              fontWeight: 500,
              primaryShadow: 'none',
              defaultShadow: 'none',
              dangerShadow: 'none',
              defaultBorderColor: '#ddd9cc',
              defaultColor: '#3f5348',
            },
            Card: {
              headerBg: 'transparent',
              headerFontSize: 15,
              headerHeight: 52,
              bodyPadding: 22,
              headerPadding: 22,
            },
            Table: {
              headerBg: '#f5f2e9',
              headerColor: '#68776c',
              headerSplitColor: 'transparent',
              rowHoverBg: '#faf8f1',
              borderColor: '#efebe0',
              cellPaddingBlockSM: 11,
              cellPaddingInlineSM: 16,
            },
            Segmented: {
              trackBg: '#f0eee5',
              itemColor: '#6d7a70',
              itemHoverColor: '#2f5a48',
              itemSelectedBg: '#dde4d1',
              itemSelectedColor: '#354c38',
              trackPadding: 3,
            },
            Tabs: {
              itemColor: '#6d7a70',
              itemHoverColor: '#2f5a48',
              itemSelectedColor: '#22312a',
              inkBarColor: '#2f5a48',
              titleFontSize: 14,
            },
            Input: {
              activeBorderColor: '#5d876f',
              hoverBorderColor: '#a9b8ab',
              activeShadow: '0 0 0 3px rgba(47, 90, 72, 0.1)',
              paddingInline: 12,
            },
            Select: {
              activeBorderColor: '#5d876f',
              hoverBorderColor: '#a9b8ab',
              activeOutlineColor: 'rgba(47, 90, 72, 0.1)',
            },
            Statistic: {
              titleFontSize: 12,
              contentFontSize: 30,
            },
            Tag: {
              defaultBg: '#f0ede3',
              defaultColor: '#5f7166',
            },
            Drawer: {
              footerPaddingBlock: 16,
              footerPaddingInline: 22,
            },
          },
        }}
      >
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
