import { useId } from 'react';

export function InkAtmosphere({ reducedMotion }: { reducedMotion: boolean }) {
  const id = useId().replaceAll(':', '');
  return (
    <svg
      className="ink-atmosphere ink-atmosphere-blocks"
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <filter
          id={`${id}-soft-edge`}
          x="-20%"
          y="-20%"
          width="140%"
          height="140%"
          colorInterpolationFilters="sRGB"
        >
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.008 0.012"
            numOctaves="2"
            seed="12"
            result="edge"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="edge"
            scale="42"
            xChannelSelector="R"
            yChannelSelector="G"
          >
            {!reducedMotion && (
              <animate attributeName="scale" values="30;62;30" dur="14s" repeatCount="indefinite" />
            )}
          </feDisplacementMap>
          <feGaussianBlur stdDeviation="2.4" />
        </filter>
      </defs>
      <rect width="1440" height="900" fill="#b5ae95" opacity="0.13" />
      <g className="ink-block ink-block-first" filter={`url(#${id}-soft-edge)`}>
        <path
          d="M-200-160 H750 C764-22 658 54 504 128 C434 166 465 255 335 296 C230 329 190 241 94 346 C-3 451-142 438-200 360Z"
          fill="#8c9280"
          opacity="0.24"
        />
        <path
          d="M938-175 H1630 V445 C1482 535 1353 455 1279 351 C1199 240 1082 304 1018 236 C958 173 1044 95 938-175Z"
          fill="#a5a38b"
          opacity="0.21"
        />
      </g>
      <g className="ink-block ink-block-second" filter={`url(#${id}-soft-edge)`}>
        <path
          d="M-230 423 C-55 329 135 423 224 486 C317 552 484 479 552 568 C628 668 431 705 375 787 C336 848 435 991 222 1060 H-230Z"
          fill="#a6a18b"
          opacity="0.26"
        />
        <path
          d="M851 502 C955 430 1031 514 1114 492 C1274 451 1459 531 1616 634 V1090 H709 C645 951 829 880 770 768 C713 660 734 583 851 502Z"
          fill="#929985"
          opacity="0.25"
        />
      </g>
      <g className="ink-block ink-block-third" filter={`url(#${id}-soft-edge)`}>
        <path
          d="M343 135 C464 79 568 206 731 144 C885 86 975 207 881 300 C791 389 939 444 850 516 C768 582 613 510 539 548 C377 630 325 518 394 428 C462 340 240 261 343 135Z"
          fill="#b4ad95"
          opacity="0.17"
        />
        <path
          d="M104 666 C227 573 301 699 441 650 C563 609 649 719 579 780 C483 864 674 897 598 1017 H86 C-16 876 18 731 104 666Z"
          fill="#818d7e"
          opacity="0.12"
        />
      </g>
    </svg>
  );
}
