/**
 * Offer 下游 Tracklink / 短链参数拼接（纯函数）。
 */

function resolveShortLinkBase(url) {
  let base = (url || '').trim();
  if (!base) return null;
  if (base.startsWith('/s/')) {
    base = `${window.location.origin}${base}`;
  }
  return base;
}

export function buildPublisherShortLink(offer, publisherId) {
  const main = resolveShortLinkBase(offer?.downstream_tracklink);
  if (!main || !main.includes('/s/') || !offer?.id || !publisherId) {
    return null;
  }
  const cleanBase = main.split('?')[0];
  return `${cleanBase}?offer_id=${offer.id}&channel_id=${publisherId}`;
}

export function buildPublisherTracklinkTemplate(offer, publisherId) {
  if (!offer?.downstream_tracklink || !publisherId) {
    return null;
  }
  return offer.downstream_tracklink.replace('{publisher_id}', publisherId);
}

export function findClientPublisher(publishers, clientId) {
  if (!publishers?.length || clientId == null) {
    return null;
  }
  return publishers.find((pub) => pub.client_id === clientId) || null;
}

export function getRowClientPublisherPO(row, clientId) {
  const pub = findClientPublisher(row?.assigned_publishers, clientId);
  return pub?.affiliate_payout ?? null;
}

export function getRowClientPublisherCap(row, clientId) {
  const pub = findClientPublisher(row?.assigned_publishers, clientId);
  return pub?.downstream_cap ?? null;
}

export function getRowClientPublisherTracklink(row, clientId) {
  const pub = findClientPublisher(row?.assigned_publishers, clientId);
  if (!pub || !row?.downstream_tracklink) {
    return null;
  }
  return buildPublisherShortLink(row, pub.id);
}

export function getClientPublisherPO(offer, clientId) {
  const pub = findClientPublisher(offer?.assigned_publishers, clientId);
  return pub?.affiliate_payout ?? null;
}

export function getClientPublisherCap(offer, clientId) {
  const pub = findClientPublisher(offer?.assigned_publishers, clientId);
  return pub?.downstream_cap ?? null;
}

export function getClientPublisherTracklinkSync(offer, clientId) {
  const pub = findClientPublisher(offer?.assigned_publishers, clientId);
  if (!pub) {
    return null;
  }
  return buildPublisherShortLink(offer, pub.id);
}
