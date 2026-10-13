import { Alert } from 'antd';
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus';

/**
 * 断网提示条。
 *
 * 只做提示、不做假装成功：断网时数据提交不了，就必须如实告诉使用者，
 * 而不是让人以为已经录进去了——那会直接污染第二天的采购预测。
 */
export function OfflineNotice() {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <Alert
      banner
      type="warning"
      showIcon
      message="网络已断开"
      description="页面可以继续浏览，但数据暂时无法提交。恢复网络后请重新提交本次录入。"
    />
  );
}
