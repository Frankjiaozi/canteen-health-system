import { Alert } from 'antd';
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus';

/**
 * 断网提示条。
 *
 * 只做提示、不做假装成功：断网时数据提交不了，就必须如实告诉使用者，
 * 而不是让人以为已经录进去了——那会直接污染第二天的采购预测。
 *
 * 采集页断网时提交会进本地队列并在联网后自动补交，其他页面的写操作则确实提交不了，
 * 所以文案要覆盖两种情况：说清「没丢」和「要重新提交」分别是什么时候。
 *
 * 待同步条数由上层传入，不在这里去读采集域的状态：shared 是底层，不该反向依赖 features。
 */
export function OfflineNotice({ pendingCount = 0 }: { pendingCount?: number }) {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <Alert
      banner
      type="warning"
      showIcon
      message="网络已断开"
      description={
        pendingCount > 0
          ? `采集页的录入会先存在本机，现有 ${pendingCount} 条待同步，恢复网络后自动补交。其他页面的修改暂时提交不了。`
          : '采集页可以继续录入，恢复网络后自动补交；其他页面的修改暂时提交不了。'
      }
    />
  );
}
