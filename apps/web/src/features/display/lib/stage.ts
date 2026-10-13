// 大屏基准分辨率与自适应缩放

export const STAGE_WIDTH = 1920;
export const STAGE_HEIGHT = 1080;

export interface StageLayout {
  // 相对基准分辨率的缩放系数
  scale: number;
  // 缩放后的居中偏移
  offsetX: number;
  offsetY: number;
}

// 按「等比缩放 + 居中」计算大屏版面。
//
// 大屏最怕溢出：内容超出浏览器视口会被截断，而现场没人会去调分辨率。
// 因此始终取宽高比例中较小的那个，保证 1920×1080 之外的任何分辨率都不溢出。
export function computeStageLayout(
  viewportWidth: number,
  viewportHeight: number,
  stageWidth: number = STAGE_WIDTH,
  stageHeight: number = STAGE_HEIGHT,
): StageLayout {
  if (viewportWidth <= 0 || viewportHeight <= 0) {
    return { scale: 1, offsetX: 0, offsetY: 0 };
  }

  const scale = Math.min(viewportWidth / stageWidth, viewportHeight / stageHeight);
  return {
    scale,
    offsetX: (viewportWidth - stageWidth * scale) / 2,
    offsetY: (viewportHeight - stageHeight * scale) / 2,
  };
}
