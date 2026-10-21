import { PictureOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { resolveDishImageUrl } from '../lib/defaultImage';

/** 用户上传图优先；没有上传时使用随应用发布的内置菜品图。 */
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
  const uploaded = url && failedUrl !== url ? url : null;
  const source = uploaded || resolveDishImageUrl(name);
  const showImage = !!source && failedUrl !== source;
  return (
    <div className={`zw-dish-image${compact ? ' is-compact' : ''}`}>
      {showImage ? (
        <img src={source} alt={name} loading="lazy" onError={() => setFailedUrl(source)} />
      ) : (
        <span>
          <PictureOutlined />
          <small>暂无图片</small>
        </span>
      )}
    </div>
  );
}
