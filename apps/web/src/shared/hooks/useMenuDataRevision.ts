import { useEffect, useState } from 'react';

const STORAGE_KEY = 'canteen:menu-data-revision';
const CHANNEL_NAME = 'canteen:menu-data';

function readRevision(): number {
  if (typeof window === 'undefined') return 0;
  return Number(window.localStorage.getItem(STORAGE_KEY) ?? 0) || 0;
}

/** 菜单发布后通知同一浏览器的其它页面立即重取菜单相关数据。 */
export function notifyMenuDataChanged(): void {
  if (typeof window === 'undefined') return;
  const revision = Date.now();
  window.localStorage.setItem(STORAGE_KEY, String(revision));
  if (typeof BroadcastChannel === 'undefined') return;
  const channel = new BroadcastChannel(CHANNEL_NAME);
  channel.postMessage(revision);
  channel.close();
}

export function useMenuDataRevision(): number {
  const [revision, setRevision] = useState(readRevision);

  useEffect(() => {
    const update = (value: number) => {
      setRevision((current) => Math.max(current, value));
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY && event.newValue) update(Number(event.newValue) || 0);
    };
    window.addEventListener('storage', onStorage);

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== 'undefined') {
      channel = new BroadcastChannel(CHANNEL_NAME);
      channel.onmessage = (event: MessageEvent<number>) => update(Number(event.data) || 0);
    }
    return () => {
      window.removeEventListener('storage', onStorage);
      channel?.close();
    };
  }, []);

  return revision;
}
