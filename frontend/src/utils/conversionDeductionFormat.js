/** 转化扣减配置展示文案 */

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

export function getStrategyLabel(strategy) {
  const map = {
    random: '随机',
    proportional: '按比例',
    round_robin: '轮询',
  };
  return map[strategy] || strategy;
}
