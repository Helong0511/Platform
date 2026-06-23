/**
 * 将 canvas 内部分辨率与 CSS 显示尺寸对齐，避免默认 300×150 被拉伸导致模糊。
 */

export function resolveCanvasDisplaySize(containerWidth, containerHeight, devicePixelRatio = 1) {
  const dpr = Math.max(1, devicePixelRatio || 1)
  const cssWidth = Math.max(0, Math.floor(containerWidth))
  const cssHeight = Math.max(0, Math.floor(containerHeight))
  return {
    cssWidth,
    cssHeight,
    bufferWidth: Math.floor(cssWidth * dpr),
    bufferHeight: Math.floor(cssHeight * dpr),
    dpr,
  }
}

export function applyCanvasDisplaySize(canvas, sizes) {
  canvas.width = sizes.bufferWidth
  canvas.height = sizes.bufferHeight
  canvas.style.width = `${sizes.cssWidth}px`
  canvas.style.height = `${sizes.cssHeight}px`
  const ctx = canvas.getContext('2d')
  ctx.setTransform(sizes.dpr, 0, 0, sizes.dpr, 0, 0)
  return ctx
}

/**
 * 按父容器尺寸准备 canvas，返回绘图上下文与逻辑宽高（CSS 像素）。
 * @returns {{ ctx: CanvasRenderingContext2D, width: number, height: number } | null}
 */
export function prepareCanvasForDisplay(canvas) {
  const container = canvas?.parentElement
  if (!container) {
    return null
  }
  const sizes = resolveCanvasDisplaySize(
    container.clientWidth,
    container.clientHeight,
    typeof window !== 'undefined' ? window.devicePixelRatio : 1,
  )
  if (!sizes.cssWidth || !sizes.cssHeight) {
    return null
  }
  const ctx = applyCanvasDisplaySize(canvas, sizes)
  return { ctx, width: sizes.cssWidth, height: sizes.cssHeight }
}

/**
 * 折线图第 index 个点的 X 坐标（逻辑像素）。
 * pointCount 为 0 或 1 时居中，避免 (pointCount - 1) 除零。
 */
export function lineChartIndexToX(index, pointCount, padding, chartWidth) {
  if (pointCount <= 1) {
    return padding + chartWidth / 2
  }
  return padding + (index / (pointCount - 1)) * chartWidth
}
