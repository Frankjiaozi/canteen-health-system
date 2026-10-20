import { useId } from 'react';

/** 原始书法资产不变，视窗裁切留白，显示滤镜去除白底。 */
export function BrandMark({ compact = false }: { compact?: boolean }) {
  const filterId = useId().replaceAll(':', '');
  return (
    <div className={`zw-brand-mark${compact ? ' is-compact' : ''}`}>
      <svg viewBox="530 250 640 335" role="img" aria-label="知味">
        <defs>
          <filter id={filterId}>
            <feColorMatrix type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 -1 -1 -1 0 3" />
          </filter>
        </defs>
        <image
          href="/intro/ink-wordmark-cursive.png"
          width="1672"
          height="941"
          filter={`url(#${filterId})`}
        />
      </svg>
      {!compact && <span>校园智慧膳食平台</span>}
    </div>
  );
}
