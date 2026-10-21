import { useEffect, useId, useRef, type CSSProperties } from 'react';

/** 采用已确认视觉稿的纯背景，书法、朱印与数字仍由独立动画绘制。 */
export function InkAtmosphere({ reducedMotion }: { reducedMotion: boolean }) {
  const id = useId().replaceAll(':', '');
  const noise = useRef<SVGFETurbulenceElement>(null);
  useEffect(() => {
    if (reducedMotion) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frameId: number;
    let previous = performance.now();
    let elapsed = 0;
    let painted = 0;
    const tick = (now: number) => {
      if (!document.hidden && !preference.matches) {
        elapsed += now - previous;
        // 20 fps 足够表现缓慢渗化，避免每帧重绘大幅背景。
        if (elapsed - painted >= 50) {
          const phase = (1 - Math.cos((elapsed / 12000) * Math.PI * 2)) / 2;
          noise.current?.setAttribute(
            'baseFrequency',
            `${0.006 + phase * 0.002} ${0.009 + phase * 0.002}`,
          );
          painted = elapsed;
        }
      }
      previous = now;
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [reducedMotion]);
  return (
    <div
      className={`ink-atmosphere${reducedMotion ? ' ink-atmosphere-still' : ''}`}
      aria-hidden="true"
      style={{ '--ink-flow-filter': `url(#${id}-flow)` } as CSSProperties}
    >
      <svg className="ink-wash-canvas" viewBox="0 0 1586 992" preserveAspectRatio="none">
        <defs>
          <filter
            id={`${id}-flow`}
            x="-5%"
            y="-5%"
            width="110%"
            height="110%"
            colorInterpolationFilters="sRGB"
          >
            <feTurbulence
              ref={noise}
              type="fractalNoise"
              baseFrequency="0.006 0.009"
              numOctaves="2"
              seed="8"
              result="current"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="current"
              scale="20"
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </defs>
        <image
          className="ink-wash-image"
          href="/intro/ink-wash-background.png"
          width="1586"
          height="992"
        />
      </svg>
    </div>
  );
}
