import { useCallback, useState, type ReactNode } from 'react';
import { IntroPreviewPage } from './IntroPreviewPage';

/** 应用启动时播放一次；路由始终留在原地址，表单与登录回跳不受影响。 */
export function StartupGate({ children }: { children: ReactNode }) {
  const [entered, setEntered] = useState(
    () =>
      // 公开大屏与预览页本就不该有进场；
      // 另外，系统设置里开了「减弱动态效果」的人直接进业务——进场动画是品牌表达，
      // 不该挡在一个明确表达了「不要动效」的用户前面，也不该让自动化测试等它播完。
      ['/intro-preview', '/display'].includes(window.location.pathname) ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true,
  );
  const finish = useCallback(() => setEntered(true), []);

  return (
    <>
      <div className="ink-app-content" aria-hidden={!entered || undefined} inert={!entered}>
        {children}
      </div>
      {!entered && (
        <div className="ink-startup-overlay">
          <IntroPreviewPage onComplete={finish} />
        </div>
      )}
    </>
  );
}
