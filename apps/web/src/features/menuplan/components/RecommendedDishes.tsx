import {
  Alert,
  Button,
  Card,
  Collapse,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useDecideSuggestion } from '@/features/recommendation/hooks/useRecommendation';
import {
  decisionLabel,
  describeGap,
  describeGapStatus,
  energyTargetWarning,
  reasonLabel,
} from '@/features/recommendation/lib/present';
import type {
  MenuPlanDish,
  MenuPlanResponse,
  MenuSuggestionRead,
  NutrientGap,
  SuggestionReason,
} from '../types';

const TONE_COLOR = {
  ok: 'green',
  over: 'red',
  under: 'orange',
} as const;

const DECISION_COLOR = { ok: 'green', bad: 'red', pending: 'default' } as const;

/**
 * ① 明天做哪几道菜。
 *
 * 这一节刻意**不列份数**：份数由预测给出、在②里跟着用料一起出现。
 * 推荐回答的是「做哪几道菜」，把它没回答的问题也列在这里，看的人会分不清该看哪个数。
 */
export function RecommendedDishes({
  plan,
  suggestion,
  synced,
  syncing,
  onSync,
}: {
  plan: MenuPlanResponse;
  suggestion: MenuSuggestionRead | undefined;
  /** 这一版是否已经写入当日数据 */
  synced: boolean;
  syncing: boolean;
  onSync: () => void;
}) {
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);
  const decideMutation = useDecideSuggestion();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');

  const decision = decisionLabel(suggestion?.status ?? 'PENDING');
  const warning = energyTargetWarning(plan.target_basis);

  return (
    <Card
      size="small"
      title={
        <Space>
          <span>① 明日菜品推荐</span>
          <Tag color={DECISION_COLOR[decision.tone]}>{decision.text}</Tag>
        </Space>
      }
      extra={
        <Typography.Text type="secondary">
          {plan.date} {plan.meal_type_label} · {plan.diner_count} 人次
        </Typography.Text>
      }
    >
      {warning ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="能量目标尚未核实"
          description={warning}
        />
      ) : null}

      <Table<MenuPlanDish>
        rowKey="dish_id"
        size="small"
        pagination={false}
        dataSource={plan.dishes}
        columns={[
          { title: '菜品', dataIndex: 'dish_name', width: 160 },
          { title: '类别', dataIndex: 'category_label', width: 100 },
          { title: '做法', dataIndex: 'cooking_method_label', width: 90 },
          {
            title: '单份能量',
            dataIndex: 'energy_kcal',
            width: 110,
            align: 'right',
            render: (value: string) => `${Number(value).toFixed(1)} 千卡`,
          },
          {
            title: '单份食盐',
            dataIndex: 'salt_g',
            width: 110,
            align: 'right',
            render: (value: string) => `${value} 克`,
          },
          {
            title: '受欢迎度',
            dataIndex: 'popularity',
            width: 120,
            align: 'right',
            render: (value: string) => `${value} 份/次`,
          },
          {
            title: '营养取自',
            dataIndex: 'nutrition_basis',
            width: 130,
            render: (value: string) => <Tag>{value || '—'}</Tag>,
          },
        ]}
      />

      {canWrite ? (
        <Space
          wrap
          style={{
            width: '100%',
            marginTop: 16,
            paddingTop: 16,
            borderTop: '1px solid #f0f0f0',
          }}
        >
          <Popconfirm
            title={`把这一版菜单同步至 ${plan.date} 的当日数据？`}
            description={
              <div style={{ maxWidth: 320 }}>
                菜单会写进这一天的当日数据：<b>每日采集</b>的供应菜品直接按它勾好（仍然可以改），
                <b>公开大屏</b>当天早上就能显示。这一天的采集一旦提交过，菜单以实际供应为准，
                计划不会再覆盖它。
              </div>
            }
            okText="确认同步"
            cancelText="取消"
            onConfirm={onSync}
          >
            <Button type="primary" loading={syncing} disabled={suggestion?.status === 'REJECTED'}>
              {synced ? '重新同步至当日数据' : '同步至当日数据'}
            </Button>
          </Popconfirm>
          <Button danger disabled={synced} onClick={() => setRejecting(true)}>
            否决
          </Button>
        </Space>
      ) : null}

      {synced ? (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 16 }}
          message={`已写入 ${plan.date} 的当日数据`}
          description="每日采集的「当日供应菜品」已按这份菜单勾好，公开大屏也看得到。临时换菜在采集页改，保存即按实际供应覆盖。"
        />
      ) : null}

      {suggestion?.status === 'REJECTED' && suggestion.rejected_reason ? (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 16 }}
          message={`否决原因：${suggestion.rejected_reason}`}
          description="它会被用来改进后续推荐。"
        />
      ) : null}

      <Collapse
        style={{ marginTop: 16 }}
        items={[
          {
            key: 'gaps',
            label: `与营养目标的差距（${
              plan.gaps.filter((gap) => gap.status !== 'ok').length
            } 项需关注）`,
            children: (
              <Table<NutrientGap>
                rowKey="code"
                size="small"
                pagination={false}
                dataSource={plan.gaps}
                columns={[
                  { title: '指标', dataIndex: 'label', width: 120 },
                  { title: '目标', dataIndex: 'target_text', width: 180 },
                  { title: '实际', dataIndex: 'actual', width: 110, align: 'right' },
                  {
                    title: '结论',
                    width: 280,
                    render: (_, row) => {
                      const style = describeGapStatus(row);
                      return (
                        <Space>
                          <Tag color={TONE_COLOR[style.tone]}>{style.label}</Tag>
                          <Typography.Text>{describeGap(row)}</Typography.Text>
                        </Space>
                      );
                    },
                  },
                  {
                    title: '口径',
                    render: (_, row) =>
                      row.note ? (
                        <Typography.Text type="secondary">{row.note}</Typography.Text>
                      ) : (
                        <Typography.Text type="secondary">—</Typography.Text>
                      ),
                  },
                ]}
              />
            ),
          },
          {
            key: 'reasons',
            label: `推荐理由（${plan.reasons.length} 条）`,
            children: (
              <>
                <Table<SuggestionReason>
                  rowKey={(row) => `${row.kind}-${row.text}`}
                  size="small"
                  pagination={false}
                  showHeader={false}
                  dataSource={plan.reasons}
                  columns={[
                    {
                      title: '类别',
                      width: 110,
                      render: (_, row) => <Tag>{reasonLabel(row)}</Tag>,
                    },
                    { title: '说明', render: (_, row) => row.text },
                  ]}
                />
                {plan.excluded_dishes.length > 0 ? (
                  <Typography.Text type="secondary">
                    因「不连续两日重复」排除：{plan.excluded_dishes.join('、')}
                  </Typography.Text>
                ) : null}
              </>
            ),
          },
        ]}
      />

      <Modal
        open={rejecting}
        title="否决这份菜单"
        okText="确认否决"
        cancelText="取消"
        onCancel={() => setRejecting(false)}
        onOk={() => {
          if (!suggestion) return;
          decideMutation.mutate({ id: suggestion.id, status: 'REJECTED', reason });
          setRejecting(false);
        }}
      >
        <Typography.Paragraph type="secondary">
          写清原因——需求里写明它会被用来改进后续推荐，只留一句「不合适」等于没记。
        </Typography.Paragraph>
        <Input.TextArea
          rows={3}
          maxLength={255}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="例如：周五学生普遍不留校吃午饭"
        />
      </Modal>
    </Card>
  );
}
