import { useEffect, useState } from 'react';

const STORAGE_KEY = 'canteen:menu-data-revision';
const CHANNEL_NAME = 'canteen:menu-data';
const LOCAL_EVENT = 'canteen:menu-data-changed';
let memoryRevision = 0;

function validRevision(value: unknown): number {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 ? number : 0;
}

function readRevision(): number {
  if (typeof window === 'undefined') return 0;
  try {
    return Math.max(memoryRevision, validRevision(window.localStorage.getItem(STORAGE_KEY)));
  } catch {
    return memoryRevision;
  }
}

/** 菜单发布后通知同一浏览器的其它页面立即重取菜单相关数据。 */
export function notifyMenuDataChanged(): void {
  if (typeof window === 'undefined') return;
  const revision = Math.max(Date.now(), readRevision() + 1);
  memoryRevision = revision;
  window.dispatchEvent(new CustomEvent(LOCAL_EVENT, { detail: revision }));
  try {
    window.localStorage.setItem(STORAGE_KEY, String(revision));
  } catch {
    /* 存储不可用时，同页通知仍然有效。 */
  }
  if (typeof BroadcastChannel === 'undefined') return;
  let channel: BroadcastChannel | null = null;
  try {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.postMessage(revision);
  } catch {
    /* 通知失败不应把已成功的业务提交变成失败。 */
  } finally {
    channel?.close();
  }
}

export function useMenuDataRevision(): number {
  const [revision, setRevision] = useState(readRevision);

  useEffect(() => {
    const update = (value: number) => {
      memoryRevision = Math.max(memoryRevision, validRevision(value));
      setRevision((current) => Math.max(current, memoryRevision));
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY && event.newValue) update(validRevision(event.newValue));
    };
    const onLocal = (event: Event) => update((event as CustomEvent<number>).detail);
    window.addEventListener('storage', onStorage);
    window.addEventListener(LOCAL_EVENT, onLocal);

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        channel = new BroadcastChannel(CHANNEL_NAME);
        channel.onmessage = (event: MessageEvent<number>) => update(validRevision(event.data));
      } catch {
        /* 浏览器禁用广播时仍接收 storage 与同页事件。 */
      }
    }
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(LOCAL_EVENT, onLocal);
      channel?.close();
    };
  }, []);

  return revision;
}
