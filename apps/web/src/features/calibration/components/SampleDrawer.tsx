import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Table,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useSubmitSample } from '../hooks/useCalibration';
import {
  NUTRIENT_ROWS,
  defaultMeasured,
  deviationOf,
  formatRatio,
  type NutrientField,
} from '../lib/compare';
import type { MealType, SamplingCandidate } from '../types';

interface SampleDrawerProps {
  candidate: SamplingCandidate;
  onDate: string;
  mealType: MealType;
  onClose: () => void;
}

interface SampleFormValues extends Record<NutrientField, number | null> {
  scope: 'DISH' | 'COOKING_METHOD';
  note: string | null;
}

/**
 * 抽样称重录入。
 *
 * 默认带出推算值，录入员只改动实际称出来不一样的那几项——这是「每周称三五道菜」
 * 这件事能不能坚持下去的关键：多数菜多数指标都是对的，从零开始填反而更容易放弃。
 */
export function SampleDrawer({ candidate, onDate, mealType, onClose }: SampleDrawerProps) {
  const [form] = Form.useForm<SampleFormValues>();
  const submitMutation = useSubmitSample();
  const [measured, setMeasured] = useState(() => defaultMeasured(candidate));
  const baseline = candidate.calibrated ?? candidate.theoretical;

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const filled = NUTRIENT_ROWS.some((row) => values[row.field] !== null);
    if (!filled) return;

    await submitMutation.mutateAsync({
      dish_id: candidate.dish_id,
      date: onDate,
      meal_type: mealType,
      measured_energy_kcal: String(values.energy_kcal ?? 0),
      measured_protein_g: String(values.protein_g ?? 0),
      measured_fat_g: String(values.fat_g ?? 0),
      measured_carb_g: String(values.carb_g ?? 0),
      measured_sodium_mg: String(values.sodium_mg ?? 0),
      scope: values.scope,
      note: values.note,
    });
    onClose();
  };

  return (
    <Drawer
      open
      size={760}
      title={`抽样称重 · ${candidate.dish_name}`}
      onClose={onClose}
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={submitMutation.isPending}
            onClick={() => void handleSubmit()}
          >
            提交实测
          </Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="食材按配方称重是可信的，差额全部归给调味料"
        description="系统用「(实测能量 − 食材能量) ÷ 配方调味料能量」反推调味料该乘多少。实测值与推算值差距过大时不会硬套系数，只留证据并提示核对配方。"
      />

      <Form<SampleFormValues>
        form={form}
        layout="vertical"
        initialValues={{ ...defaultMeasured(candidate), scope: 'DISH', note: null }}
        onValuesChange={(changed) => {
          for (const row of NUTRIENT_ROWS) {
            if (row.field in changed) {
              setMeasured((current) => ({ ...current, [row.field]: changed[row.field] }));
            }
          }
        }}
      >
        <Table
          size="small"
          pagination={false}
          rowKey="field"
          dataSource={NUTRIENT_ROWS.map((row) => ({ ...row }))}
          columns={[
            { title: '指标', dataIndex: 'label', width: 110 },
            { title: '单位', dataIndex: 'unit', width: 70 },
            {
              title: '推算值',
              width: 120,
              align: 'right',
              render: (_, row) => (
                <Typography.Text type="secondary">
                  {baseline ? Number(baseline[row.field]).toFixed(row.digits) : '—'}
                </Typography.Text>
              ),
            },
            {
              title: '实测（单份）',
              width: 180,
              render: (_, row) => (
                <Form.Item name={row.field} style={{ margin: 0 }}>
                  <InputNumber min={0} precision={row.digits} style={{ width: '100%' }} />
                </Form.Item>
              ),
            },
            {
              title: '偏差',
              width: 90,
              align: 'right',
              render: (_, row) => {
                const value = measured[row.field];
                if (value === null || !baseline) {
                  return <Typography.Text type="secondary">—</Typography.Text>;
                }
                const deviation = deviationOf(String(value), baseline[row.field]);
                return (
                  <Typography.Text type={deviation.notable ? 'danger' : 'secondary'}>
                    {formatRatio(deviation.ratio)}
                  </Typography.Text>
                );
              },
            },
          ]}
        />

        <Form.Item
          label="修正范围"
          name="scope"
          extra="称的是哪一道菜就改哪一道；同一类做法普遍偏，才选整类烹饪方式"
          style={{ marginTop: 16 }}
        >
          <Radio.Group
            optionType="button"
            buttonStyle="solid"
            options={[
              { value: 'DISH', label: `只改「${candidate.dish_name}」` },
              { value: 'COOKING_METHOD', label: `改整类「${candidate.cooking_method_label}」` },
            ]}
          />
        </Form.Item>
        <Form.Item label="备注" name="note">
          <Input maxLength={255} placeholder="例如：称的是出锅后静置 5 分钟的一整份" />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
