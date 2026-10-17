import { useCallback, useState, type ReactNode } from 'react';
import { IntroPreviewPage } from './IntroPreviewPage';

/** 应用启动时播放一次；路由始终留在原地址，表单与登录回跳不受影响。 */
export function StartupGate({ children }: { children: ReactNode }) {
  const [entered, setEntered] = useState(() =>
    ['/intro-preview', '/display'].includes(window.location.pathname),
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
