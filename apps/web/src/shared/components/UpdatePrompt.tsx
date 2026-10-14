import { Button } from 'antd';
import { useRegisterSW } from 'virtual:pwa-register/react';

/** 隔多久主动问一次有没有新版本。 */
const CHECK_INTERVAL_MS = 30 * 60 * 1000;

/**
 * 「有新版本可用」提示条。
 *
 * 为什么要它：前端是预缓存的应用壳，浏览器会先拿缓存里的旧版本，
 * 所以「部署完了却看不到新东西」是常态，而且很难自查。与其让人反复硬刷新，
 * 不如让应用自己发现新版本并说清楚——这也符合本系统「不静默」的一贯做法。
 *
 * 提示里必须写明刷新会丢什么：离线队列里**已提交**的采集单存在 localStorage，刷新不会丢；
 * 但**填了一半还没提交**的表单会丢。不说清楚，用户会在录入到一半时点刷新。
 */
export function UpdatePrompt() {
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (!registration) return;
      // 只靠页面加载时检查一次是不够的：公开大屏这类页面会整天开着，
      // 那样永远等不到提示。这里定时主动问一次。
      window.setInterval(() => void registration.update(), CHECK_INTERVAL_MS);
    },
  });

  if (!needRefresh) return null;

  return (
    <div
      data-testid="update-prompt"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 2000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        padding: '8px 16px',
        background: '#1677ff',
        color: '#fff',
        fontSize: 14,
      }}
    >
      <span>新版本已就绪。刷新后生效；填了一半还没提交的录入会丢失。</span>
      <Button size="small" onClick={() => void updateServiceWorker(true)}>
        刷新
      </Button>
    </div>
  );
}
