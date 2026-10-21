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
};

export function defaultDishImageUrl(name: string): string | undefined {
  const file = DEFAULT_DISH_IMAGES[name.trim()];
  return file ? `${DISH_IMAGE_DIR}/${file}` : undefined;
}

/** 用户上传图优先；没有上传时使用随应用发布的默认配图。 */
export function resolveDishImageUrl(name: string, uploadedUrl?: string | null): string | undefined {
  return uploadedUrl || defaultDishImageUrl(name);
}
