import { Tag } from 'antd';
import { AdminPageHeading } from '@/layouts/AdminPageHeading';
import { useAgentStatus } from '../hooks/useAgentStatus';

/** 把模型标识显示成人能读的名字；未知模型保留原值，不替它编品牌。 */
function modelDisplayName(name: string): string {
  if (name.toLowerCase().startsWith('deepseek-')) {
    const parts = name
      .slice('deepseek-'.length)
      .split('-')
      .map((part) => (part.toLowerCase() === 'pro' ? 'Pro' : part.toUpperCase()));
    return `DeepSeek ${parts.join(' ')}`;
  }
  return name;
}

export function AgentHeaderTitle() {
  const status = useAgentStatus();
  const modelStatus = status.isPending
    ? '连接中'
    : status.isError
      ? '未连接'
      : status.data?.mode === 'model'
        ? status.data.model_name
          ? `已接入 ${modelDisplayName(status.data.model_name)}`
          : '已接入模型'
        : '规则模式';

  return (
    <AdminPageHeading
      title="知味膳食助手"
      tag={
        <Tag
          className="zw-admin-page-status"
          color={status.isError ? 'red' : status.data?.mode === 'model' ? 'green' : 'default'}
          variant="filled"
        >
          {modelStatus}
        </Tag>
      }
      tagline="把一句安排，变成可核对的菜单与采购。"
    />
  );
}
