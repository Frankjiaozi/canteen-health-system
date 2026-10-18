import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { Button, Tag } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Readiness } from '../api/types';

const LABELS = { ready: '结构检查未见缺口', attention: '有待核对的数据', blocked: '先处理阻塞项' };

export function ReadinessResult({ report }: { report: Readiness }) {
  const [expanded, setExpanded] = useState(false);
  const issues = expanded ? report.issues : report.issues.slice(0, 12);
  return (
    <section className="zw-agent-readiness" aria-label="计划数据体检">
      <div className="zw-agent-section-title">
        <h3>
          <FileSearchOutlined /> 数据体检
        </h3>
        <Tag
          color={
            report.state === 'ready' ? 'success' : report.state === 'blocked' ? 'error' : 'warning'
          }
        >
          {LABELS[report.state]}
        </Tag>
      </div>
      <p>
        {report.on_date} {report.meal_type_label}，按检查时的排除条件核对。
      </p>
      <dl className="zw-agent-readiness-facts">
        <div>
          <dt>可用候选</dt>
          <dd>
            {report.available_count}
            <small> / {report.active_dish_count} 道在用</small>
          </dd>
        </div>
        <div>
          <dt>可预测份数</dt>
          <dd>
            {report.predicted_count}
            <small> 道</small>
          </dd>
        </div>
        <div>
          <dt>本餐次历史</dt>
          <dd>
            {report.days_with_records}
            <small> 天 · {report.history_record_count} 份记录</small>
          </dd>
        </div>
        <div>
          <dt>缺少单价</dt>
          <dd>
            {report.missing_price_count}
            <small> 项原料</small>
          </dd>
        </div>
      </dl>
      <div className="zw-agent-readiness-categories" aria-label="必需类别准备情况">
        {report.categories.map((row) => (
          <span
            key={row.code}
            className={row.available_count < row.required_minimum ? 'is-missing' : ''}
          >
            {row.available_count < row.required_minimum ? (
              <ExclamationCircleOutlined />
            ) : (
              <CheckCircleOutlined />
            )}
            {row.label} {row.available_count} 道<small>至少 {row.required_minimum} 道</small>
          </span>
        ))}
      </div>
      <p className="zw-agent-subtle">
        历史范围 {report.history_start} 至 {report.history_end}。
        {report.latest_record_date
          ? `最近有效人次：${report.latest_record_date}，${report.latest_diner_count} 人次。`
          : '尚无可用的本餐次人次基准。'}
      </p>
      {issues.length ? (
        <ol className="zw-agent-readiness-issues">
          {issues.map((issue, index) => (
            <li
              key={`${issue.code}-${issue.entity_id ?? index}`}
              className={`is-${issue.severity}`}
            >
              <div>
                <Tag color={issue.severity === 'blocking' ? 'error' : 'warning'}>
                  {issue.severity === 'blocking' ? '先处理' : '待核对'}
                </Tag>
                <h4>{issue.title}</h4>
              </div>
              <p>{issue.detail}</p>
              <p className="zw-agent-subtle">{issue.action}</p>
              <Link to={issue.link}>打开原数据核对</Link>
            </li>
          ))}
        </ol>
      ) : (
        <p className="zw-agent-readiness-ok">
          <CheckCircleOutlined /> 本次检查未发现结构缺口，仍需核对来源与实际供餐背景。
        </p>
      )}
      {report.issues.length > 12 && (
        <Button type="link" onClick={() => setExpanded(!expanded)}>
          {expanded ? '收起' : `查看当前返回的全部 ${report.issues.length} 项`}
        </Button>
      )}
      {report.truncated && (
        <p className="zw-agent-publish-warning">
          共 {report.issue_count} 项，本次最多展示 100 项；处理后重新检查。
        </p>
      )}
      <p className="zw-agent-subtle">{report.note}</p>
      <p className="zw-agent-subtle">
        检查时间：{new Date(report.checked_at).toLocaleString('zh-CN')}。数据变化后请重新体检。
      </p>
    </section>
  );
}
