import {
  CalendarOutlined,
  HistoryOutlined,
  PlusOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { Button, DatePicker, InputNumber, Select } from 'antd';
import dayjs from 'dayjs';
import type { AgentDish, DinerForecast, PlanParameters, SessionSummary } from '../api/types';

interface Props {
  parameters: PlanParameters;
  onChange: (value: PlanParameters) => void;
  dishes: AgentDish[];
  sessions: SessionSummary[];
  activeSession: string | null;
  onSelectSession: (id: string) => void;
  onNew: () => void;
  busy: boolean;
  canPlan: boolean;
  dinerForecast: DinerForecast | null;
  dinerForecastLoading: boolean;
  onCheckData: () => void;
  unavailable: boolean;
}

export function TaskPanel({
  parameters,
  onChange,
  dishes,
  sessions,
  activeSession,
  onSelectSession,
  onNew,
  busy,
  canPlan,
  dinerForecast,
  dinerForecastLoading,
  onCheckData,
  unavailable,
}: Props) {
  const update = (patch: Partial<PlanParameters>) => onChange({ ...parameters, ...patch });
  const predictedDiners = dinerForecast?.predicted_diner_count ?? null;
  const manualDiners =
    predictedDiners != null &&
    parameters.diner_count != null &&
    parameters.diner_count !== predictedDiners;
  return (
    <aside className="zw-agent-task" aria-label="任务条件与历史对话">
      <div className="zw-agent-task-heading">
        <span>
          <CalendarOutlined /> 任务条件
        </span>
        <span className="zw-agent-subtle">随时可调整</span>
      </div>
      <fieldset disabled={busy || !canPlan} className="zw-agent-fields">
        <label htmlFor="agent-date">供餐日期</label>
        <DatePicker
          id="agent-date"
          allowClear={false}
          value={dayjs(parameters.on_date)}
          disabled={busy || !canPlan}
          onChange={(value) => value && update({ on_date: value.format('YYYY-MM-DD') })}
          disabledDate={(value) => value.isBefore(dayjs().startOf('day'))}
        />
        <label htmlFor="agent-meal">餐次</label>
        <Select
          id="agent-meal"
          value={parameters.meal_type}
          disabled={busy || !canPlan}
          onChange={(meal_type) => update({ meal_type })}
          options={[
            { value: 'BREAKFAST', label: '早餐' },
            { value: 'LUNCH', label: '午餐' },
            { value: 'DINNER', label: '晚餐' },
          ]}
        />
        <div className="zw-agent-field-pair">
          <div>
            <label htmlFor="agent-diners">预计人次</label>
            <InputNumber
              id="agent-diners"
              min={1}
              max={100000}
              precision={0}
              value={parameters.diner_count}
              placeholder={dinerForecastLoading ? '系统预测中' : '填写人数'}
              disabled={busy || !canPlan}
              onChange={(value) => update({ diner_count: value })}
            />
          </div>
          <div>
            <label htmlFor="agent-budget">每人预算 / 元</label>
            <InputNumber
              id="agent-budget"
              min={0.01}
              max={1000}
              precision={2}
              value={Number(parameters.budget_per_person)}
              disabled={busy || !canPlan}
              onChange={(value) => value != null && update({ budget_per_person: String(value) })}
            />
          </div>
        </div>
        {predictedDiners != null && (
          <p className="zw-agent-diner-source">
            系统预测 {predictedDiners} 人
            {dinerForecast?.lower != null && dinerForecast.upper != null
              ? ` · 参考区间 ${dinerForecast.lower}–${dinerForecast.upper} 人`
              : ''}
            {manualDiners ? ' · 当前为手动值' : ` · ${dinerForecast?.basis_label ?? ''}`}
          </p>
        )}
        <label htmlFor="agent-exclusions">本次不做的菜</label>
        <Select
          id="agent-exclusions"
          mode="multiple"
          allowClear
          value={parameters.excluded_dish_ids}
          placeholder="可选，保留其他约束"
          disabled={busy || !canPlan}
          options={dishes.map((dish) => ({ value: dish.id, label: dish.name }))}
          optionFilterProp="label"
          onChange={(excluded_dish_ids) => update({ excluded_dish_ids })}
        />
      </fieldset>
      <Button
        className="zw-agent-check-data"
        block
        icon={<FileSearchOutlined />}
        disabled={busy || unavailable}
        onClick={onCheckData}
      >
        先检查数据
      </Button>
      <p className="zw-agent-task-note">
        计算用当前条件。对话中可更改人数、每人预算或菜品；换菜会排除此菜并重算整餐。
      </p>
      {!canPlan && (
        <p className="zw-agent-permission">当前账号可核查记录；菜单安排与发布由食堂负责。</p>
      )}
      <div className="zw-agent-history-heading">
        <span>
          <HistoryOutlined /> 最近任务
        </span>
        <Button type="text" size="small" icon={<PlusOutlined />} disabled={busy} onClick={onNew}>
          新建
        </Button>
      </div>
      <nav className="zw-agent-history" aria-label="对话历史">
        {sessions.length ? (
          sessions.map((session) => (
            <button
              type="button"
              key={session.id}
              className={session.id === activeSession ? 'is-current' : ''}
              disabled={busy}
              onClick={() => onSelectSession(session.id)}
              aria-current={session.id === activeSession ? 'page' : undefined}
            >
              <span>{session.title}</span>
              <small>
                {dayjs(session.updated_at).format('MM-DD HH:mm')}
                {session.revision > 0 ? ` · ${session.revision} 版方案` : ''}
              </small>
            </button>
          ))
        ) : (
          <p className="zw-agent-subtle">任务会随账号保存，刷新后可继续。</p>
        )}
      </nav>
    </aside>
  );
}
