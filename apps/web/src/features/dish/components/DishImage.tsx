import { PictureOutlined } from '@ant-design/icons';
import { useState } from 'react';

/** 没有用户图片时始终显示占位，不用示例食物照片替代。 */
export function DishImage({
  url,
  name,
  compact = false,
}: {
  url?: string | null;
  name: string;
  compact?: boolean;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const showImage = !!url && failedUrl !== url;
  return (
    <div className={`zw-dish-image${compact ? ' is-compact' : ''}`}>
      {showImage ? (
        <img src={url} alt={name} loading="lazy" onError={() => setFailedUrl(url)} />
      ) : (
        <span>
          <PictureOutlined />
          <small>暂无图片</small>
        </span>
      )}
    </div>
  );
}
