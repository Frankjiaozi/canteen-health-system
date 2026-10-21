// 透明水墨数字图集：两行六列；每格内缩去掉分隔边缘，按真实数字动态取字。
const ATLAS = '/intro/ink-numerals.png';
const CELL = 362;
const INSET = 8;

function Glyph({ index, x, percent = false }: { index: number; x: number; percent?: boolean }) {
  const left = (index % 6) * CELL + INSET;
  const top = Math.floor(index / 6) * CELL + INSET;
  return (
    <svg
      x={x}
      y={percent ? 31 : 9}
      width={percent ? 19 : 39}
      height={percent ? 19 : 39}
      viewBox={`${left} ${top} ${CELL - INSET * 2} ${CELL - INSET * 2}`}
      preserveAspectRatio="xMidYMid meet"
      overflow="hidden"
    >
      <image href={ATLAS} width="2172" height="724" />
    </svg>
  );
}

export function InkLoadingNumber({ value }: { value: number }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const image = new Image();
    image.src = ATLAS;
    void image
      .decode()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch(() => {
        // 图片慢或不可用时仍显示真实数字，不阻塞入场。
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const digits = String(value).padStart(2, '0');
  const offset = (142 - (digits.length * 39 + 22)) / 2;
  return (
    <span className="ink-loading-number">
      <span className="ink-loading-readable">{digits}%</span>
      <svg viewBox="0 0 142 64" aria-hidden="true">
        {ready ? (
          <>
            {digits.split('').map((digit, index) => (
              <Glyph key={index} index={Number(digit)} x={offset + index * 39} />
            ))}
            <Glyph index={10} x={offset + digits.length * 39} percent />
          </>
        ) : (
          <text
            x="71"
            y="49"
            textAnchor="middle"
            fill="currentColor"
            fontFamily="KaiTi, STKaiti, serif"
            fontSize="44"
          >
            {digits}%
          </text>
        )}
      </svg>
    </span>
  );
}
import { useEffect, useState } from 'react';
