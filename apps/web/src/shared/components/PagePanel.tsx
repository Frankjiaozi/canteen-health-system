import type { ReactNode } from 'react';
import { Card } from 'antd';

interface PagePanelProps {
  filters?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

/** 业务页统一面板：一条工具栏 + 一张贴边表格，页标题只留在全局页眉里。 */
export function PagePanel({
  filters,
  actions,
  children,
  className,
  bodyClassName,
}: PagePanelProps) {
  const hasToolbar = filters !== undefined || actions !== undefined;

  return (
    <Card
      className={`zw-page-panel${className ? ` ${className}` : ''}`}
      styles={{ body: { padding: 0 } }}
    >
      {hasToolbar ? (
        <div className="zw-page-toolbar">
          <div className="zw-page-toolbar-filters">{filters}</div>
          {actions ? <div className="zw-page-toolbar-actions">{actions}</div> : null}
        </div>
      ) : null}
      <div className={`zw-page-body${bodyClassName ? ` ${bodyClassName}` : ''}`}>{children}</div>
    </Card>
  );
}
