import { DeleteOutlined, EditOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
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
  Typography,
} from 'antd';
import type { TableProps } from 'antd';
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { DishFormDrawer } from '../components/DishFormDrawer';
import { ImportDrawer } from '../components/ImportDrawer';
import { useDeactivateDish, useDishDetail, useDishList } from '../hooks/useDishes';
import { formatNutrient } from '@/features/ingredient/lib/query';
import type { Dish, DishCategory } from '../types';

export function DishListPage() {
  const { data: user } = useCurrentUser();
  const { data: enumOptions } = useEnumOptions();
  const canWrite = canWriteBusinessData(user);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');
  const [category, setCategory] = useState<DishCategory | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const listQuery = useDishList({ page, pageSize, keyword, category, includeInactive });
  const detailQuery = useDishDetail(drawerOpen ? editingId : null);
  const deactivateMutation = useDeactivateDish();

  const openCreate = () => {
    setEditingId(null);
    setDrawerOpen(true);
  };

  const openEdit = (dish: Dish) => {
    setEditingId(dish.id);
    setDrawerOpen(true);
  };

  const columns: TableProps<Dish>['columns'] = [
    {
      title: '菜品',
      dataIndex: 'name',
      fixed: 'left',
      width: 160,
      render: (name: string, record) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{name}</Typography.Text>
          <Space size={4}>
            {record.is_active ? null : <Tag>已停用</Tag>}
            {record.nutrition === null ? <Tag color="warning">无配方</Tag> : null}
            {/* 早餐固定供应不属于「午晚餐轮换」，不标出来会被当成漏排 */}
            {record.is_breakfast_staple ? <Tag color="blue">早餐固定</Tag> : null}
            <Tag>配方 v{record.recipe_version}</Tag>
          </Space>
        </Space>
      ),
    },
    { title: '类别', dataIndex: 'category_label', width: 90 },
    { title: '烹饪', dataIndex: 'cooking_method_label', width: 80 },
    {
      title: '标准份量（克）',
      dataIndex: 'standard_serving_g',
      width: 120,
      align: 'right',
    },
    {
      title: '单份能量（千卡）',
      key: 'energy',
      width: 130,
      align: 'right',
      render: (_, record) => formatNutrient(record.nutrition?.energy_kcal, 2),
    },
    {
      title: '单份蛋白质（克）',
      key: 'protein',
      width: 130,
      align: 'right',
      render: (_, record) => formatNutrient(record.nutrition?.protein_g, 3),
    },
    {
      title: '单份钠（毫克）',
      key: 'sodium',
      width: 130,
      align: 'right',
      render: (_, record) => formatNutrient(record.nutrition?.sodium_mg, 2),
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
              title="停用该菜品？"
              description="历史菜单里的记录与营养结果会保留。"
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
      title="菜品与配方"
      extra={
        <Space>
          <Typography.Text type="secondary">共 {listQuery.data?.total ?? 0} 道</Typography.Text>
          {canWrite ? (
            <>
              <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
                批量导入
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                新增菜品
              </Button>
            </>
          ) : null}
        </Space>
      }
    >
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          placeholder="按名称搜索"
          style={{ width: 240 }}
          onSearch={(value) => {
            setKeyword(value);
            setPage(1);
          }}
        />
        <Select<DishCategory>
          allowClear
          placeholder="全部类别"
          style={{ width: 150 }}
          value={category ?? undefined}
          onChange={(value) => {
            setCategory(value ?? null);
            setPage(1);
          }}
          options={(enumOptions?.dish_category ?? []).map((option) => ({
            value: option.value as DishCategory,
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

      <Table<Dish>
        rowKey="id"
        size="small"
        loading={listQuery.isFetching}
        columns={columns}
        dataSource={listQuery.data?.items ?? []}
        scroll={{ x: 1200 }}
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

      {drawerOpen && (editingId === null || detailQuery.data !== undefined) ? (
        <DishFormDrawer
          // 换菜品时用 key 强制重建，让表单拿到新的初始值
          key={editingId ?? 'new'}
          dish={detailQuery.data ?? null}
          onClose={() => setDrawerOpen(false)}
        />
      ) : null}
      <ImportDrawer open={importOpen} onClose={() => setImportOpen(false)} />
    </Card>
  );
}
