import { useEffect, useRef } from 'react';

// 用原稿的墨迹纹理沿起伏轨迹铺开，整条墨线只绘制一次。
// 播放时只改变裁剪范围，留下的笔触不伸缩，也不重新生成。
const HEIGHTS = [45, 26, 21, 36, 57, 62, 45, 24, 30];
function sweepHeight(t: number) {
  const position = t * (HEIGHTS.length - 1);
  const i = Math.min(HEIGHTS.length - 2, Math.floor(position));
  const u = position - i;
  const a = HEIGHTS[Math.max(0, i - 1)];
  const b = HEIGHTS[i];
  const c = HEIGHTS[i + 1];
  const d = HEIGHTS[Math.min(HEIGHTS.length - 1, i + 2)];
  return (
    0.5 *
    (2 * b +
      (-a + c) * u +
      (2 * a - 5 * b + 4 * c - d) * u * u +
      (-a + 3 * b - 3 * c + d) * u * u * u)
  );
}

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
        canvas.height = 180;
        const context = canvas.getContext('2d');
        if (!context) return;
        context.fillStyle = '#fff';
        context.fillRect(0, 0, canvas.width, canvas.height);
        for (let x = 0; x < canvas.width; x++) {
          const t = x / (canvas.width - 1);
          const y = (sweepHeight(t) - 18) * 2;
          context.drawImage(image, 575 + 505 * t, 597, 505 / canvas.width, 61, x, y, 1, 72);
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
