/**
 * 转化扣减配置展示格式化
 * @file utils/conversionDeductionFormat.js
 *
 * 将扣减层级、状态等枚举值转为中文标签与 Element Plus 标签颜色。
 */

/** 扣减层级 → 中文标签 */
export function getLevelLabel(level) {
  const map = {
    advertiser: '广告主',
    offer: 'Offer',
    publisher: '渠道',
  };
  return map[level] || level;
}

export function getLevelTagType(level) {
  const map = {
    advertiser: 'primary',
    offer: 'success',
    publisher: 'warning',
  };
  return map[level] || '';
}

/**
 * 转化扣量策略的中文展示名。
 */
export function getStrategyLabel(strategy) {
  const map = {
    random: '随机',
    proportional: '按比例',
    round_robin: '轮询',
  };
  return map[strategy] || strategy;
}
