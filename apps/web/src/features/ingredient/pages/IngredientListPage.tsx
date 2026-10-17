import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Card,
  Input,
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
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { IngredientFormDrawer } from '../components/IngredientFormDrawer';
import { useDeactivateIngredient, useIngredientList } from '../hooks/useIngredients';
import { formatNutrient, ratioToPercent } from '../lib/query';
import { NUTRIENT_COLUMNS, type Ingredient, type IngredientCategory } from '../types';

export function IngredientListPage() {
  const { data: user } = useCurrentUser();
  const { data: enumOptions } = useEnumOptions();
  const canWrite = canWriteBusinessData(user);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [category, setCategory] = useState<IngredientCategory | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editing, setEditing] = useState<Ingredient | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const listQuery = useIngredientList({ page, pageSize, keyword, category, includeInactive });
  const deactivateMutation = useDeactivateIngredient();

  const openCreate = () => {
    setEditing(null);
    setDrawerOpen(true);
  };

  const openEdit = (ingredient: Ingredient) => {
    setEditing(ingredient);
    setDrawerOpen(true);
  };

  const columns: TableProps<Ingredient>['columns'] = [
    {
      title: '食材',
      dataIndex: 'name',
      fixed: 'left',
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
      title: `${column.title}（${column.unit}）`,
      dataIndex: column.field,
      width: 110,
      align: 'right' as const,
      // 缺数据显示为「—」而不是 0：数据缺失与真的为零是两码事
      render: (value: string | null) => formatNutrient(value, column.digits),
    })),
    {
      title: '可食部',
      dataIndex: 'edible_ratio',
      width: 82,
      align: 'right',
      render: (value: string) => `${ratioToPercent(value) ?? 100}%`,
    },
    {
      title: '数据来源',
      dataIndex: 'data_source',
      width: 168,
      // 表格里只显示**条目名 + 条目 ID**：它逐行不同，是这条数值真正的可追溯坐标；
      // 出版方那 30 多个字的全称每行都一样，塞进单元格只会把列撑爆，
      // 放进悬停提示与编辑抽屉里看就够。
      ellipsis: { showTitle: false },
      render: (value: string, record) => {
        const entry = record.source_version ?? value;
        const full = `${value}${record.source_version ? `（${record.source_version}）` : ''}`;
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
      fixed: 'right',
      width: 140,
      render: (_, record) =>
        canWrite && record.is_active ? (
          <Space size={4}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEdit(record)}
            >
              编辑
            </Button>
            <Popconfirm
              title="停用该食材？"
              description="历史营养结果会保留，但新配方不能再选它。"
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
    <Card
      title="食材库"
      extra={
        <Space>
          <Typography.Text type="secondary">共 {listQuery.data?.total ?? 0} 种</Typography.Text>
          {canWrite ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增食材
            </Button>
          ) : null}
        </Space>
      }
    >
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          placeholder="按名称或数据来源搜索"
          style={{ width: 260 }}
          onSearch={(value) => {
            setKeyword(value);
            setPage(1);
          }}
        />
        <Select<IngredientCategory>
          allowClear
          placeholder="全部类别"
          style={{ width: 160 }}
          value={category ?? undefined}
          onChange={(value) => {
            setCategory(value ?? null);
            setPage(1);
          }}
          options={(enumOptions?.ingredient_category ?? []).map((option) => ({
            value: option.value as IngredientCategory,
            label: option.label,
          }))}
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
      </Space>

      <Table<Ingredient>
        rowKey="id"
        size="small"
        loading={listQuery.isFetching}
        columns={columns}
        dataSource={listQuery.data?.items ?? []}
        scroll={{ x: 1176 }}
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

      <IngredientFormDrawer
        open={drawerOpen}
        ingredient={editing}
        onClose={() => setDrawerOpen(false)}
      />
    </Card>
  );
}
