import {
  CheckCircleOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { Alert, Button, Select, Tabs, Tag } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Conversation, PlanVersion, Review } from '../api/types';
import { comparePlans, formatAmount } from '../lib/compare';
import { ReadinessResult } from './ReadinessResult';
import { basisRows } from '../lib/evidence';

const STATUS_LABEL = { ok: '在目标区间', under: '低于目标', over: '高于目标' };

function Comparison({ version, versions }: { version: PlanVersion; versions: PlanVersion[] }) {
  const [chosen, setChosen] = useState<number | null>(null);
  const options = versions.filter((item) => item.revision !== version.revision);
  const previous = options.find((item) => item.revision === chosen) ?? options.at(-1);
  if (!previous)
    return (
      <div className="zw-agent-result-empty">
        <SwapOutlined />
        <h3>保留每一次调整</h3>
        <p>修改人数、预算或排除一道菜后重算，便可查看菜品和采购金额的变化。</p>
      </div>
    );
  const comparison = comparePlans(version, previous);
  return (
    <div className="zw-agent-comparison">
      <label htmlFor="agent-compare-version">第 {version.revision} 版，对比</label>
      <Select
        id="agent-compare-version"
        value={previous.revision}
        onChange={setChosen}
        options={options.map((item) => ({
          value: item.revision,
          label: `第 ${item.revision} 版 · ${item.result.date}`,
        }))}
      />
      {!comparison.sameScope && (
        <Alert type="warning" showIcon title="两个方案的日期或餐次不同，金额不宜直接判断优劣。" />
      )}
      <dl>
        <div>
          <dt>就餐人次变化</dt>
          <dd>
            {comparison.dinerDelta > 0 ? '+' : ''}
            {comparison.dinerDelta} 人次
          </dd>
        </div>
        <div>
          <dt>采购金额变化</dt>
          <dd>
            {comparison.costDelta != null
              ? `${comparison.costDelta > 0 ? '+' : ''}${formatAmount(comparison.costDelta)} 元`
              : '缺少完整单价，无法比较'}
          </dd>
        </div>
      </dl>
      <h4>新加入</h4>
      <p>{comparison.added.map((dish) => dish.dish_name).join('、') || '菜品未增加'}</p>
      <h4>移除</h4>
      <p>{comparison.removed.map((dish) => dish.dish_name).join('、') || '菜品未移除'}</p>
      <p className="zw-agent-subtle">
        两版计算快照均保留。人数和预算不同时，采购金额的增减不代表节约或浪费。
      </p>
    </div>
  );
}

function ReviewResult({ review, sessionId }: { review: Review; sessionId: string }) {
  return (
    <section className="zw-agent-review">
      <div className="zw-agent-section-title">
        <h3>供应记录核查</h3>
        <Button
          type="text"
          icon={<DownloadOutlined />}
          href={`/agent-api/v1/sessions/${sessionId}/review.md`}
        >
          导出
        </Button>
      </div>
      <p>
        {review.start} 至 {review.end}，共 {review.record_count} 份记录，覆盖{' '}
        {review.days_with_records} 天。
      </p>
      <p className="zw-agent-subtle">{review.note}</p>
      {review.truncated && (
        <Alert type="warning" title="记录过多，当前核查没有覆盖全部记录，请缩短时间范围。" />
      )}
      {review.issues.length ? (
        <ol className="zw-agent-review-issues">
          {review.issues.map((issue, index) => (
            <li key={`${issue.date}-${issue.meal_type}-${index}`}>
              <span>
                {issue.date} {issue.meal_label}
              </span>
              <h4>{issue.title}</h4>
              <p>{issue.detail}</p>
              <p className="zw-agent-subtle">{issue.suggestion}</p>
              <Link to={issue.link}>打开原始采集单</Link>
            </li>
          ))}
        </ol>
      ) : (
        <div className="zw-agent-result-empty">
          <FileSearchOutlined />
          <h3>{review.record_count ? '本次规则未发现需要提示的记录' : '这段时间还没有采集记录'}</h3>
          <p>
            {review.record_count
              ? '这不代表所有数据都正确，仍需结合人工记录判断。'
              : '先录入真实供餐数据，再重新核查。'}
          </p>
          <Link to="/admin/collection">前往每日采集</Link>
        </div>
      )}
      {review.missing_dates.length > 0 && (
        <details className="zw-agent-missing">
          <summary>{review.missing_dates.length} 天没有记录，核对是否营业</summary>
          <p>{review.missing_dates.join('、')}</p>
        </details>
      )}
    </section>
  );
}

