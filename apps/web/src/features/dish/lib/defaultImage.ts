const DISH_IMAGE_DIR = '/design/dishes';

const DEFAULT_DISH_IMAGES: Record<string, string> = {
  木耳炒肉片: 'wood-ear-pork.webp',
  番茄炒蛋: 'tomato-eggs.webp',
  胡萝卜炒鸡蛋: 'carrot-eggs.webp',
  青椒炒肉丝: 'pepper-pork.webp',
  麻婆豆腐: 'mapo-tofu.webp',
  土豆炖牛肉: 'potato-beef.webp',
  宫保鸡丁: 'kung-pao-chicken.webp',
  清蒸鲈鱼: 'steamed-bass.webp',
  红烧肉: 'braised-pork.webp',
  鸡腿烧土豆: 'chicken-potatoes.webp',
  冬瓜排骨汤: 'winter-melon-ribs.webp',
  番茄蛋汤: 'tomato-egg-soup.webp',
  清炒西兰花: 'stir_broccoli.webp',
  紫菜蛋花汤: 'nori_egg_soup.webp',
  米饭: 'steamed_rice.webp',
  馒头: 'steamed_bun.webp',
  蒜蓉油菜: 'garlic_bok_choy.webp',
  醋溜白菜: 'vinegar_cabbage.webp',
  凉拌黄瓜: 'cucumber_salad.webp',
  干煸豆角: 'dry_fried_beans.webp',
  冬瓜蛋花汤: 'winter_melon_egg_soup.webp',
  番茄豆腐汤: 'tomato_tofu_soup.webp',
  紫菜豆腐汤: 'nori_tofu_soup.webp',
  蒜蓉西兰花: 'garlic_broccoli.webp',
  青椒土豆丝: 'pepper_potato.webp',
  洋葱木耳: 'onion_wood_ear.webp',
  清炒胡萝卜: 'carrot_stir.webp',
  番茄炖牛肉: 'tomato_beef.webp',
  鸡丁炒黄瓜: 'chicken_cucumber.webp',
  虾仁豆腐: 'prawn_tofu.webp',
  白粥: 'congee.webp',
  花卷: 'steamed_roll.webp',
  煮鸡蛋: 'boiled_egg.webp',
  鸡蛋饼: 'egg_pancake.webp',
  热牛奶: 'hot_milk.webp',
  晨光番茄蛋: 'breakfast_tomato_egg.webp',
  清炒小油菜: 'breakfast_bok_choy.webp',
  豆腐蛋花汤: 'breakfast_tofu_soup.webp',
  胡萝卜鸡蛋饼: 'breakfast_carrot_pancake.webp',
  醋香白菜: 'breakfast_cabbage.webp',
};

export function defaultDishImageUrl(name: string): string | undefined {
  const file = DEFAULT_DISH_IMAGES[name.trim()];
  return file ? `${DISH_IMAGE_DIR}/${file}` : undefined;
}

/** 用户上传图优先；没有上传时使用随应用发布的默认配图。 */
export function resolveDishImageUrl(name: string, uploadedUrl?: string | null): string | undefined {
  return uploadedUrl || defaultDishImageUrl(name);
}
