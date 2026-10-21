import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Typography,
  Tabs,
  App,
  Alert,
  Tag,
} from 'antd';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { DishImageUpload, type DishImageChange } from './DishImageUpload';
import { saveDishImage } from '../api/dishApi';
import { useEnumOptions } from '@/shared/hooks/useEnumOptions';
import { useIngredientList } from '@/features/ingredient/hooks/useIngredients';
import { useSeasoningList } from '../hooks/useDishes';
import { useCreateDish, useSaveRecipe, useUpdateDish } from '../hooks/useDishes';
import type { DishCategory, DishDetail, CookingMethod } from '../types';
import { DishNutrition } from './DishNutrition';

interface DishFormDrawerProps {
  /** 为空表示新增 */
  dish: DishDetail | null;
  onClose: () => void;
  initialSection?: string;
}

interface RecipeLineForm {
  /** 编辑已有配方行时用于区分「食材」与「调味料」 */
  kind: 'ingredient' | 'seasoning';
  targetId: string;
  quantity: number;
  edibleRatioOverride: number | null;
  note: string | null;
}

interface DishFormValues {
  name: string;
  category: DishCategory;
  cookingMethod: CookingMethod;
  standardServingG: number;
  servingsPerPot: number;
  allergenText: string;
  isBreakfastStaple: boolean;
  note: string | null;
  lines: RecipeLineForm[];
}

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function splitAllergens(text: string): string[] {
  return text
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildLines(dish: DishDetail | null): RecipeLineForm[] {
  if (!dish) return [];
  return [
    ...dish.recipe.ingredients.map((line) => ({
      kind: 'ingredient' as const,
      targetId: line.ingredient_id,
      quantity: Number(line.quantity_per_serving_g),
      edibleRatioOverride: toNumber(line.edible_ratio_override),
      note: line.note,
    })),
    ...dish.recipe.seasonings.map((line) => ({
      kind: 'seasoning' as const,
      targetId: line.seasoning_id,
      quantity: Number(line.quantity_per_serving_g),
      edibleRatioOverride: null,
      note: line.note,
    })),
  ];
}

// 打开时由父组件挂载、关闭时卸载，初始值直接来自 props——
// 比在 effect 里 setState 同步一遍干净，也少一次级联渲染。
export function DishFormDrawer({ dish, onClose, initialSection = 'basic' }: DishFormDrawerProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const [section, setSection] = useState(initialSection);
  const [savedDishId, setSavedDishId] = useState<string | null>(dish?.id ?? null);
  const [image, setImage] = useState<DishImageChange>({ file: null, remove: false });
  const [savingImage, setSavingImage] = useState(false);
  const [recipeError, setRecipeError] = useState('');
  const [form] = Form.useForm<DishFormValues>();
  const { data: enumOptions } = useEnumOptions();
  const ingredients = useIngredientList({ page: 1, pageSize: 100 });
  const seasonings = useSeasoningList({ page: 1, pageSize: 100 });

  const createMutation = useCreateDish();
  const updateMutation = useUpdateDish();
  const recipeMutation = useSaveRecipe();
  const isEditing = savedDishId !== null;
  const submitting =
    createMutation.isPending || updateMutation.isPending || recipeMutation.isPending || savingImage;

  const [activeLines, setActiveLines] = useState<RecipeLineForm[]>(() => buildLines(dish));
  const [savedLines, setSavedLines] = useState(() => JSON.stringify(buildLines(dish)));
  const recipeChanged = JSON.stringify(activeLines) !== savedLines;
  const requestClose = () => {
    if (submitting) return;
    if (form.isFieldsTouched() || recipeChanged || image.file || image.remove) {
      modal.confirm({
        title: '放弃未保存的修改？',
        content: '本次修改尚未保存，离开后需要重新填写。',
        okText: '放弃修改',
        cancelText: '继续编辑',
        onOk: onClose,
      });
    } else onClose();
  };

  const ingredientOptions = (ingredients.data?.items ?? [])
    .filter((item) => item.is_active)
    .map((item) => ({ value: item.id, label: item.name }));
  const seasoningOptions = (seasonings.data?.items ?? [])
    .filter((item) => item.is_active)
    .map((item) => ({ value: item.id, label: item.name }));

  const handleSubmit = async () => {
    let values: DishFormValues;
    try {
      values = await form.validateFields();
    } catch {
      setSection('basic');
      return;
    }
    const unique = new Set<string>();
    const invalid = activeLines.some((line) => {
      const key = `${line.kind}:${line.targetId}`;
      if (
        !line.targetId ||
        !Number.isFinite(line.quantity) ||
        line.quantity <= 0 ||
        unique.has(key)
      )
        return true;
      unique.add(key);
      return false;
    });
    if (
      invalid ||
      ((activeLines.length > 0 || (dish?.recipe.ingredients.length ?? 0) > 0) &&
        !activeLines.some((line) => line.kind === 'ingredient' && line.targetId))
    ) {
      setRecipeError(
        invalid
          ? '请为每行选择用料并填写大于 0 的用量，同一用料不能重复添加。'
          : '配方至少需要一项食材，请补充后保存。',
      );
      setSection('recipe');
      return;
    }
    setRecipeError('');
    const base = {
      name: values.name.trim(),
      category: values.category,
      cooking_method: values.cookingMethod,
      standard_serving_g: values.standardServingG.toFixed(2),
      servings_per_pot: values.servingsPerPot.toFixed(2),
      allergens: splitAllergens(values.allergenText ?? ''),
      is_breakfast_staple: values.isBreakfastStaple ?? false,
      note: values.note?.trim() || null,
    };

    // 配方整体提交：食材行与调味料行分开，服务端按自然键同步
    const recipe = {
      ingredients: activeLines
        .filter((line) => line.kind === 'ingredient' && line.targetId)
        .map((line) => ({
          ingredient_id: line.targetId,
          quantity_per_serving_g: line.quantity.toFixed(3),
          edible_ratio_override: line.edibleRatioOverride?.toFixed(4) ?? null,
          note: line.note,
        })),
      seasonings: activeLines
        .filter((line) => line.kind === 'seasoning' && line.targetId)
        .map((line) => ({
          seasoning_id: line.targetId,
          quantity_per_serving_g: line.quantity.toFixed(3),
          note: line.note,
        })),
    };

    try {
      let savedId = savedDishId;
      if (savedId) {
        if (form.isFieldsTouched())
          await updateMutation.mutateAsync({ id: savedId, payload: base });
        if (recipe.ingredients.length > 0 && JSON.stringify(activeLines) !== savedLines) {
          await recipeMutation.mutateAsync({ id: savedId, payload: recipe });
          setSavedLines(JSON.stringify(activeLines));
        }
      } else {
        if (recipe.ingredients.length === 0) {
          // 没有配方也能建菜品，但界面上要说清楚它暂时算不出营养
          savedId = (await createMutation.mutateAsync({ ...base, recipe: null })).id;
        } else {
          savedId = (await createMutation.mutateAsync({ ...base, recipe })).id;
        }
        setSavedLines(JSON.stringify(activeLines));
      }
      setSavedDishId(savedId);
      if (savedId && (image.file || image.remove)) {
        setSavingImage(true);
        try {
          await saveDishImage(savedId, image.file);
          await Promise.all(
            [['dishes'], ['dashboard', 'menus'], ['agent', 'dishes']].map((queryKey) =>
              queryClient.invalidateQueries({ queryKey }),
            ),
          );
          void message.success(image.remove ? '菜品图片已移除' : '菜品图片已保存');
        } catch (error) {
          void message.error(
            `菜品信息已保存，图片未保存：${error instanceof Error ? error.message : '请重试'}`,
          );
          // 保留图片与已创建的菜品 ID，重试不会再次新增。
          setSection('image');
          return;
        } finally {
          setSavingImage(false);
        }
      }
      onClose();
    } catch {
      // 失败提示由 mutation 的 onError 统一处理，这里只需保持抽屉打开
    }
  };

  return (
    <Drawer
      title={isEditing ? (dish ? `编辑菜品：${dish.name}` : '完善菜品图片') : '新增菜品'}
      open
      size={section === 'recipe' ? 860 : 540}
      className="zw-dish-form-drawer"
      onClose={requestClose}
      destroyOnHidden
      maskClosable={!submitting}
      closable={!submitting}
      footer={
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button disabled={submitting} onClick={requestClose}>
            取消
          </Button>
          <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>
            {isEditing ? '保存' : '新增'}
          </Button>
        </Space>
      }
    >
      <Tabs
        activeKey={section}
        onChange={setSection}
        items={[
          { key: 'basic', label: '基本信息' },
          { key: 'recipe', label: '标准配方' },
          { key: 'image', label: '菜品图片' },
        ]}
      />
      <div hidden={section !== 'image'}>
        <DishImageUpload
          currentUrl={dish?.image_url}
          value={image}
          onChange={setImage}
          disabled={submitting}
        />
      </div>
      <div hidden={section === 'image'}>
        <Form<DishFormValues>
          form={form}
          layout="vertical"
          requiredMark={false}
          disabled={submitting}
          initialValues={{
            name: dish?.name ?? '',
            category: dish?.category,
            cookingMethod: dish?.cooking_method,
            standardServingG: dish ? Number(dish.standard_serving_g) : undefined,
            servingsPerPot: dish ? Number(dish.servings_per_pot) : undefined,
            allergenText: (dish?.allergens ?? []).join('、'),
            isBreakfastStaple: dish?.is_breakfast_staple ?? false,
            note: dish?.note ?? null,
          }}
        >
          <div hidden={section !== 'basic'}>
            <Form.Item
              name="name"
              label="菜品名称"
              rules={[
                { required: true, message: '请输入菜品名称' },
                { max: 64, message: '名称不能超过 64 个字符' },
              ]}
            >
              <Input placeholder="例如：土豆炖牛肉" />
            </Form.Item>

            <Space className="zw-dish-form-row" size={12} style={{ display: 'flex' }} align="start">
              <Form.Item
                name="category"
                label="类别"
                rules={[{ required: true, message: '请选择类别' }]}
                style={{ flex: 1 }}
              >
                <Select
                  style={{ width: '100%' }}
                  getPopupContainer={(trigger) => trigger.parentElement ?? document.body}
                  placeholder="请选择"
                  options={(enumOptions?.dish_category ?? []).map((option) => ({
                    value: option.value,
                    label: option.label,
                  }))}
                />
              </Form.Item>
              <Form.Item
                name="cookingMethod"
                label="烹饪方式"
                rules={[{ required: true, message: '请选择烹饪方式' }]}
                style={{ flex: 1 }}
              >
                <Select
                  style={{ width: '100%' }}
                  getPopupContainer={(trigger) => trigger.parentElement ?? document.body}
                  placeholder="请选择"
                  options={(enumOptions?.cooking_method ?? []).map((option) => ({
                    value: option.value,
                    label: option.label,
                  }))}
                />
              </Form.Item>
            </Space>

            <Space className="zw-dish-form-row" size={12} style={{ display: 'flex' }} align="start">
              <Form.Item
                name="standardServingG"
                label="标准份量（克）"
                rules={[{ required: true, message: '请输入标准份量' }]}
                style={{ flex: 1 }}
              >
                <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="servingsPerPot"
                label="单锅份数"
                rules={[{ required: true, message: '请输入单锅份数' }]}
                style={{ flex: 1 }}
              >
                <InputNumber min={0.01} precision={2} style={{ width: '100%' }} />
              </Form.Item>
            </Space>

            <Form.Item
              name="allergenText"
              label="过敏原"
              tooltip="多个用顿号或逗号分隔，例如：蛋、花生"
            >
              <Input placeholder="蛋、花生" />
            </Form.Item>

            <Form.Item
              name="isBreakfastStaple"
              label="早餐固定供应"
              valuePropName="checked"
              tooltip="勾上之后这道菜每天都是早餐的一部分（早餐不走每日选菜），并且不再出现在午餐与晚餐里"
            >
              <Switch />
            </Form.Item>

            <Form.Item name="note" label="备注">
              <Input.TextArea
                rows={4}
                maxLength={255}
                showCount
                placeholder="补充菜品介绍、制作步骤或出餐注意事项"
              />
            </Form.Item>
          </div>
          <div className="zw-recipe-workspace" hidden={section !== 'recipe'}>
            <div className="zw-recipe-saved-summary">
              <div>
                <h3>已保存的单份营养</h3>
                <Tag>
                  {recipeChanged ? '配方有未保存修改' : `配方 v${dish?.recipe_version ?? 1}`}
                </Tag>
              </div>
              <DishNutrition nutrition={dish?.nutrition} />
              <p>营养结果由保存后的配方计算。调整用量后，保存即可更新。</p>
            </div>
            <div className="zw-recipe-editor">
              <Divider>标准配方</Divider>
              <Typography.Paragraph type="secondary" style={{ marginTop: -8 }}>
                配方是全系统营养计算的唯一基准。用量的单位统一是克，食材按市品重量填写，
                计算时再按可食部比例折算。
              </Typography.Paragraph>
              {recipeError && (
                <Alert type="error" showIcon title={recipeError} className="zw-recipe-error" />
              )}

              {activeLines.map((line, index) => (
                <div className="zw-recipe-edit-line" key={index}>
                  <Select
                    disabled={submitting}
                    aria-label="配方行类型"
                    value={line.kind}
                    options={[
                      { value: 'ingredient', label: '食材' },
                      { value: 'seasoning', label: '调味料' },
                    ]}
                    onChange={(kind: RecipeLineForm['kind']) => {
                      const next = [...activeLines];
                      next[index] = { ...line, kind, targetId: '' };
                      setActiveLines(next);
                    }}
                  />
                  <Select
                    disabled={submitting}
                    aria-label="配方用料"
                    showSearch
                    value={line.targetId || undefined}
                    placeholder={line.kind === 'ingredient' ? '选择食材' : '选择调味料'}
                    optionFilterProp="label"
                    options={line.kind === 'ingredient' ? ingredientOptions : seasoningOptions}
                    onChange={(value: string) => {
                      const next = [...activeLines];
                      next[index] = { ...line, targetId: value };
                      setActiveLines(next);
                    }}
                  />
                  <div className="zw-recipe-quantity">
                    <InputNumber
                      disabled={submitting}
                      aria-label="配方用量"
                      changeOnBlur={false}
                      min={0}
                      precision={3}
                      value={line.quantity}
                      addonAfter="克"
                      style={{ width: '100%' }}
                      onChange={(value) => {
                        const next = [...activeLines];
                        next[index] = { ...line, quantity: value ?? 0 };
                        setActiveLines(next);
                      }}
                    />
                  </div>
                  <Button
                    disabled={submitting}
                    aria-label={`删除第${index + 1}行配方`}
                    type="text"
                    danger
                    icon={<MinusCircleOutlined />}
                    onClick={() => setActiveLines(activeLines.filter((_, i) => i !== index))}
                  />
                </div>
              ))}

              <Button
                disabled={submitting}
                type="dashed"
                icon={<PlusOutlined />}
                style={{ marginTop: 12 }}
                onClick={() =>
                  setActiveLines([
                    ...activeLines,
                    {
                      kind: 'ingredient',
                      targetId: '',
                      quantity: 50,
                      edibleRatioOverride: null,
                      note: null,
                    },
                  ])
                }
              >
                添加一行
              </Button>

              {activeLines.length === 0 ? (
                <Typography.Paragraph type="warning" style={{ marginTop: 12 }}>
                  还没有配方，这道菜暂时算不出营养值，也就不会出现在公开大屏上。
                </Typography.Paragraph>
              ) : null}
            </div>
          </div>
        </Form>
      </div>
    </Drawer>
  );
}
