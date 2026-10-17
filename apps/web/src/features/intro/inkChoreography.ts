import paths from './handwrittenPaths.json' with { type: 'json' };

export const clamp = (value: number) => Math.max(0, Math.min(1, value));
export const settle = (value: number) => value * value * (3 - 2 * value);
type Profile = [number, number, number, number]; // 路程、笔宽、墨色、干笔比例
export type BrushStyle = {
  name: string;
  character: '知' | '味';
  ms: number;
  pause: number;
  profile: Profile[];
  pace: [number, number][];
};
const styles: BrushStyle[] = [
  {
    name: '知 · 起笔与横挑',
    character: '知',
    ms: 590,
    pause: 55,
    profile: [
      [0, 3, 0.75, 0.08],
      [0.12, 47, 0.98, 0.04],
      [0.34, 61, 0.97, 0.08],
      [0.56, 37, 0.92, 0.12],
      [0.65, 21, 0.66, 0.3],
      [0.84, 25, 0.65, 0.37],
      [1, 1.8, 0.4, 0.6],
    ],
    pace: [
      [0, 0],
      [0.13, 0.045],
      [0.45, 0.49],
      [0.69, 0.65],
      [0.95, 0.95],
      [1, 1],
    ],
  },
  {
    name: '知 · 游丝回锋',
    character: '知',
    ms: 460,
    pause: 35,
    profile: [
      [0, 2, 0.48, 0.65],
      [0.39, 2.4, 0.53, 0.65],
      [0.55, 4, 0.6, 0.6],
      [0.64, 11, 0.8, 0.55],
      [0.84, 25, 0.85, 0.45],
      [0.93, 21, 0.81, 0.4],
      [1, 1.5, 0.4, 0.65],
    ],
    pace: [
      [0, 0],
      [0.32, 0.53],
      [0.59, 0.66],
      [0.93, 0.91],
      [1, 1],
    ],
  },
  {
    name: '知 · 按笔纵撇',
    character: '知',
    ms: 370,
    pause: 65,
    profile: [
      [0, 3, 0.72, 0.1],
      [0.14, 29, 0.99, 0.04],
      [0.38, 42, 0.98, 0.1],
      [0.67, 37, 0.96, 0.22],
      [0.88, 15, 0.78, 0.5],
      [1, 1, 0.42, 0.8],
    ],
    pace: [
      [0, 0],
      [0.2, 0.08],
      [0.62, 0.53],
      [0.89, 0.88],
      [1, 1],
    ],
  },
  {
    name: '知 · 收捺',
    character: '知',
    ms: 190,
    pause: 95,
    profile: [
      [0, 2, 0.6, 0.15],
      [0.24, 14, 0.82, 0.2],
      [0.6, 28, 0.74, 0.36],
      [0.89, 19, 0.62, 0.58],
      [1, 2, 0.42, 0.75],
    ],
    pace: [
      [0, 0],
      [0.23, 0.09],
      [0.74, 0.68],
      [1, 1],
    ],
  },
  {
    name: '知 · 连写草口',
    character: '知',
    ms: 670,
    pause: 190,
    profile: [
      [0, 2, 0.65, 0.15],
      [0.11, 19, 0.95, 0.07],
      [0.23, 25, 0.95, 0.07],
      [0.37, 15, 0.75, 0.25],
      [0.53, 24, 0.94, 0.08],
      [0.71, 31, 0.98, 0.04],
      [0.84, 23, 0.97, 0.07],
      [0.93, 28, 0.99, 0.08],
      [1, 3, 0.62, 0.36],
    ],
    pace: [
      [0, 0],
      [0.15, 0.12],
      [0.28, 0.23],
      [0.4, 0.34],
      [0.6, 0.63],
      [0.73, 0.76],
      [0.87, 0.85],
      [0.96, 0.94],
      [1, 1],
    ],
  },
  {
    name: '味 · 口左竖',
    character: '味',
    ms: 255,
    pause: 28,
    profile: [
      [0, 2, 0.66, 0.16],
      [0.2, 18, 0.9, 0.08],
      [0.65, 26, 0.96, 0.06],
      [0.88, 19, 0.88, 0.18],
      [1, 1.4, 0.6, 0.35],
    ],
    pace: [
      [0, 0],
      [0.25, 0.12],
      [0.75, 0.72],
      [1, 1],
    ],
  },
  {
    name: '味 · 口回转与牵丝',
    character: '味',
    ms: 430,
    pause: 55,
    profile: [
      [0, 2, 0.55, 0.45],
      [0.12, 15, 0.8, 0.18],
      [0.3, 26, 0.96, 0.06],
      [0.51, 20, 0.97, 0.09],
      [0.64, 25, 0.91, 0.12],
      [0.74, 8, 0.65, 0.45],
      [0.88, 1.7, 0.43, 0.7],
      [1, 0.9, 0.25, 0.85],
    ],
    pace: [
      [0, 0],
      [0.22, 0.15],
      [0.43, 0.36],
      [0.71, 0.64],
      [0.83, 0.75],
      [1, 1],
    ],
  },
  {
    name: '味 · 上横回锋',
    character: '味',
    ms: 280,
    pause: 62,
    profile: [
      [0, 2, 0.65, 0.2],
      [0.23, 26, 0.98, 0.04],
      [0.54, 37, 0.99, 0.02],
      [0.69, 27, 0.86, 0.12],
      [0.85, 11, 0.65, 0.45],
      [1, 1.3, 0.45, 0.7],
    ],
    pace: [
      [0, 0],
      [0.23, 0.1],
      [0.51, 0.51],
      [0.83, 0.7],
      [1, 1],
    ],
  },
  {
    name: '味 · 下横',
    character: '味',
    ms: 235,
    pause: 55,
    profile: [
      [0, 2, 0.7, 0.15],
      [0.14, 26, 0.98, 0.06],
      [0.37, 32, 0.95, 0.1],
      [0.72, 24, 0.74, 0.25],
      [0.93, 15, 0.64, 0.5],
      [1, 1.5, 0.4, 0.75],
    ],
    pace: [
      [0, 0],
      [0.24, 0.11],
      [0.77, 0.74],
      [1, 1],
    ],
  },
  {
    name: '味 · 沉笔长竖',
    character: '味',
    ms: 710,
    pause: 80,
    profile: [
      [0, 2, 0.75, 0.1],
      [0.07, 26, 0.99, 0.03],
      [0.18, 20, 0.95, 0.18],
      [0.39, 17, 0.72, 0.63],
      [0.66, 18, 0.82, 0.55],
      [0.85, 36, 0.98, 0.12],
      [0.96, 46, 1, 0.02],
      [1, 10, 0.87, 0.18],
    ],
    pace: [
      [0, 0],
      [0.15, 0.04],
      [0.31, 0.2],
      [0.6, 0.69],
      [0.83, 0.9],
      [0.97, 0.97],
      [1, 1],
    ],
  },
  {
    name: '味 · 提笔长撇',
    character: '味',
    ms: 330,
    pause: 30,
    profile: [
      [0, 2, 0.66, 0.25],
      [0.12, 23, 0.94, 0.12],
      [0.35, 29, 0.94, 0.14],
      [0.6, 18, 0.79, 0.3],
      [0.74, 7, 0.6, 0.6],
      [0.87, 1.1, 0.38, 0.75],
      [1, 0.65, 0.16, 0.9],
    ],
    pace: [
      [0, 0],
      [0.23, 0.1],
      [0.72, 0.6],
      [1, 1],
    ],
  },
  {
    name: '味 · 飞白收捺',
    character: '味',
    ms: 210,
    pause: 0,
    profile: [
      [0, 2, 0.55, 0.3],
      [0.24, 17, 0.83, 0.2],
      [0.61, 31, 0.77, 0.45],
      [0.82, 20, 0.6, 0.7],
      [1, 1.3, 0.35, 0.9],
    ],
    pace: [
      [0, 0],
      [0.22, 0.11],
      [0.72, 0.66],
      [1, 1],
    ],
  },
];

