import {
  AppstoreOutlined,
  UnorderedListOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  Button,
  Grid,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Segmented,
  Pagination,
  Empty,
  Skeleton,
} from 'antd';
import type { TableProps } from 'antd';
import { useState } from 'react';
import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { PagePanel } from '@/shared/components/PagePanel';
import { SoftCard } from '@/shared/components/SoftCard';
import { DishImage } from '../components/DishImage';
import '../dish.css';
import { DishFormDrawer } from '../components/DishFormDrawer';
import { ImportDrawer } from '../components/ImportDrawer';
import { useDeactivateDish, useDishDetail, useDishList } from '../hooks/useDishes';
import { defaultDishImageUrl } from '../lib/defaultImage';
import { formatNutrient } from '@/features/ingredient/lib/query';
import type { Dish, DishCategory } from '../types';

export function DishListPage() {
  const { data: user } = useCurrentUser();
  const { data: enumOptions } = useEnumOptions();
  const screens = Grid.useBreakpoint();
  const isPhone = screens.md === false;
  const canWrite = canWriteBusinessData(user);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [view, setView] = useState('cards');
  const [keyword, setKeyword] = useState('');
  const [category, setCategory] = useState<DishCategory | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingSection, setEditingSection] = useState('basic');
  const [importOpen, setImportOpen] = useState(false);

  const listQuery = useDishList({ page, pageSize, keyword, category, includeInactive });
  const detailQuery = useDishDetail(drawerOpen ? editingId : null);
  const deactivateMutation = useDeactivateDish();

  const openCreate = () => {
    setEditingSection('basic');
    setEditingId(null);
    setDrawerOpen(true);
  };

  const openEdit = (dish: Dish, section = 'basic') => {
    setEditingSection(section);
    setEditingId(dish.id);
    setDrawerOpen(true);
  };

  const columns: TableProps<Dish>['columns'] = [
    {
      title: '菜品',
      dataIndex: 'name',
      fixed: isPhone ? undefined : 'left',
      width: isPhone ? 150 : 160,
      render: (name: string, record) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{name}</Typography.Text>
          <Space size={4}>
            {record.is_active ? null : <Tag>已停用</Tag>}
            {record.nutrition === null ? <Tag color="warning">无配方</Tag> : null}
            {/* 早餐固定供应不属于「午晚餐轮换」，不标出来会被当成漏排 */}
            {record.is_breakfast_staple ? <Tag className="zw-tag-sage">早餐固定</Tag> : null}
            <Tag>配方 v{record.recipe_version}</Tag>
          </Space>
        </Space>
      ),
    },
    { title: '类别', dataIndex: 'category_label', width: isPhone ? 80 : 90 },
    {
      title: '烹饪',
      dataIndex: 'cooking_method_label',
      width: 80,
      responsive: ['md'],
    },
    {
      title: '标准份量（克）',
      dataIndex: 'standard_serving_g',
      width: 120,
      align: 'right',
      responsive: ['md'],
    },
    {
      title: '单份能量（千卡）',
      key: 'energy',
      width: 130,
      align: 'right',
      responsive: ['md'],
      render: (_, record) => formatNutrient(record.nutrition?.energy_kcal, 2),
    },
    {
      title: '单份蛋白质（克）',
      key: 'protein',
      width: 130,
      align: 'right',
      responsive: ['md'],
      render: (_, record) => formatNutrient(record.nutrition?.protein_g, 3),
    },
    {
      title: '单份钠（毫克）',
      key: 'sodium',
      width: 130,
      align: 'right',
      responsive: ['md'],
      render: (_, record) => formatNutrient(record.nutrition?.sodium_mg, 2),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: isPhone ? undefined : 'right',
      width: isPhone ? 110 : 160,
      render: (_, record) =>
        canWrite && record.is_active ? (
          <Space size={isPhone ? 0 : 4}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              title="编辑"
              aria-label="编辑"
              onClick={() => openEdit(record)}
            >
              {isPhone ? null : '编辑'}
            </Button>
            <Popconfirm
              title="停用该菜品？"
              description="历史菜单里的记录与营养结果会保留。"
              okText="停用"
              cancelText="取消"
              onConfirm={() => void deactivateMutation.mutateAsync(record.id)}
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                title="停用"
                aria-label="停用"
              >
                {isPhone ? null : '停用'}
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
        </>
      }
      actions={
        <>
          <Segmented
            aria-label="菜品展示方式"
            value={view}
            onChange={setView}
            options={[
              { value: 'cards', label: '卡片', icon: <AppstoreOutlined /> },
              { value: 'list', label: '列表', icon: <UnorderedListOutlined /> },
            ]}
          />
          <span className="zw-page-toolbar-meta">共 {listQuery.data?.total ?? 0} 道</span>
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
        </>
      }
    >
      {view === 'cards' ? (
        <div className="zw-dish-gallery-wrap">
          {listQuery.isPending ? (
            <Skeleton active />
          ) : listQuery.isError ? (
            <Empty description="菜品读取失败">
              <Button onClick={() => void listQuery.refetch()}>重新加载</Button>
            </Empty>
          ) : !listQuery.data?.items.length ? (
            <Empty description="暂无符合条件的菜品" />
          ) : (
            <div className="zw-dish-gallery">
              {listQuery.data.items.map((dish) => (
                <SoftCard className="zw-dish-card" key={dish.id}>
                  <div className="zw-dish-card-visual">
                    <DishImage url={dish.image_url} name={dish.name} />
                    {canWrite && dish.is_active && (
                      <Button
                        type="text"
                        size="small"
                        icon={<UploadOutlined />}
                        onClick={() => openEdit(dish, 'image')}
                      >
                        {dish.image_url || defaultDishImageUrl(dish.name) ? '更换图片' : '上传图片'}
                      </Button>
                    )}
                  </div>
                  <div className="zw-dish-card-copy">
                    <div className="zw-dish-card-heading">
                      <h2>{dish.name}</h2>
                      {!dish.is_active && <Tag>已停用</Tag>}
                    </div>
                    <Space size={4} wrap>
                      <Tag className="zw-tag-sage">{dish.category_label}</Tag>
                      <Tag>{dish.cooking_method_label}</Tag>
                      {dish.is_breakfast_staple && <Tag>早餐固定</Tag>}
                    </Space>
                    <dl className="zw-dish-facts">
                      <div>
                        <dt>标准份量</dt>
                        <dd>
                          {formatNutrient(dish.standard_serving_g, 0)} <small>克</small>
                        </dd>
                      </div>
                      <div>
                        <dt>单份能量</dt>
                        <dd>
                          {formatNutrient(dish.nutrition?.energy_kcal, 1)} <small>千卡</small>
                        </dd>
                      </div>
                      <div>
                        <dt>配方版本</dt>
                        <dd>v{dish.recipe_version}</dd>
                      </div>
                    </dl>
                    <footer>
                      <span>{dish.nutrition ? '已有标准配方' : '待完善配方'}</span>
                      {canWrite && dish.is_active && (
                        <Space size={2}>
                          <Button
                            type="text"
                            icon={<EditOutlined />}
                            onClick={() => openEdit(dish)}
                          >
                            编辑
                          </Button>
                          <Popconfirm
                            title="停用该菜品？"
                            description="历史菜单里的记录与营养结果会保留。"
                            onConfirm={() => void deactivateMutation.mutateAsync(dish.id)}
                          >
                            <Button
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              aria-label={`停用${dish.name}`}
                            />
                          </Popconfirm>
                        </Space>
                      )}
                    </footer>
                  </div>
                </SoftCard>
              ))}
            </div>
          )}
          <Pagination
            current={page}
            pageSize={pageSize}
            total={listQuery.data?.total ?? 0}
            showSizeChanger
            pageSizeOptions={[12, 24, 48]}
            showTotal={(total) => `共 ${total} 道菜品`}
            onChange={(next, size) => {
              setPage(next);
              setPageSize(size);
            }}
          />
        </div>
      ) : (
        <Table<Dish>
          rowKey="id"
          size="small"
          loading={listQuery.isFetching}
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          scroll={isPhone ? undefined : { x: 1000 }}
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
      )}

      {drawerOpen && (editingId === null || detailQuery.data !== undefined) ? (
        <DishFormDrawer
          // 换菜品时用 key 强制重建，让表单拿到新的初始值
          key={editingId ?? 'new'}
          dish={detailQuery.data ?? null}
          initialSection={editingSection}
          onClose={() => setDrawerOpen(false)}
        />
      ) : null}
      <ImportDrawer open={importOpen} onClose={() => setImportOpen(false)} />
    </PagePanel>
  );
}
