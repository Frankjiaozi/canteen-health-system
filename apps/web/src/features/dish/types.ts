import type { components } from '@canteen/api-client';

export type Dish = components['schemas']['DishRead'];
export type DishDetail = components['schemas']['DishDetail'];
export type DishCreatePayload = components['schemas']['DishCreate'];
export type DishUpdatePayload = components['schemas']['DishUpdate'];
export type DishPage = components['schemas']['DishPage'];
export type DishCategory = components['schemas']['DishCategory'];
export type CookingMethod = components['schemas']['CookingMethod'];
export type NutritionSummary = components['schemas']['NutritionSummary'];
export type RecipePayload = components['schemas']['RecipePayload'];
export type RecipeRead = components['schemas']['RecipeRead'];
export type RecipeUpdateResult = components['schemas']['RecipeUpdateResult'];

export type Seasoning = components['schemas']['SeasoningRead'];
export type SeasoningCreatePayload = components['schemas']['SeasoningCreate'];
export type SeasoningUpdatePayload = components['schemas']['SeasoningUpdate'];
export type SeasoningCategory = components['schemas']['SeasoningCategory'];

export type ImportReport = components['schemas']['ImportReport'];
export type ImportIssue = components['schemas']['ImportIssue'];
