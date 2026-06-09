/**
 * 短链 / Offer Tracklink 占位符校验（与后端 validate_track_url_placeholders 规则一致）
 */
const SUPPORTED_CANONICAL = new Set([
  'click_id', 'ip', 'os', 'device_type', 'country', 'user_agent', 'referer',
  'accept_language', 'language', 'lang', 'gaid', 'idfa', 'devad_id',
  'offer_id', 'offer_name', 'advertiser_offer_id', 'offer_payout', 'affiliate_payout',
  'offer_country', 'offer_category', 'offer_type', 'offer_status',
  'publisher_id', 'channel_id', 'publisher_name', 'publisher_email',
  'advertiser_id', 'advertiser_name', 'advertiser_email',
]);

const ALIAS_TO_CANONICAL = {
  clickid: 'click_id',
  clickId: 'click_id',
  clk_id: 'click_id',
  cid: 'click_id',
  aff_click_id: 'click_id',
  affclickid: 'click_id',
  publisherId: 'publisher_id',
  publisherid: 'publisher_id',
  channelId: 'channel_id',
  channelid: 'channel_id',
  sub_affid: 'channel_id',
  subaffid: 'channel_id',
  subid: 'channel_id',
  sub_id: 'channel_id',
  offerId: 'offer_id',
  offerid: 'offer_id',
  payout: 'offer_payout',
  gaid: 'gaid',
  idfa: 'idfa',
  client_ip: 'ip',
  clientip: 'ip',
  client_user_agent: 'user_agent',
  clientuseragent: 'user_agent',
  client_language: 'accept_language',
  clientlanguage: 'accept_language',
  language: 'accept_language',
  lang: 'accept_language',
  device_id: 'device_type',
  devad_id: 'gaid',
};

const DOUBLE_RE = /\{\{([^{}]+)\}\}/g;
const SINGLE_RE = /\{([^{}]+)\}/g;

export const PLACEHOLDER_HINT =
  '支持 {click_id}、{payout}、{GAID}、{IDFA}、{CLIENT IP}、{CLIENT USER AGENT}、{CLIENT LANGUAGE} 等；'
  + '支持 {name} 与 {{name}}；不支持三层花括号 {{{name}}}';

function normalizeName(name) {
  if (!name) return name;
  let n = String(name).trim();
  n = n.replace(/[\s\-.]+/g, '_');
  const low = n.toLowerCase();
  if (ALIAS_TO_CANONICAL[low]) return ALIAS_TO_CANONICAL[low];
  if (ALIAS_TO_CANONICAL[n]) return ALIAS_TO_CANONICAL[n];
  return n.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '');
}

function canonicalName(raw) {
  const n = normalizeName(raw);
  if (n === 'channel_id' || n === 'sub_affid') return 'publisher_id';
  return n;
}

function isSupported(raw) {
  const c = canonicalName(raw);
  return SUPPORTED_CANONICAL.has(c);
}

function findNamedPlaceholders(text) {
  const seen = new Set();
  const names = [];
  let m;
  DOUBLE_RE.lastIndex = 0;
  while ((m = DOUBLE_RE.exec(text)) !== null) {
    if (!seen.has(m[1])) {
      seen.add(m[1]);
      names.push(m[1]);
    }
  }
  SINGLE_RE.lastIndex = 0;
  while ((m = SINGLE_RE.exec(text)) !== null) {
    const start = m.index;
    if (start > 0 && text[start - 1] === '{') continue;
    const end = start + m[0].length;
    if (end < text.length && text[end] === '}') continue;
    if (!seen.has(m[1])) {
      seen.add(m[1]);
      names.push(m[1]);
    }
  }
  return names;
}

function stripTokens(text, names) {
  let out = text;
  for (const name of names) {
    out = out.split(`{{${name}}}`).join('');
    out = out.split(`{${name}}`).join('');
  }
  return out;
}

function findMalformedSnippets(remainder) {
  const re = /\{\{?[^{}]*\}\}?|\{[^{}]*\}|\{|\}/g;
  const bad = [];
  let m;
  while ((m = re.exec(remainder)) !== null) {
    const s = m[0];
    if (s === '{' || s === '}') {
      bad.push(s);
      continue;
    }
    const inner = s.replace(/^\{+|\}+$/g, '').trim();
    const normalized = normalizeName(inner);
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(normalized)) {
      bad.push(s.slice(0, 80));
    }
  }
  return [...new Set(bad)];
}

/**
 * 校验短链 original_url 中占位符语法及与 offer_id/channel_id 的一致性。
 * @returns {{ ok: boolean, errors: string[], warnings: string[] }}
 */
export function validateShortLinkPlaceholders(url, { offerId = null, channelId = null } = {}) {
  const errors = [];
  const warnings = [];
  if (!url || !String(url).trim()) {
    return { ok: true, errors, warnings };
  }
  const text = String(url).trim();

  if (text.includes('{{{') || text.includes('}}}')) {
    errors.push('占位符仅支持 {name} 或 {{name}}，不支持三层花括号');
  }

  const names = findNamedPlaceholders(text);
  const unknown = names.filter((n) => !isSupported(n));
  if (unknown.length) {
    errors.push(
      `不支持的占位符：${unknown.map((n) => `{${n}}`).join('、')}。${PLACEHOLDER_HINT}`,
    );
  }

  const remainder = stripTokens(text, names);
  const malformed = findMalformedSnippets(remainder);
  if (malformed.length) {
    errors.push(
      `URL 中存在无法解析的花括号片段：${malformed.map((s) => `'${s}'`).join('、')}。请检查拼写或非法字符`,
    );
  }

  const canonicalUsed = new Set(names.map((n) => canonicalName(n)));
  const offerRelated = [
    'offer_id', 'offer_name', 'advertiser_offer_id', 'offer_payout', 'affiliate_payout',
    'advertiser_id', 'advertiser_name',
  ];
  const pubRelated = ['publisher_id', 'channel_id', 'publisher_name'];
  if ([...canonicalUsed].some((c) => offerRelated.includes(c)) && !offerId) {
    warnings.push('含 Offer 相关占位符但未关联 Offer，运行时可能为空');
  }
  if ([...canonicalUsed].some((c) => pubRelated.includes(c)) && !channelId && !offerId) {
    warnings.push('含渠道占位符但未关联渠道/Offer，运行时可能为空');
  }

  return { ok: errors.length === 0, errors, warnings };
}
