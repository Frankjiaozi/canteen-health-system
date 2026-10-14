import { Alert, Button, Card, Input, Modal, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { useDecideSuggestion } from '../hooks/useRecommendation';
import {
  decisionLabel,
  describeGap,
  describeGapStatus,
  energyTargetWarning,
  reasonLabel,
} from '../lib/present';
import type { MenuSuggestionRead, NutrientGap, PlannedDishRead } from '../types';

const TONE_COLOR = {
  ok: 'green',
  over: 'red',
  under: 'orange',
  pending: 'default',
  bad: 'red',
} as const;

/** 一份菜单建议的完整呈现：菜单、差距、理由、采纳与否决。 */
export function SuggestionDetail({ suggestion }: { suggestion: MenuSuggestionRead }) {
  const { data: user } = useCurrentUser();
  const decideMutation = useDecideSuggestion();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const canWrite = canWriteBusinessData(user);
  const decision = decisionLabel(suggestion.status);
  const warning = energyTargetWarning(suggestion.target_basis);

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title={
          <Space>
            <span>
              {suggestion.date} {suggestion.meal_type_label}菜单建议
            </span>
            <Tag color={TONE_COLOR[decision.tone]}>{decision.text}</Tag>
          </Space>
        }
        extra={
          <Typography.Text>
            成本 {suggestion.cost_estimate} 元 / 预算 {suggestion.budget} 元（
            {suggestion.diner_count} 人次）
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
        {suggestion.missing_price_warning ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={suggestion.missing_price_warning}
          />
        ) : null}

        <Table<PlannedDishRead>
          rowKey="dish_id"
          size="small"
          pagination={false}
          scroll={{ x: 900 }}
          dataSource={suggestion.dishes}
          columns={[
            { title: '菜品', dataIndex: 'dish_name', width: 160, fixed: 'left' },
            { title: '类别', dataIndex: 'category_label', width: 90 },
            { title: '做法', dataIndex: 'cooking_method_label', width: 80 },
            {
              title: '建议份数',
              dataIndex: 'servings',
              width: 110,
              align: 'right',
              render: (value: string) => Math.round(Number(value)).toLocaleString('zh-CN'),
            },
            { title: '成本（元）', dataIndex: 'cost', width: 110, align: 'right' },
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
              width: 110,
              align: 'right',
              render: (value: string) => `${value} 份/次`,
            },
          ]}
        />
      </Card>

      <Card size="small" title="与营养目标的差距">
        <Table<NutrientGap>
          rowKey="code"
          size="small"
          pagination={false}
          dataSource={suggestion.gaps}
          columns={[
            { title: '指标', dataIndex: 'label', width: 120 },
            { title: '目标', dataIndex: 'target_text', width: 180 },
            { title: '实际', dataIndex: 'actual', width: 110, align: 'right' },
            {
              title: '结论',
              width: 260,
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
      </Card>

      <Card size="small" title="推荐理由">
        <Table
          rowKey={(reason) => `${reason.kind}-${reason.text}`}
          size="small"
          pagination={false}
          showHeader={false}
          dataSource={suggestion.reasons}
          columns={[
            {
              title: '类别',
              width: 110,
              render: (_, reason) => <Tag>{reasonLabel(reason)}</Tag>,
            },
            { title: '说明', render: (_, reason) => reason.text },
          ]}
        />
        {suggestion.excluded_dishes.length > 0 ? (
          <Typography.Text type="secondary">
            因「不连续两日重复」排除：{suggestion.excluded_dishes.join('、')}
          </Typography.Text>
        ) : null}
      </Card>

      {canWrite && suggestion.status === 'PENDING' ? (
        <Space>
          <Button
            type="primary"
            loading={decideMutation.isPending}
            onClick={() =>
              decideMutation.mutate({ id: suggestion.id, status: 'ACCEPTED', reason: null })
            }
          >
            采纳这份菜单
          </Button>
          <Button danger onClick={() => setRejecting(true)}>
            否决
          </Button>
        </Space>
      ) : null}

      {suggestion.status === 'REJECTED' && suggestion.rejected_reason ? (
        <Alert
          type="info"
          showIcon
          message={`否决原因：${suggestion.rejected_reason}`}
          description="它会被用来改进后续推荐。"
        />
      ) : null}

      <Modal
        open={rejecting}
        title="否决这份建议"
        okText="确认否决"
        cancelText="取消"
        onCancel={() => setRejecting(false)}
        onOk={() => {
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
    </Space>
  );
}