interface Props {
  activeTab: string;
  onTabChange: (value: string) => void;
  conversation: Conversation | undefined;
  revision: number | null;
  onRevision: (value: number) => void;
  onReplace: (name: string) => void;
  onPublish: (version: PlanVersion) => void;
  onReuse: (version: PlanVersion) => void;
  canPlan: boolean;
  busy: boolean;
  publishing: boolean;
}

export function ResultPanel({
  activeTab,
  onTabChange,
  conversation,
  revision,
  onRevision,
  onReplace,
  onPublish,
  onReuse,
  canPlan,
  busy,
  publishing,
}: Props) {
  const versions = conversation?.plans ?? [];
  const version = versions.find((item) => item.revision === revision) ?? versions.at(-1);
  const latest = versions.at(-1);
  const review = conversation?.review;
  const readiness = conversation?.readiness;
  if (!version)
    return (
      <section className="zw-agent-results" aria-label="任务结果">
        {readiness && (activeTab === 'readiness' || !review) ? (
          <ReadinessResult report={readiness} />
        ) : review && conversation ? (
          <ReviewResult review={review} sessionId={conversation.id} />
        ) : (
          <div className="zw-agent-result-empty zw-agent-awaiting">
            <div className="zw-agent-tray" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <h3>菜单与采购，会在这里展开</h3>
            <p>
              先告诉知味供餐安排。
              <br />
              每一版都保留计算依据，确认后才写入正式菜单。
            </p>
            <ul>
              <li>按历史预测份数</li>
              <li>按配方汇总采购</li>
              <li>营养差距如实列出</li>
            </ul>
          </div>
        )}
      </section>
    );
  const plan = version.result;
  const isLatest = version.revision === latest?.revision;
  const changed = plan.gaps.filter((gap) => gap.status !== 'ok');
  const targetNotice = Object.values(plan.target_basis).filter(
    (value): value is string =>
      typeof value === 'string' && (value.includes('待核实') || value.includes('演示')),
  );
  const items = [
    {
      key: 'plan',
      label: '菜单与营养',
      children: (
        <>
          <div className="zw-agent-dish-list">
            {plan.dishes.map((dish) => (
              <div className="zw-agent-dish" key={dish.dish_id}>
                <div>
                  <h4>{dish.dish_name}</h4>
                  <span>
                    {dish.category_label} · {dish.cooking_method_label}
                  </span>
                </div>
                <div className="zw-agent-dish-numbers">
                  <strong>
                    {dish.prediction_fallback ? '估算 ' : ''}
                    {formatAmount(dish.planned_servings ?? dish.predicted_servings)}{' '}
                    <small>份</small>
                  </strong>
                  <span>{formatAmount(dish.energy_kcal, 0)} kcal / 份</span>
                </div>
                {canPlan && isLatest && (
                  <Button
                    type="text"
                    size="small"
                    disabled={busy || publishing}
                    onClick={() => onReplace(dish.dish_name)}
                    aria-label={`换掉${dish.dish_name}`}
                  >
                    换菜
                  </Button>
                )}
              </div>
            ))}
          </div>
          <div className="zw-agent-section-title">
            <h3>人均供给与目标差距</h3>
            <span>{changed.length ? `${changed.length} 项需要关注` : '按当前目标计算'}</span>
          </div>
          <div className="zw-agent-table-wrap">
            <table className="zw-agent-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>计算值</th>
                  <th>目标</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {plan.gaps.map((gap) => (
                  <tr key={gap.code}>
                    <th scope="row">{gap.label}</th>
                    <td>
                      {formatAmount(gap.actual)} {gap.unit}
                    </td>
                    <td>{gap.target_text}</td>
                    <td>
                      <span className={`zw-agent-gap is-${gap.status}`}>
                        {STATUS_LABEL[gap.status as keyof typeof STATUS_LABEL] ?? gap.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="zw-agent-subtle">
            供给量不等于实际摄入量。建议目标未必全部满足，请结合差距决定是否修改。
          </p>
          {targetNotice.map((note) => (
            <Alert key={note} type="warning" showIcon title={note} />
          ))}
        </>
      ),
    },
    {
      key: 'purchase',
      label: '采购清单',
      children: (
        <>
          <p className="zw-agent-subtle">{plan.servings_note}</p>
          <div className="zw-agent-table-wrap">
            <table className="zw-agent-table">
              <thead>
                <tr>
                  <th>原料</th>
                  <th>数量 / 公斤</th>
                  <th>单价 / 元</th>
                  <th>金额 / 元</th>
                </tr>
              </thead>
              <tbody>
                {plan.requirements.map((row, index) => (
                  <tr key={`${row.name}-${index}`}>
                    <th scope="row">{row.name}</th>
                    <td>{formatAmount(row.quantity, 3)}</td>
                    <td>{formatAmount(row.unit_price)}</td>
                    <td>{formatAmount(row.estimated_cost)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th colSpan={3}>采购合计</th>
                  <td>{formatAmount(plan.total_cost)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="zw-agent-subtle">
            单价口径：元 / 公斤市品。未录单价的项目不计入合计，导出与当前快照一致。
          </p>
          <Button
            icon={<DownloadOutlined />}
            href={`/agent-api/v1/sessions/${conversation?.id}/purchase.csv?revision=${version.revision}`}
          >
            导出这版采购单
          </Button>
        </>
      ),
    },
    {
      key: 'compare',
      label: '方案对比',
      children: <Comparison key={version.revision} version={version} versions={versions} />,
    },
    {
      key: 'evidence',
      label: '计算依据',
      children: (
        <div className="zw-agent-evidence">
          <h3>这版是怎样算出的</h3>
          <ol>
            {plan.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ol>
          <h4>菜品选择理由</h4>
          <ul>
            {plan.reasons.map((reason, index) => (
              <li key={index}>{reason.text}</li>
            ))}
          </ul>
          {plan.calendar_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {plan.skipped_predictions.length > 0 && (
            <p>历史不足的菜品：{plan.skipped_predictions.join('、')}</p>
          )}
          <h4>目标与数据口径</h4>
          <dl>
            {basisRows(plan.target_basis).map((row) => (
              <div key={row.key}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
          <h4>快照记录</h4>
          <p>
            第 {version.revision} 版，{new Date(version.created_at).toLocaleString('zh-CN')}
          </p>
          <code>{plan.suggestion_id}</code>
          {version.readiness && (
            <>
              <h4>生成前的检查快照</h4>
              <ReadinessResult report={version.readiness} />
            </>
          )}
          <p className="zw-agent-subtle">
            数字来自业务服务；解释不能替代实际配方、称重与人工核对。
          </p>
        </div>
      ),
    },
    ...(review && conversation
      ? [
          {
            key: 'review',
            label: '记录核查',
            children: <ReviewResult review={review} sessionId={conversation.id} />,
          },
        ]
      : []),
    ...(readiness
      ? [
          {
            key: 'readiness',
            label: '数据体检',
            children: (
              <>
                {(readiness.on_date !== plan.date || readiness.meal_type !== plan.meal_type) && (
                  <p className="zw-agent-publish-warning" role="status">
                    本次检查针对 {readiness.on_date} {readiness.meal_type_label}。上方仍为第{' '}
                    {version.revision} 版的 {plan.date} {plan.meal_type_label}
                    方案，检查不会改变已有菜单。
                  </p>
                )}
                <ReadinessResult report={readiness} />
              </>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="zw-agent-results" aria-label="菜单、采购与依据">
      <div className="zw-agent-result-top">
        <div>
          <span className="zw-agent-subtle">
            {plan.date} {plan.meal_type_label}
          </span>
          <h2>{plan.diner_count.toLocaleString()} 人的供餐安排</h2>
        </div>
        <Select
          aria-label="查看方案版本"
          value={version.revision}
          onChange={onRevision}
          options={versions.map((item) => ({
            value: item.revision,
            label: `第 ${item.revision} 版${item.revision === latest?.revision ? ' · 最新' : ''}`,
          }))}
        />
      </div>
      <div className="zw-agent-plan-totals">
        <div>
          <span>{plan.missing_price_warning ? '已知价格部分合计 / 元' : '采购预计 / 元'}</span>
          <strong>{formatAmount(plan.total_cost)}</strong>
        </div>
        <div>
          <span>总预算 / 元</span>
          <strong>{formatAmount(plan.budget)}</strong>
        </div>
        <Tag color={version.publication ? 'success' : 'default'}>
          {version.publication ? '已确认发布' : '待人工确认'}
        </Tag>
      </div>
      <div className="zw-agent-version-actions">
        <Button
          type="text"
          size="small"
          disabled={busy || publishing || !canPlan}
          onClick={() => onReuse(version)}
        >
          载入此版条件
        </Button>
        <Button
          type="text"
          size="small"
          target="_blank"
          rel="noopener noreferrer"
          href={`/agent-api/v1/sessions/${conversation?.id}/report.html?revision=${version.revision}&download=false`}
        >
          预览报告
        </Button>
        <Button
          type="text"
          size="small"
          icon={<DownloadOutlined />}
          href={`/agent-api/v1/sessions/${conversation?.id}/report.html?revision=${version.revision}`}
        >
          下载完整报告
        </Button>
      </div>
      {!plan.calculation_version && (
        <Alert
          type="warning"
          showIcon
          title="这版使用旧计算口径。历史记录保留，新的安排请载入条件后重新计算。"
        />
      )}
      {plan.missing_price_warning && (
        <Alert type="warning" showIcon title={plan.missing_price_warning} />
      )}
      {changed.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title={`有 ${changed.length} 项偏离建议目标，请核对营养差距后决定是否调整。`}
        />
      )}
      {plan.total_cost != null && Number(plan.total_cost) > Number(plan.budget) && (
        <Alert type="error" showIcon title="采购金额高于预算，请调整后再发布。" />
      )}
      <Tabs
        activeKey={items.some((item) => item.key === activeTab) ? activeTab : 'plan'}
        onChange={onTabChange}
        items={items}
      />
      {version.publication ? (
        <div className="zw-agent-published">
          <CheckCircleOutlined />
          <div>
            <strong>本版已确认发布</strong>
            <p>
              {version.publication.published_by} ·{' '}
              {new Date(version.publication.published_at).toLocaleString('zh-CN')}
            </p>
          </div>
          <Link to={`/admin/collection?date=${plan.date}&meal=${plan.meal_type}`}>
            查看当餐采集单
          </Link>
        </div>
      ) : (
        <div className="zw-agent-confirm-bar">
          <p>
            {isLatest
              ? '核对菜品、金额和差距，确认后写入这餐菜单。'
              : '当前为历史版本。发布前请选择最新方案。'}
          </p>
          <Button
            type="primary"
            loading={publishing}
            disabled={
              !canPlan ||
              !isLatest ||
              busy ||
              (plan.total_cost != null && Number(plan.total_cost) > Number(plan.budget))
            }
            onClick={() => onPublish(version)}
          >
            确认并发布菜单
          </Button>
        </div>
      )}
    </section>
  );
}