type XY = { x: number; y: number };
type Point = XY & { u: number; width: number; ink: number; dry: number; nx: number; ny: number };
type Stroke = BrushStyle & {
  id: number;
  sourcePath: string;
  start: number;
  length: number;
  points: Point[];
  fullRibbon: string;
  bounds: { x: number; y: number; width: number; height: number };
};
function mix(a: number, b: number, t: number) {
  return a + (b - a) * t;
}
function cubic(a: number, b: number, c: number, d: number, t: number) {
  const s = 1 - t;
  return s * s * s * a + 3 * s * s * t * b + 3 * s * t * t * c + t * t * t * d;
}
function profileAt(profile: Profile[], u: number) {
  const i = Math.max(0, profile.findIndex((p) => p[0] >= u) - 1),
    a = profile[i],
    b = profile[Math.min(i + 1, profile.length - 1)];
  const t = settle(clamp((u - a[0]) / (b[0] - a[0] || 1)));
  return { width: mix(a[1], b[1], t), ink: mix(a[2], b[2], t), dry: mix(a[3], b[3], t) };
}
function paceAt(pace: [number, number][], t: number) {
  const i = Math.max(0, pace.findIndex((p) => p[0] >= t) - 1),
    a = pace[i],
    b = pace[Math.min(i + 1, pace.length - 1)];
  const local = clamp((t - a[0]) / (b[0] - a[0] || 1));
  return mix(a[1], b[1], mix(local, settle(local), 0.18));
}
const fixed = (n: number) => n.toFixed(2);
// 微小的、可重复的笔毫偏差不会在播放时闪烁。
function rough(u: number, seed: number) {
  return Math.sin(u * 233 + seed * 7) * 0.48 + Math.sin(u * 571 + seed * 13) * 0.28;
}
function ribbon(points: Point[], seed: number) {
  if (points.length < 2) return '';
  const pieces: string[] = [];
  // 每小段与笔毫接点均独立叠墨，急转和回锋不会让轮廓相消成白洞。
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1],
      b = points[i],
      dx = b.x - a.x,
      dy = b.y - a.y,
      length = Math.hypot(dx, dy) || 1;
    const nx = -dy / length,
      ny = dx / length;
    const aw = Math.max(
      0.1,
      a.width * 0.5 + rough(a.u, seed) * Math.min(1, a.width * 0.08) * a.dry,
    );
    const bw = Math.max(
      0.1,
      b.width * 0.5 + rough(b.u, seed) * Math.min(1, b.width * 0.08) * b.dry,
    );
    pieces.push(
      'M ' +
        fixed(a.x + nx * aw) +
        ' ' +
        fixed(a.y + ny * aw) +
        ' L ' +
        fixed(b.x + nx * bw) +
        ' ' +
        fixed(b.y + ny * bw) +
        ' L ' +
        fixed(b.x - nx * bw) +
        ' ' +
        fixed(b.y - ny * bw) +
        ' L ' +
        fixed(a.x - nx * aw) +
        ' ' +
        fixed(a.y - ny * aw) +
        ' Z',
    );
    if (i < points.length - 1) {
      const r = Math.max(0.12, b.width * 0.48);
      pieces.push(
        'M ' +
          fixed(b.x + r) +
          ' ' +
          fixed(b.y) +
          ' a ' +
          fixed(r) +
          ' ' +
          fixed(r) +
          ' 0 1 0 ' +
          fixed(-2 * r) +
          ' 0 a ' +
          fixed(r) +
          ' ' +
          fixed(r) +
          ' 0 1 0 ' +
          fixed(2 * r) +
          ' 0 Z',
      );
    }
  }
  return pieces.join(' ');
}
let cursor = 480;
export const INK_STROKES: Stroke[] = paths.map((path, index) => {
  const style = styles[index];
  const raw: (XY & { distance: number })[] = [{ ...path.nodes[0], distance: 0 }];
  path.nodes.slice(1).forEach((b, i) => {
    const a = path.nodes[i];
    for (let step = 1; step <= 44; step++) {
      const t = step / 44,
        previous = raw.at(-1)!;
      const x = cubic(a.x, a.out.x, b.in.x, b.x, t),
        y = cubic(a.y, a.out.y, b.in.y, b.y, t);
      raw.push({ x, y, distance: previous.distance + Math.hypot(x - previous.x, y - previous.y) });
    }
  });
  const length = raw.at(-1)!.distance,
    count = Math.ceil(length / 1.4),
    points: Point[] = [];
  let segment = 1;
  for (let i = 0; i <= count; i++) {
    const u = i / count,
      distance = u * length;
    while (segment < raw.length - 1 && raw[segment].distance < distance) segment++;
    const a = raw[segment - 1],
      b = raw[segment],
      t = (distance - a.distance) / (b.distance - a.distance || 1);
    points.push({
      x: mix(a.x, b.x, t),
      y: mix(a.y, b.y, t),
      u,
      ...profileAt(style.profile, u),
      nx: 0,
      ny: 0,
    });
  }
  points.forEach((p, i) => {
    const a = points[Math.max(0, i - 1)],
      b = points[Math.min(points.length - 1, i + 1)],
      dx = b.x - a.x,
      dy = b.y - a.y,
      length = Math.hypot(dx, dy) || 1;
    p.nx = -dy / length;
    p.ny = dx / length;
  });
  const xs = points.map((p) => p.x),
    ys = points.map((p) => p.y),
    padding = Math.max(...style.profile.map((p) => p[1])) * 0.6 + 8;
  const bounds = {
    x: Math.min(...xs) - padding,
    y: Math.min(...ys) - padding,
    width: Math.max(...xs) - Math.min(...xs) + padding * 2,
    height: Math.max(...ys) - Math.min(...ys) + padding * 2,
  };
  const start = cursor;
  cursor += style.ms + style.pause;
  return {
    ...style,
    id: path.id,
    sourcePath: path.d,
    start,
    length,
    points,
    bounds,
    fullRibbon: ribbon(points, index),
  };
});
export const WRITING_END = cursor;
export const SEAL_START = WRITING_END + 310;
export const DURATION = SEAL_START + 850;
export const TASTE_START = INK_STROKES.find((s) => s.character === '味')!.start;
const TOTAL_LENGTH = INK_STROKES.reduce((sum, s) => sum + s.length, 0);
type BrushFrame = {
  amount: number;
  head: Point;
  ribbon: string;
  fibers: { d: string; width: number; opacity: number }[];
};
const completedFrames = new Map<number, BrushFrame>();
export function brushFrame(stroke: Stroke, elapsed: number): BrushFrame {
  const cached = elapsed >= stroke.start + stroke.ms ? completedFrames.get(stroke.id) : undefined;
  if (cached) return cached;
  const time = clamp((elapsed - stroke.start) / stroke.ms),
    amount = paceAt(stroke.pace, time);
  const position = amount * (stroke.points.length - 1),
    i = Math.floor(position),
    a = stroke.points[i],
    b = stroke.points[Math.min(i + 1, stroke.points.length - 1)],
    t = position - i;
  const head = {
    ...a,
    x: mix(a.x, b.x, t),
    y: mix(a.y, b.y, t),
    u: amount,
    ...profileAt(stroke.profile, amount),
  };
  const points = stroke.points.slice(0, i + 1);
  if (amount < 1) points.push(head);
  const fibers: { d: string; width: number; opacity: number }[] = [];
  // 飞白镂空限制在这一笔自己的墨迹里，交叉处仍可自然叠墨。
  [-0.72, -0.46, -0.19, 0.12, 0.38, 0.67].forEach((offset, lane) => {
    let run: Point[] = [];
    const flush = () => {
      if (run.length > 3) {
        const d = run
          .map((p, j) => {
            const lateral = (offset + 0.035 * Math.sin(p.u * 81 + lane)) * p.width * 0.5;
            return `${j === 0 ? 'M' : 'L'} ${fixed(p.x + p.nx * lateral)} ${fixed(p.y + p.ny * lateral)}`;
          })
          .join(' ');
        fibers.push({
          d,
          width: 0.55 + (lane % 3) * 0.38,
          opacity: 0.55 + Math.min(0.45, run.reduce((sum, p) => sum + p.dry, 0) / run.length),
        });
      }
      run = [];
    };
    points.forEach((p) => {
      if (
        p.dry > 0.27 + (lane % 3) * 0.1 &&
        p.width > 2.5 &&
        Math.sin(p.u * 61 + lane * 2.7) > -0.72
      )
        run.push(p);
      else flush();
    });
    flush();
  });
  const result = {
    amount,
    head,
    ribbon: amount === 1 ? stroke.fullRibbon : ribbon(points, stroke.id - 1),
    fibers,
  };
  if (amount === 1) completedFrames.set(stroke.id, result);
  return result;
}
export function inkProgress(elapsed: number) {
  return INK_STROKES.reduce((sum, s) => sum + brushAmount(s, elapsed) * s.length, 0) / TOTAL_LENGTH;
}
function brushAmount(stroke: Stroke, elapsed: number) {
  return paceAt(stroke.pace, clamp((elapsed - stroke.start) / stroke.ms));
}
export function inkColor(ink: number) {
  const gray = Math.round((1 - ink) * 150 + 10);
  return `rgb(${gray},${gray},${gray})`;
}
