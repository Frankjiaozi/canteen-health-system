import { useEffect, useId, useRef, useState } from 'react';
import { InkAtmosphere } from './InkAtmosphere';
import { InkProgressStroke } from './InkProgressStroke';
import './intro.css';
const ART = '/intro/ink-wordmark-cursive.png';
const SWEEP_START = 160;
const SWEEP_END = 1950;
const SEAL_START = 2270;
const DURATION = 2600;
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const settle = (value: number) => value * value * (3 - 2 * value);
const DOTS = [
  { x: 571, y: 351, r: 3.3, opacity: 0.4 },
  { x: 579, y: 337, r: 1.6, opacity: 0.65 },
  { x: 619, y: 245, r: 2.1, opacity: 0.5 },
  { x: 670, y: 257, r: 1.4, opacity: 0.32 },
  { x: 615, y: 275, r: 1.3, opacity: 0.6 },
  { x: 561, y: 472, r: 2.7, opacity: 0.35 },
  { x: 578, y: 455, r: 1.1, opacity: 0.48 },
  { x: 704, y: 555, r: 3.1, opacity: 0.2 },
  { x: 721, y: 549, r: 1.4, opacity: 0.35 },
  { x: 1022, y: 287, r: 2.5, opacity: 0.45 },
  { x: 1040, y: 296, r: 1.2, opacity: 0.3 },
  { x: 1118, y: 393, r: 3.2, opacity: 0.3 },
  { x: 1145, y: 452, r: 1.7, opacity: 0.5 },
  { x: 1102, y: 477, r: 1.2, opacity: 0.6 },
];
export function IntroPreviewPage({ onComplete }: { onComplete?: () => void }) {
  const [reducedMotion] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const [elapsed, setElapsed] = useState(reducedMotion ? DURATION : 0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const elapsedRef = useRef(elapsed);
  const id = useId().replaceAll(':', '');
  useEffect(() => {
    let cancelled = false;
    const image = new Image();
    image.src = ART;
    image
      .decode()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (!ready || elapsedRef.current >= DURATION) return;
    let previous = performance.now(),
      frameId: number;
    const resetClock = () => {
      previous = performance.now();
    };
    const frame = (now: number) => {
      if (!document.hidden) {
        elapsedRef.current = Math.min(DURATION, elapsedRef.current + (now - previous));
        setElapsed(elapsedRef.current);
      }
      previous = now;
      if (elapsedRef.current < DURATION) frameId = requestAnimationFrame(frame);
    };
    document.addEventListener('visibilitychange', resetClock);
    frameId = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(frameId);
      document.removeEventListener('visibilitychange', resetClock);
    };
  }, [ready]);
  useEffect(() => {
    if (!onComplete || (!failed && (!ready || elapsed < DURATION))) return;
    // 素材加载失败时直接进入系统，进场效果不能阻塞业务入口。
    const timeout = window.setTimeout(onComplete, failed ? 0 : 180);
    return () => window.clearTimeout(timeout);
  }, [elapsed, ready, failed, onComplete]);
  const progress = settle(clamp((elapsed - SWEEP_START) / (SWEEP_END - SWEEP_START))),
    seal = clamp((elapsed - SEAL_START) / 330);
  const sweepX = 533 + 565 * progress;
  const matureProgress = settle(clamp((elapsed - SWEEP_START - 320) / (SWEEP_END - SWEEP_START)));
  const matureX = 533 + 565 * matureProgress;
  const freshInk = Math.round(70 + 185 * settle(clamp((elapsed - SWEEP_END) / 320)));
  const sceneLabel = !ready
    ? '墨迹准备中'
    : elapsed < SWEEP_START
      ? '墨点正在出现'
      : elapsed < SWEEP_END + 320
        ? '知味正在从左向右显现'
        : elapsed < SEAL_START
          ? '知味已显现，等待落印'
          : seal < 1
            ? '正在落下朱红印章'
            : '知味书写完成，朱红印章已落下';
  const sealScale = 1.08 - settle(clamp(seal / 0.68)) * 0.08;
  // 数字表示完整入场进度，包含书写和落印，不把动画时间冒充接口下载进度。
  const entranceProgress = ready ? clamp(elapsed / DURATION) : 0;
  const percentage = Math.floor(entranceProgress * 100);
  return (
    <main
      className={`ink-preview${onComplete && ready && elapsed >= DURATION ? ' ink-preview-finished' : ''}`}
      aria-label="知味进场动画"
    >
      <InkAtmosphere reducedMotion={reducedMotion} />
      <svg className="ink-paper" width="100%" height="100%" aria-hidden="true">
        <defs>
          <filter id={`${id}-paper`}>
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.008 0.014"
              numOctaves="3"
              seed="17"
            />
            <feColorMatrix type="saturate" values="0" />
            <feComponentTransfer>
              <feFuncA type="linear" slope="0.11" />
            </feComponentTransfer>
          </filter>
        </defs>
        <rect width="100%" height="100%" filter={`url(#${id}-paper)`} />
      </svg>
      {failed ? (
        <div className="ink-load-error" role="alert">
          <p>墨迹素材未能加载</p>
          <button type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
        </div>
      ) : (
        <svg
          className="ink-stage"
          viewBox="480 215 740 495"
          role="img"
          aria-label={sceneLabel}
          style={{ opacity: ready ? 1 : 0 }}
        >
          <defs>
            <image id={`${id}-art`} href={ART} width="1672" height="941" />
            <filter id={`${id}-ink`} colorInterpolationFilters="sRGB">
              <feColorMatrix
                type="matrix"
                values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -.333333 -.333333 -.333333 0 1"
              />
            </filter>
            <filter id={`${id}-seal-ink`} colorInterpolationFilters="sRGB">
              <feColorMatrix
                type="matrix"
                values="0 0 0 0 .66  0 0 0 0 .09  0 0 0 0 .08  0 -1.3 0 0 1.274"
              />
            </filter>
            <clipPath id={`${id}-seal`}>
              <rect x="1092" y="505" width="50" height="66" />
            </clipPath>
            <clipPath id={`${id}-word`}>
              <path d="M533 278 H1098 V505 H1092 V572 H533 Z" />
            </clipPath>
            <linearGradient
              id={`${id}-sweep`}
              gradientUnits="userSpaceOnUse"
              x1={matureX}
              x2={Math.max(matureX + 0.01, sweepX)}
            >
              <stop stopColor="white" />
              <stop offset="1" stopColor={`rgb(${freshInk},${freshInk},${freshInk})`} />
            </linearGradient>
            <mask
              id={`${id}-reveal`}
              maskUnits="userSpaceOnUse"
              x="533"
              y="278"
              width="565"
              height="294"
            >
              <rect
                x="533"
                y="278"
                width={565 * progress}
                height="294"
                fill={matureProgress === 1 ? 'white' : `url(#${id}-sweep)`}
              />
              <rect x="598" y="286" width="17" height="18" fill="black" />
            </mask>
            {[
              { x: 638, y: 259, w: 27, h: 26 },
              { x: 598, y: 286, w: 16, h: 17 },
              { x: 1098, y: 438, w: 23, h: 23 },
              { x: 1124, y: 416, w: 12, h: 14 },
            ].map((dot, index) => (
              <clipPath key={index} id={`${id}-dot-${index}`}>
                <rect x={dot.x} y={dot.y} width={dot.w} height={dot.h} />
              </clipPath>
            ))}
          </defs>
          {DOTS.map((dot, index) => {
            const amount = settle(clamp((elapsed - 70 - (index % 5) * 75) / 340));
            return (
              <path
                key={`splash-${index}`}
                d="M-1-.75 C-.55-1.2 .42-1 .86-.53 L1 .12 .62 .8 -.14 1 -.84 .46 -1.08-.15 Z"
                transform={`translate(${dot.x} ${dot.y}) rotate(${index * 47}) scale(${dot.r * (0.6 + 0.4 * amount)})`}
                fill="#272a29"
                opacity={dot.opacity * amount}
              />
            );
          })}
          {[
            { x: 651, y: 272, delay: 40 },
            { x: 606, y: 295, delay: 170 },
            { x: 1109, y: 449, delay: 260 },
            { x: 1130, y: 423, delay: 340 },
          ].map((dot, index) => {
            const amount = settle(clamp((elapsed - dot.delay) / 210));
            return (
              <g
                key={index}
                opacity={amount}
                transform={`translate(${dot.x} ${dot.y}) scale(${0.45 + amount * 0.55}) translate(${-dot.x} ${-dot.y})`}
              >
                <use
                  href={`#${id}-art`}
                  clipPath={`url(#${id}-dot-${index})`}
                  filter={`url(#${id}-ink)`}
                />
              </g>
            );
          })}
          <g clipPath={`url(#${id}-word)`} mask={`url(#${id}-reveal)`}>
            <use href={`#${id}-art`} filter={`url(#${id}-ink)`} />
          </g>
          {seal > 0 && (
            <g
              opacity={settle(clamp(seal / 0.54))}
              transform={`translate(1117 538) scale(${sealScale}) rotate(${-1.2 * (1 - seal)}) translate(-1117 -538)`}
            >
              <use
                href={`#${id}-art`}
                clipPath={`url(#${id}-seal)`}
                filter={`url(#${id}-seal-ink)`}
              />
            </g>
          )}
        </svg>
      )}
      {ready && !failed && <InkProgressStroke progress={entranceProgress} art={ART} />}
      {!failed && (
        <div
          className="ink-loading"
          role="progressbar"
          aria-label="入场进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percentage}
        >
          <span className="ink-loading-number">
            {String(percentage).padStart(2, '0')}
            <span className="ink-loading-unit">%</span>
          </span>
          <span className="ink-loading-caption">
            {percentage === 100 ? '准备就绪' : '正在进入'}
          </span>
        </div>
      )}
    </main>
  );
}
