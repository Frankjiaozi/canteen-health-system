import { clamp, INK_STROKES, settle } from './inkChoreography';
import { REVEAL_WIDTHS, STROKE_REGIONS } from './strokeLayers';

export const INK_BOX = { x: 533, y: 278, width: 565, height: 294 };
function makeCanvas() {
  const canvas = document.createElement('canvas');
  canvas.width = INK_BOX.width;
  canvas.height = INK_BOX.height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('Canvas unavailable');
  return { canvas, context };
}
function distanceAt(pace: [number, number][], time: number) {
  const t = clamp(time);
  const index = Math.max(0, pace.findIndex((p) => p[0] >= t) - 1);
  const a = pace[index],
    b = pace[Math.min(index + 1, pace.length - 1)];
  const u = clamp((t - a[0]) / (b[0] - a[0] || 1));
  return a[1] + (b[1] - a[1]) * (u * 0.8 + settle(u) * 0.2);
}
export function createInkPainter(canvas: HTMLCanvasElement, image: HTMLImageElement) {
  canvas.width = INK_BOX.width;
  canvas.height = INK_BOX.height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas unavailable');
  const source = makeCanvas();
  source.context.drawImage(image, -INK_BOX.x, -INK_BOX.y);
  const artwork = source.context.getImageData(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < artwork.data.length; i += 4) {
    const darkness = 1 - (artwork.data[i] + artwork.data[i + 1] + artwork.data[i + 2]) / 765;
    artwork.data[i + 3] = Math.round(darkness * artwork.data[i + 3]);
    artwork.data[i] = artwork.data[i + 1] = artwork.data[i + 2] = 0;
  }
  source.context.putImageData(artwork, 0, 0);
  // 十二个独立墨迹图层，再按路径显现；不用全字最近路径分配像素。
  const layers = INK_STROKES.map((stroke, index) => {
    const layer = makeCanvas();
    layer.context.save();
    layer.context.translate(-INK_BOX.x, -INK_BOX.y);
    layer.context.clip(new Path2D(STROKE_REGIONS[index]));
    layer.context.drawImage(source.canvas, INK_BOX.x, INK_BOX.y);
    layer.context.restore();
    const full = layer.context.getImageData(0, 0, canvas.width, canvas.height);
    const pixels: number[] = [];
    for (let i = 3; i < full.data.length; i += 4) {
      if (full.data[i] > 2) pixels.push(i);
    }
    return { stroke, canvas: layer.canvas, full, pixels, width: REVEAL_WIDTHS[index] };
  });
  const mask = makeCanvas(),
    active = makeCanvas();
  const output = context.createImageData(canvas.width, canvas.height);
  let previous = -1;
  return {
    paint(elapsed: number) {
      if (elapsed === previous) return;
      previous = elapsed;
      output.data.fill(0);
      for (const layer of layers) {
        const { stroke } = layer;
        if (elapsed <= stroke.start) continue;
        let data = layer.full.data;
        if (elapsed < stroke.start + stroke.ms) {
          const u = distanceAt(stroke.pace, (elapsed - stroke.start) / stroke.ms);
          mask.context.clearRect(0, 0, canvas.width, canvas.height);
          mask.context.save();
          mask.context.translate(-INK_BOX.x, -INK_BOX.y);
          mask.context.strokeStyle = '#fff';
          mask.context.lineCap = 'round';
          mask.context.lineJoin = 'round';
          const points = stroke.points;
          for (let j = 1; j < points.length; j++) {
            const a = points[j - 1],
              b = points[j];
            if (a.u >= u) break;
            const part = clamp((u - a.u) / (b.u - a.u));
            mask.context.lineWidth = layer.width;
            mask.context.beginPath();
            mask.context.moveTo(a.x, a.y);
            mask.context.lineTo(a.x + (b.x - a.x) * part, a.y + (b.y - a.y) * part);
            mask.context.stroke();
          }
          mask.context.restore();
          active.context.clearRect(0, 0, canvas.width, canvas.height);
          active.context.globalCompositeOperation = 'source-over';
          active.context.drawImage(layer.canvas, 0, 0);
          active.context.globalCompositeOperation = 'destination-in';
          active.context.drawImage(mask.canvas, 0, 0);
          active.context.globalCompositeOperation = 'source-over';
          data = active.context.getImageData(0, 0, canvas.width, canvas.height).data;
        }
        // 交叉区域取一次原稿浓度，重播和拖动时间轴不会累积黑块。
        for (const i of layer.pixels) output.data[i] = Math.max(output.data[i], data[i]);
      }
      context.putImageData(output, 0, 0);
    },
  };
}
