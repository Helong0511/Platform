/**
 * Offer 下游 Tracklink / 短链参数拼接
 * @file utils/offerTracklink.js
 *
 * 纯函数工具，根据 Offer 与渠道 ID 生成下游追踪链接或模板。
 */
function resolveShortLinkBase(url) {
  let base = (url || '').trim();
  if (!base) return null;
  if (base.startsWith('/s/')) {
    base = `${window.location.origin}${base}`;
  }
  return base;
}

/**
 * 构建渠道专属短链接（含 offer_id 与 channel_id 参数）
 * @param {Object} offer - Offer 对象
 * @param {number|string} publisherId - 渠道 ID
 * @returns {string|null} 完整短链接 URL
 */
export function buildPublisherShortLink(offer, publisherId) {
  const main = resolveShortLinkBase(offer?.downstream_tracklink);
  if (!main || !main.includes('/s/') || !offer?.id || !publisherId) {
    return null;
  }
  const cleanBase = main.split('?')[0];
  return `${cleanBase}?offer_id=${offer.id}&channel_id=${publisherId}`;
}

/**
 * 构建Publisher Tracklink Template。
 */
export function buildPublisherTracklinkTemplate(offer, publisherId) {
  if (!offer?.downstream_tracklink || !publisherId) {
    return null;
  }
  return offer.downstream_tracklink.replace('{publisher_id}', publisherId);
}

/**
 * findClientPublisher 接口。
 */
export function findClientPublisher(publishers, clientId) {
  if (!publishers?.length || clientId == null) {
    return null;
  }
  return publishers.find((pub) => pub.client_id === clientId) || null;
}

/**
 * 从表格行读取客户-渠道 PO 单价。
 */
export function getRowClientPublisherPO(row, clientId) {
  const pub = findClientPublisher(row?.assigned_publishers, clientId);
  return pub?.affiliate_payout ?? null;
}

/**
 * 从表格行读取客户-渠道 Cap 上限。
 */
export function getRowClientPublisherCap(row, clientId) {
  const pub = findClientPublisher(row?.assigned_publishers, clientId);
  return pub?.downstream_cap ?? null;
}

/**
 * 从表格行读取客户-渠道 Tracklink。
 */
export function getRowClientPublisherTracklink(row, clientId) {
  const pub = findClientPublisher(row?.assigned_publishers, clientId);
  if (!pub || !row?.downstream_tracklink) {
    return null;
  }
  return buildPublisherShortLink(row, pub.id);
}

/**
 * 获取客户-渠道 PO 单价（异步）。
 */
export function getClientPublisherPO(offer, clientId) {
  const pub = findClientPublisher(offer?.assigned_publishers, clientId);
  return pub?.affiliate_payout ?? null;
}

/**
 * 获取客户-渠道 Cap 配置（异步）。
 */
export function getClientPublisherCap(offer, clientId) {
  const pub = findClientPublisher(offer?.assigned_publishers, clientId);
  return pub?.downstream_cap ?? null;
}

/**
 * 同步获取客户-渠道 Tracklink。
 */
export function getClientPublisherTracklinkSync(offer, clientId) {
  const pub = findClientPublisher(offer?.assigned_publishers, clientId);
  if (!pub) {
    return null;
  }
  return buildPublisherShortLink(offer, pub.id);
}
