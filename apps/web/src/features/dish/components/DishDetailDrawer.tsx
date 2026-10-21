import { Alert, Button, Drawer, Empty, Skeleton, Space, Tag } from 'antd';
import { EditOutlined, UploadOutlined } from '@ant-design/icons';
import { useDishDetail } from '../hooks/useDishes';
import { formatNutrient } from '@/features/ingredient/lib/query';
import { DishImage } from './DishImage';
import { DishNutrition } from './DishNutrition';
import type { DishDetail } from '../types';

export function DishDetailDrawer({
  id,
  canWrite,
  onClose,
  onEdit,
}: {
  id: string;
  canWrite: boolean;
  onClose: () => void;
  onEdit: (dish: DishDetail, section?: string) => void;
}) {
  const query = useDishDetail(id);
  const dish = query.data;
  return (
    <Drawer
      open
      title="菜品详情"
      className="zw-dish-detail-drawer"
      size={760}
      onClose={onClose}
      footer={
        dish && canWrite && dish.is_active ? (
          <Space wrap>
            <Button
              type="primary"
              icon={<EditOutlined aria-hidden />}
              onClick={() => onEdit(dish, 'recipe')}
            >
              编辑配方
            </Button>
            <Button icon={<UploadOutlined aria-hidden />} onClick={() => onEdit(dish, 'image')}>
              {dish.image_url ? '更换图片' : '上传图片'}
            </Button>
          </Space>
        ) : undefined
      }
    >
      {query.isPending ? (
        <Skeleton active />
      ) : query.isError ? (
        <Alert
          type="error"
          showIcon
          title="菜品详情读取失败"
          action={<Button onClick={() => void query.refetch()}>重新加载</Button>}
        />
      ) : dish ? (
        <article className="zw-dish-detail">
          <DishImage url={dish.image_url} name={dish.name} />
          <header>
            <Space wrap size={6}>
              <Tag className="zw-tag-sage">{dish.category_label}</Tag>
              <Tag>{dish.cooking_method_label}</Tag>
              {!dish.is_active && <Tag>已停用</Tag>}
              {dish.is_breakfast_staple && <Tag>早餐固定</Tag>}
            </Space>
            <h2>{dish.name}</h2>
            <p>
              每份 {formatNutrient(dish.standard_serving_g, 0)} 克
              <span>每锅 {formatNutrient(dish.servings_per_pot, 0)} 份</span>
              <span>配方 v{dish.recipe_version}</span>
            </p>
          </header>
          <section>
            <h3>单份营养</h3>
            <DishNutrition nutrition={dish.nutrition} />
            {!dish.nutrition && <p className="zw-dish-muted">配方尚未完成，营养数据待计算。</p>}
          </section>
          <section>
            <h3>
              标准配方 <small>每份用量 · 克</small>
            </h3>
            {!dish.recipe.ingredients.length && !dish.recipe.seasonings.length ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未录入配方" />
            ) : (
              <div className="zw-dish-recipe-columns">
                {[
                  {
                    title: '食材',
                    lines: dish.recipe.ingredients.map((line) => ({
                      id: line.ingredient_id,
                      name: line.ingredient_name,
                      quantity: line.quantity_per_serving_g,
                      active: line.ingredient_active,
                    })),
                  },
                  {
                    title: '调味料',
                    lines: dish.recipe.seasonings.map((line) => ({
                      id: line.seasoning_id,
                      name: line.seasoning_name,
                      quantity: line.quantity_per_serving_g,
                      active: line.seasoning_active,
                    })),
                  },
                ].map((group) => (
                  <div key={group.title}>
                    <h4>{group.title}</h4>
                    <ul>
                      {group.lines.map((line) => (
                        <li key={line.id}>
                          <span>
                            {line.name}
                            {!line.active && <Tag>已停用</Tag>}
                          </span>
                          <strong>
                            {formatNutrient(line.quantity, 2)} <small>克</small>
                          </strong>
                        </li>
                      ))}
                    </ul>
                    {!group.lines.length && <p className="zw-dish-muted">未添加{group.title}</p>}
                  </div>
                ))}
              </div>
            )}
          </section>
          <section>
            <h3>过敏原</h3>
            {dish.allergens?.length ? (
              <Space wrap>
                {dish.allergens.map((name) => (
                  <Tag color="warning" key={name}>
                    {name}
                  </Tag>
                ))}
              </Space>
            ) : (
              <p className="zw-dish-muted">未登记过敏原，请结合实际用料核对。</p>
            )}
          </section>
          <section>
            <h3>菜品说明与制作备注</h3>
            <p className="zw-dish-description">
              {dish.note?.trim() || '尚未填写，可在编辑菜品时补充。'}
            </p>
          </section>
        </article>
      ) : null}
    </Drawer>
  );
}
