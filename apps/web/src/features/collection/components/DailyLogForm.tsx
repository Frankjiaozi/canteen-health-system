import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { useSaveSheet } from '../hooks/useCollection';
import {
  buildSavePayload,
  initialFormValues,
  initialRows,
  validateSheet,
  type SheetFormValues,
  type SheetRow,
} from '../lib/sheet';
import type { DailyLogSheet, MealType } from '../types';

interface DailyLogFormProps {
  onDate: string;
  sheet: DailyLogSheet;
}

/**
 * 采集单主体。
 *
 * 由父组件在拿到数据之后挂载、切换日期时卸载重建，初始值直接来自 props——
 * 与菜品配方抽屉同一套做法，省掉 effect 里同步表单状态的那一次级联渲染。
 */
export function DailyLogForm({ onDate, sheet }: DailyLogFormProps) {
  const [form] = Form.useForm<SheetFormValues>();
  const [rows, setRows] = useState<SheetRow[]>(() => initialRows(sheet));
  const { data: user } = useCurrentUser();
  const { data: enumOptions } = useEnumOptions();
  const saveMutation = useSaveSheet(onDate, sheet.meal_type);
  const canWrite = canWriteBusinessData(user);

  const patchRow = (dishId: string, patch: Partial<SheetRow>) => {
    setRows((current) =>
      current.map((row) => (row.dishId === dishId ? { ...row, ...patch } : row)),
    );
  };

  const handleSubmit = async () => {
    let values: SheetFormValues;
    try {
      values = await form.validateFields();
    } catch {
      // 校验不通过时 AntD 已经把错误渲染在对应字段下面了，这里不必再提示一遍
      return;
    }
    const problem = validateSheet(values, rows);
    if (problem) {
      // 校验失败不静默：直接在表单顶部给出能照做的提示
      void saveMutation.reset();
      form.setFields([{ name: 'dinerCount', errors: [problem] }]);
      return;
    }
    try {
      await saveMutation.mutateAsync(buildSavePayload(values, rows));
    } catch {
      // 失败提示与「存入本地队列」都在 mutation 的 onError 里完成；
      // 这里只是别让这个 rejection 漏到控制台，看着像出了别的问题
    }
  };

  const selectedCount = rows.filter((row) => row.selected).length;

  return (
    <Form<SheetFormValues>
      form={form}
      layout="vertical"
      initialValues={initialFormValues(sheet)}
      disabled={!canWrite}
    >
      <Card
        size="small"
        title={`当日总量（${sheet.meal_type_label}）`}
        style={{ marginBottom: 16 }}
      >
        <Space size={24} wrap align="start">
          <Form.Item
            name="dinerCount"
            label="就餐人次"
            rules={[{ required: true, message: '请填写就餐人次' }]}
            style={{ marginBottom: 0 }}
          >
            <InputNumber min={1} precision={0} style={{ width: 140 }} addonAfter="人次" />
          </Form.Item>
          <Form.Item name="oilTotalG" label="食用油" style={{ marginBottom: 0 }}>
            <InputNumber min={0} precision={2} style={{ width: 150 }} addonAfter="克" />
          </Form.Item>
          <Form.Item name="saltTotalG" label="食盐" style={{ marginBottom: 0 }}>
            <InputNumber min={0} precision={2} style={{ width: 150 }} addonAfter="克" />
          </Form.Item>
          <Form.Item name="sugarTotalG" label="添加糖" style={{ marginBottom: 0 }}>
            <InputNumber min={0} precision={2} style={{ width: 150 }} addonAfter="克" />
          </Form.Item>
          <Form.Item name="leftoverWeightG" label="剩餐总重" style={{ marginBottom: 0 }}>
            <InputNumber min={0} precision={2} style={{ width: 150 }} addonAfter="克" />
          </Form.Item>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          油、盐、糖是校准模型的关键输入，按当日实际投放量填到克；其余靠配方推导。
        </Typography.Paragraph>
      </Card>

      <Card
        size="small"
        title={`当日供应的菜品（已勾选 ${selectedCount} 道）`}
        extra={<Typography.Text type="secondary">勾选即写入当天菜单日</Typography.Text>}
        style={{ marginBottom: 16 }}
      >
        {sheet.warning ? (
          <Typography.Paragraph type="warning" style={{ marginTop: 0 }}>
            {sheet.warning}
          </Typography.Paragraph>
        ) : null}
        <Table<SheetRow>
          rowKey="dishId"
          size="small"
          pagination={false}
          scroll={{ y: 320 }}
          dataSource={rows}
          columns={[
            {
              title: '供应',
              width: 70,
              align: 'center',
              render: (_, row) => (
                <input
                  type="checkbox"
                  aria-label={`供应-${row.dishId}`}
                  checked={row.selected}
                  disabled={!canWrite}
                  onChange={(event) => patchRow(row.dishId, { selected: event.target.checked })}
                />
              ),
            },
            {
              title: '菜品',
              width: 200,
              render: (_, row) => {
                const dish = sheet.dishes.find((item) => item.dish_id === row.dishId);
                return (
                  <Space orientation="vertical" size={0}>
                    <Typography.Text strong>{dish?.name}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {dish?.category_label} · {dish?.cooking_method_label}
                    </Typography.Text>
                  </Space>
                );
              },
            },
            {
              title: '折算能量（单份）',
              width: 160,
              align: 'right',
              render: (_, row) => {
                const dish = sheet.dishes.find((item) => item.dish_id === row.dishId);
                if (!dish?.energy_kcal)
                  return <Typography.Text type="secondary">—</Typography.Text>;
                return (
                  <Space orientation="vertical" size={0} style={{ textAlign: 'right' }}>
                    <Typography.Text>{Number(dish.energy_kcal).toFixed(1)} 千卡</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {dish.nutrition_source}
                    </Typography.Text>
                  </Space>
                );
              },
            },
            {
              title: '出餐份数',
              width: 150,
              render: (_, row) => (
                <InputNumber
                  min={0}
                  precision={2}
                  style={{ width: '100%' }}
                  value={row.servings}
                  disabled={!canWrite || !row.selected}
                  onChange={(value) => patchRow(row.dishId, { servings: value ?? null })}
                />
              ),
            },
            {
              title: '剩余比例',
              width: 150,
              render: (_, row) => (
                <InputNumber
                  min={0}
                  max={1}
                  step={0.01}
                  precision={4}
                  style={{ width: '100%' }}
                  value={row.leftoverRatio}
                  disabled={!canWrite || !row.selected}
                  onChange={(value) => patchRow(row.dishId, { leftoverRatio: value ?? null })}
                />
              ),
            },
            {
              title: '临时替换',
              width: 110,
              align: 'center',
              render: (_, row) => (
                <input
                  type="checkbox"
                  aria-label={`临时替换-${row.dishId}`}
                  checked={row.isSubstituted}
                  disabled={!canWrite || !row.selected}
                  onChange={(event) =>
                    patchRow(row.dishId, { isSubstituted: event.target.checked })
                  }
                />
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" title="异常与备注" style={{ marginBottom: 16 }}>
        <Space size={24} wrap align="start">
          <Form.Item
            name="anomalyFlags"
            label="特殊情况"
            extra="标了异常的日子不参与预测的历史序列"
            style={{ marginBottom: 0, minWidth: 320 }}
          >
            <Select
              mode="multiple"
              allowClear
              placeholder="当天无异常"
              options={(enumOptions?.manual_anomaly_flag ?? []).map((option) => ({
                value: option.value,
                label: option.label,
              }))}
            />
          </Form.Item>
          <Form.Item name="note" label="备注" style={{ marginBottom: 0, minWidth: 320 }}>
            <Input maxLength={255} placeholder="例如：临时接待某班级" style={{ width: 320 }} />
          </Form.Item>
        </Space>
        {sheet.anomaly_flags.some((flag) => flag.system) ? (
          <div style={{ marginTop: 12 }}>
            <Typography.Text type="secondary">系统判定：</Typography.Text>{' '}
            {sheet.anomaly_flags
              .filter((flag) => flag.system)
              .map((flag) => (
                <Tag key={flag.value} color="orange">
                  {flag.label}
                </Tag>
              ))}
            <Typography.Text type="secondary">
              （由校准校验写入，把用量改对之后重跑校准会自动撤掉）
            </Typography.Text>
          </div>
        ) : null}
      </Card>

      {canWrite ? (
        <Space>
          <Button
            type="primary"
            loading={saveMutation.isPending}
            onClick={() => void handleSubmit()}
          >
            保存并重算营养
          </Button>
          {sheet.submitted_at ? (
            <Typography.Text type="secondary">
              上次保存：{new Date(sheet.submitted_at).toLocaleString('zh-CN')}
            </Typography.Text>
          ) : null}
        </Space>
      ) : (
        <Typography.Text type="secondary">
          学校管理方是只读的观察者，采集由食堂录入员或管理员填写。
        </Typography.Text>
      )}
    </Form>
  );
}

export type { MealType };
