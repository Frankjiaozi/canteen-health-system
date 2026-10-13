import { useEffect, useState } from 'react';

// 浏览器在线状态。
//
// 食堂网络不稳定是常态，因此界面必须在断网时明确告诉使用者「现在提交不了」，
// 而不是让人反复点按钮却毫无反馈。
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  return isOnline;
}
