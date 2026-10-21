import { useEffect, useRef } from 'react';

// 用原稿的墨迹纹理沿起伏轨迹铺开，整条墨线只绘制一次。
// 播放时只改变裁剪范围，留下的笔触不伸缩，也不重新生成。
// 按用户手绘路径描摹：左侧拱起后快速落笔，中段低位舒展，右端向上扬起。
const SWEEP_PATH =
  'M42 166 C98 114 123 91 174 80 C207 66 211 139 252 160 C285 179 340 173 388 172 C520 171 610 119 671 40';

export function InkProgressStroke({ progress, art }: { progress: number; art: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let cancelled = false;
    const image = new Image();
    image.src = art;
    image
      .decode()
      .then(() => {
        const canvas = canvasRef.current;
        if (cancelled || !canvas) return;
        canvas.width = 2020;
        canvas.height = 320;
        const context = canvas.getContext('2d');
        if (!context) return;
        context.fillStyle = '#fff';
        context.fillRect(0, 0, canvas.width, canvas.height);
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', SWEEP_PATH);
        const length = path.getTotalLength();
        const points = Array.from({ length: 513 }, (_, index) =>
          path.getPointAtLength((length * index) / 512),
        );
        let pointIndex = 1;
        for (let x = 0; x < canvas.width; x++) {
          const t = x / (canvas.width - 1);
          const sourceX = 42 + t * (671 - 42);
          while (pointIndex < points.length - 1 && points[pointIndex].x < sourceX) pointIndex++;
          const start = points[pointIndex - 1];
          const end = points[pointIndex];
          const fraction = Math.max(0, Math.min(1, (sourceX - start.x) / (end.x - start.x || 1)));
          const sourceY = start.y + (end.y - start.y) * fraction;
          const y = 8 + ((sourceY - 40) / 134) * 242;
          context.drawImage(image, 575 + 505 * t, 597, 505 / canvas.width, 61, x, y, 1, 64);
        }
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
        for (let i = 0; i < pixels.data.length; i += 4) {
          const darkness = 1 - (pixels.data[i] + pixels.data[i + 1] + pixels.data[i + 2]) / 765;
          pixels.data[i + 3] = Math.round(darkness * 255);
          pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = 0;
        }
        context.putImageData(pixels, 0, 0);
      })
      .catch(() => {
        /* 素材失败由预览页面统一显示重试入口。 */
      });
    return () => {
      cancelled = true;
    };
  }, [art]);
  return (
    <div
      className="ink-page-progress"
      aria-hidden="true"
      style={{ clipPath: `inset(0 ${(1 - progress) * 100}% 0 0)` }}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
