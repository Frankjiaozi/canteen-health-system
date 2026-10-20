import { useEffect, useState, type ReactNode } from 'react';
import { STAGE_HEIGHT, STAGE_WIDTH, computeStageLayout } from '../lib/stage';

// 1920×1080 基准舞台：等比缩放并居中。
//
// 现场没人会去调大屏机器的分辨率，所以版面按基准画好，由这里统一缩放，
// 任何分辨率下都不会溢出或出现滚动条。
export function BaselineStage({ children }: { children: ReactNode }) {
  const [layout, setLayout] = useState(() =>
    computeStageLayout(window.innerWidth, window.innerHeight),
  );

  useEffect(() => {
    const update = () => setLayout(computeStageLayout(window.innerWidth, window.innerHeight));
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        overflow: 'hidden',
        background: 'radial-gradient(circle at 18% 0%, #ffffff 0%, #f4f7f1 42%, #e7eee4 100%)',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: layout.offsetX,
          top: layout.offsetY,
          width: STAGE_WIDTH,
          height: STAGE_HEIGHT,
          transform: `scale(${layout.scale})`,
          transformOrigin: 'top left',
        }}
      >
        {children}
      </div>
    </div>
  );
}
