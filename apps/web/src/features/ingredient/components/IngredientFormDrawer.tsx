import { Button, Drawer, Form, Input, InputNumber, Select, Space, Typography } from 'antd';
import { useEffect } from 'react';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { useCreateIngredient, useUpdateIngredient } from '../hooks/useIngredients';
import { percentToRatio, ratioToPercent } from '../lib/query';
import { NUTRIENT_COLUMNS, type Ingredient, type IngredientCategory } from '../types';

interface IngredientFormDrawerProps {
  open: boolean;
  /** 为空表示新增 */
  ingredient: Ingredient | null;
  onClose: () => void;
}

interface FormValues {
  name: string;
  category: IngredientCategory;
  energy_kcal: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
  sodium_mg: number | null;
  edible_ratio_percent: number;
  unit_price: number | null;
  data_source: string;
  source_version: string | null;
  note: string | null;
}

/** 数值转字符串时固定小数位，避免 25.5 与 25.50 两种写法混进库里。 */
function toDecimalString(value: number | null | undefined, digits: number): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null;
  }
  return value.toFixed(digits);
}

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function IngredientFormDrawer({ open, ingredient, onClose }: IngredientFormDrawerProps) {
  const [form] = Form.useForm<FormValues>();
  const { data: enumOptions } = useEnumOptions();
  const createMutation = useCreateIngredient();
  const updateMutation = useUpdateIngredient();
  const isEditing = ingredient !== null;
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (!open) return;
    if (ingredient) {
      form.setFieldsValue({
        name: ingredient.name,
        category: ingredient.category,
        energy_kcal: toNumber(ingredient.energy_kcal),
        protein_g: toNumber(ingredient.protein_g),
        fat_g: toNumber(ingredient.fat_g),
        carb_g: toNumber(ingredient.carb_g),
        sodium_mg: toNumber(ingredient.sodium_mg),
        edible_ratio_percent: ratioToPercent(ingredient.edible_ratio) ?? 100,
        unit_price: toNumber(ingredient.unit_price),
        data_source: ingredient.data_source,
        source_version: ingredient.source_version,
        note: ingredient.note,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ edible_ratio_percent: 100 });
    }
  }, [form, ingredient, open]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = {
      name: values.name.trim(),
      category: values.category,
      energy_kcal: toDecimalString(values.energy_kcal, 2),
      protein_g: toDecimalString(values.protein_g, 3),
      fat_g: toDecimalString(values.fat_g, 3),
      carb_g: toDecimalString(values.carb_g, 3),
      sodium_mg: toDecimalString(values.sodium_mg, 2),
      edible_ratio: percentToRatio(values.edible_ratio_percent) ?? '1.0000',
      unit_price: toDecimalString(values.unit_price, 2),
      data_source: values.data_source.trim(),
      source_version: values.source_version?.trim() || null,
      note: values.note?.trim() || null,
    };

    try {
      if (isEditing && ingredient) {
        await updateMutation.mutateAsync({ id: ingredient.id, payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onClose();
    } catch {
      // 失败提示已由 mutation 的 onError 统一处理，这里只需要保持抽屉打开
    }
  };

  return (
    <Drawer
      title={isEditing ? `编辑食材：${ingredient?.name}` : '新增食材'}
      open={open}
      size={520}
      onClose={onClose}
      destroyOnHidden
      footer={
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>
            {isEditing ? '保存' : '新增'}
          </Button>
        </Space>
      }
    >
      <Form<FormValues> form={form} layout="vertical" requiredMark={false}>
        <Form.Item
          name="name"
          label="食材名称"
          rules={[
            { required: true, message: '请输入食材名称' },
            { max: 64, message: '名称不能超过 64 个字符' },
          ]}
        >
          <Input placeholder="例如：西兰花" />
        </Form.Item>

        <Form.Item name="category" label="类别" rules={[{ required: true, message: '请选择类别' }]}>
          <Select
            placeholder="请选择"
            options={(enumOptions?.ingredient_category ?? []).map((option) => ({
              value: option.value,
              label: option.label,
            }))}
          />
        </Form.Item>

        <Typography.Paragraph type="secondary" style={{ marginTop: -8 }}>
          营养成分按每 100 克可食部填写；成分表里缺项的留空即可，不要填 0。
        </Typography.Paragraph>

        {NUTRIENT_COLUMNS.map((column) => (
          <Form.Item
            key={column.field}
            name={column.field}
            label={`${column.title}（${column.unit}/100 克）`}
          >
            <InputNumber
              min={0}
              precision={column.digits}
              style={{ width: '100%' }}
              placeholder="留空表示数据缺失"
            />
          </Form.Item>
        ))}

        <Form.Item
          name="edible_ratio_percent"
          label="可食部比例（%）"
          rules={[{ required: true, message: '请输入可食部比例' }]}
          tooltip="食材中可食用部分所占的比例，例如鸡蛋约 85%"
        >
          <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item name="unit_price" label="单价（元/公斤，按市品）">
          <InputNumber min={0} precision={2} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name="data_source"
          label="数据来源"
          rules={[{ required: true, message: '营养数据必须标注来源' }]}
          tooltip="任何营养数据都要能点开看到来源，这一条是硬性要求"
        >
          <Input placeholder="例如：《中国食物成分表（标准版第 6 版）》" />
        </Form.Item>

        <Form.Item name="source_version" label="来源版本">
          <Input placeholder="例如：6 版" />
        </Form.Item>

        <Form.Item name="note" label="备注">
          <Input.TextArea rows={2} maxLength={255} />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
