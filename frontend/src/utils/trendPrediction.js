/**
 * 趋势预测展示辅助：按预测步数动态解析「未来 N 分钟」对应索引。
 */

/** 与 getTrendPredict 默认 steps 一致，表示未来 1 小时（60 个 1 分钟步长） */
export const PREDICTION_HORIZON_MINUTES = 60

/**
 * 解析预测序列中「未来 horizonMinutes 分钟」对应的下标（0-based）。
 * 每个索引代表 1 分钟；步数不足时取 min(horizon, requestedSteps, seriesLength) 避免越界。
 *
 * @param {number} seriesLength 预测序列实际长度
 * @param {number} horizonMinutes 展示/读取的未来分钟数（默认 60）
 * @param {number} [requestedSteps] API 请求的预测步数；未传时以 seriesLength 为准
 */
export function resolvePredictionHorizonIndex(
  seriesLength,
  horizonMinutes = PREDICTION_HORIZON_MINUTES,
  requestedSteps,
) {
  if (!seriesLength || seriesLength < 1) {
    return -1
  }
  const availableSteps = requestedSteps != null
    ? Math.min(requestedSteps, seriesLength)
    : seriesLength
  const targetMinute = Math.min(horizonMinutes, availableSteps)
  return Math.max(0, targetMinute - 1)
}

/** 从预测序列中取出未来 horizonMinutes 分钟处的值 */
export function pickPredictionValue(
  series,
  horizonMinutes = PREDICTION_HORIZON_MINUTES,
  requestedSteps,
) {
  if (!Array.isArray(series) || !series.length) {
    return 0
  }
  const idx = resolvePredictionHorizonIndex(series.length, horizonMinutes, requestedSteps)
  if (idx < 0) {
    return 0
  }
  const value = series[idx]
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}
