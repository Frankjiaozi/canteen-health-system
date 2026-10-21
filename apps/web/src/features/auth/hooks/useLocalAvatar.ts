import { useSyncExternalStore } from 'react';

const eventName = 'zhiwei-avatar-changed';
const subscribe = (callback: () => void) => {
  window.addEventListener('storage', callback);
  window.addEventListener(eventName, callback);
  return () => {
    window.removeEventListener('storage', callback);
    window.removeEventListener(eventName, callback);
  };
};
export function useLocalAvatar(userId: string | undefined) {
  const key = `zhiwei.avatar.${userId ?? 'anonymous'}`;
  const avatar = useSyncExternalStore(
    subscribe,
    () => {
      if (!userId) return null;
      try {
        const value = localStorage.getItem(key);
        return value && /^data:image\/(png|jpeg|webp);base64,/.test(value) ? value : null;
      } catch {
        return null;
      }
    },
    () => null,
  );
  const saveAvatar = (value: string | null) => {
    if (!userId) return;
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
    window.dispatchEvent(new Event(eventName));
  };
  return { avatar, saveAvatar };
}
