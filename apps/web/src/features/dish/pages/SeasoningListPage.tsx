import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { TableProps } from 'antd';
import { useEffect, useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { formatNutrient } from '@/features/ingredient/lib/query';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { PagePanel } from '@/shared/components/PagePanel';
import {
  useCreateSeasoning,
  useDeactivateSeasoning,
  useSeasoningList,
  useUpdateSeasoning,
} from '../hooks/useDishes';
import { NUTRIENT_COLUMNS } from '@/shared/config/nutrients';
import type { Seasoning, SeasoningCategory } from '../types';

interface SeasoningFormValues {
  name: string;
  category: SeasoningCategory;
  unit: string;
  energy_kcal: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
  sodium_mg: number | null;
  unit_price: number | null;
  data_source: string | null;
  source_version: string | null;
  note: string | null;
}

/**
 * 数值转字符串时固定小数位，避免 25.5 与 25.50 两种写法混进库里。
 *
 * 表单里没填过的数字字段给到的是 `undefined` 而不是 `null`：漏判它会在
 * 「只填了名称与类别」这种最常见的用法上直接抛异常，整条提交静默失败。
 */
function toDecimalString(value: number | null | undefined, digits: number): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null;
  }
  return value.toFixed(digits);
}

export function SeasoningListPage() {
  const { data: user } = useCurrentUser();
  const { data: enumOptions } = useEnumOptions();
  const canWrite = canWriteBusinessData(user);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editing, setEditing] = useState<Seasoning | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [form] = Form.useForm<SeasoningFormValues>();
  const listQuery = useSeasoningList({ page, pageSize, keyword, includeInactive });
  const createMutation = useCreateSeasoning();
  const updateMutation = useUpdateSeasoning();
  const deactivateMutation = useDeactivateSeasoning();

  useEffect(() => {
    if (!drawerOpen) return;
    if (editing) {
      form.setFieldsValue({
        name: editing.name,
        category: editing.category,
        unit: editing.unit,
        energy_kcal: Number(editing.energy_kcal ?? 0),
        protein_g: Number(editing.protein_g ?? 0),
        fat_g: Number(editing.fat_g ?? 0),
        carb_g: Number(editing.carb_g ?? 0),
        sodium_mg: Number(editing.sodium_mg ?? 0),
        unit_price: editing.unit_price === null ? null : Number(editing.unit_price),
        data_source: editing.data_source,
        source_version: editing.source_version,
        note: editing.note,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ unit: 'g' });
    }
  }, [drawerOpen, editing, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = {
      name: values.name.trim(),
      category: values.category,
      unit: values.unit || 'g',
      energy_kcal: toDecimalString(values.energy_kcal, 2),
      protein_g: toDecimalString(values.protein_g, 3),
      fat_g: toDecimalString(values.fat_g, 3),
      carb_g: toDecimalString(values.carb_g, 3),
      sodium_mg: toDecimalString(values.sodium_mg, 2),
      unit_price: toDecimalString(values.unit_price, 2),
      data_source: values.data_source?.trim() || null,
      source_version: values.source_version?.trim() || null,
      note: values.note?.trim() || null,
    };
    try {
      if (editing) {
        await updateMutation.mutateAsync({ id: editing.id, payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      setDrawerOpen(false);
    } catch {
      // 提示已由 mutation 统一处理
    }
  };

  const columns: TableProps<Seasoning>['columns'] = [
    {
      title: '调味料',
      dataIndex: 'name',
      width: 140,
      render: (name: string, record) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{name}</Typography.Text>
          {record.is_active ? null : <Tag>已停用</Tag>}
        </Space>
      ),
    },
    { title: '类别', dataIndex: 'category_label', width: 96 },
    ...NUTRIENT_COLUMNS.map((column) => ({
      title: `${column.title}（${column.unit}/100克）`,
      dataIndex: column.field,
      width: 124,
      align: 'right' as const,
      render: (value: string | null) => formatNutrient(value, column.digits),
    })),
    {
      title: '数据来源',
      dataIndex: 'data_source',
      width: 150,
      // 与食材库同一处理：单元格里放逐行不同的「条目名 + 条目 ID」，
      // 来源全称放进悬停提示——它每行都一样，占着地方反而把名称列挤扁
      ellipsis: { showTitle: false },
      render: (value: string | null, record) => {
        if (!value) {
          return <Typography.Text type="secondary">—</Typography.Text>;
        }
        const entry = record.source_version ?? value;
        const full = record.source_version ? `${value}（${record.source_version}）` : value;
        return (
          <Tooltip title={full} placement="topLeft">
            <Typography.Text type="secondary">{entry}</Typography.Text>
          </Tooltip>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) =>
        canWrite && record.is_active ? (
          <Space size={4}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setEditing(record);
                setDrawerOpen(true);
              }}
            >
              编辑
            </Button>
            <Popconfirm
              title="停用该调味料？"
              description="历史配方与营养结果会保留。"
              okText="停用"
              cancelText="取消"
              onConfirm={() => void deactivateMutation.mutateAsync(record.id)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                停用
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
  ];

  return (
    <PagePanel
      filters={
        <>
          <Input.Search
            allowClear
            placeholder="按名称搜索"
            style={{ width: 240 }}
            onSearch={(value) => {
              setKeyword(value);
              setPage(1);
            }}
          />
          <Space size={6}>
            <Switch
              size="small"
              checked={includeInactive}
              onChange={(checked) => {
                setIncludeInactive(checked);
                setPage(1);
              }}
            />
            <Typography.Text type="secondary">包含已停用</Typography.Text>
          </Space>
        </>
      }
      actions={
        <>
          <span className="zw-page-toolbar-meta">共 {listQuery.data?.total ?? 0} 种</span>
          {canWrite ? (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditing(null);
                setDrawerOpen(true);
              }}
            >
              新增调味料
            </Button>
          ) : null}
        </>
      }
    >
      <Table<Seasoning>
        rowKey="id"
        size="small"
        loading={listQuery.isFetching}
        columns={columns}
        dataSource={listQuery.data?.items ?? []}
        scroll={{ x: 1166 }}
        pagination={{
          current: page,
          pageSize,
          total: listQuery.data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage);
            setPageSize(nextPageSize);
          },
        }}
      />

      <Drawer
        title={editing ? `编辑调味料：${editing.name}` : '新增调味料'}
        open={drawerOpen}
        size={520}
        onClose={() => setDrawerOpen(false)}
        destroyOnHidden
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              loading={createMutation.isPending || updateMutation.isPending}
              onClick={() => void handleSubmit()}
            >
              {editing ? '保存' : '新增'}
            </Button>
          </Space>
        }
      >
        <Form<SeasoningFormValues> form={form} layout="vertical" requiredMark={false}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：大豆油" />
          </Form.Item>
          <Form.Item
            name="category"
            label="类别"
            rules={[{ required: true, message: '请选择类别' }]}
          >
            <Select
              placeholder="请选择"
              options={(enumOptions?.seasoning_category ?? []).map((option) => ({
                value: option.value,
                label: option.label,
              }))}
            />
          </Form.Item>
          <Form.Item name="unit" label="计量单位">
            <Input placeholder="g" />
          </Form.Item>
          <Form.Item name="energy_kcal" label="能量（千卡/100 克）">
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="protein_g" label="蛋白质（克/100 克）">
            <InputNumber min={0} precision={3} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="fat_g" label="脂肪（克/100 克）">
            <InputNumber min={0} precision={3} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="carb_g" label="碳水化合物（克/100 克）">
            <InputNumber min={0} precision={3} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="sodium_mg"
            label="钠（毫克/100 克）"
            tooltip="食盐的钠含量约 39311 毫克/100 克，它是校准模型的锚点"
          >
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="unit_price" label="单价（元/公斤，按市品）">
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="data_source" label="数据来源">
            <Input placeholder="例如：中国食物成分表·食物营养成分查询平台" />
          </Form.Item>
          <Form.Item
            name="source_version"
            label="来源版本"
            tooltip="写清是哪一条：条目名 + 条目 ID。只写「查过成分表」等于没写。"
          >
            <Input placeholder="例如：豆油 · 条目 1497" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} maxLength={255} />
          </Form.Item>
        </Form>
      </Drawer>
    </PagePanel>
  );
}
