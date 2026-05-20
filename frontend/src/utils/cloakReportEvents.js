/**
 * Meta 标准事件与斗篷上报校验（与后端 app/schemas/cloak.py 一致）。
 */

export const CLOAK_REPORT_EVENTS = [
  { value: 'PageView', label: 'PageView（页面浏览）' },
  { value: 'ViewContent', label: 'ViewContent（查看内容）' },
  { value: 'Search', label: 'Search（搜索）' },
  { value: 'AddToCart', label: 'AddToCart（加入购物车）' },
  { value: 'AddToWishlist', label: 'AddToWishlist（加入心愿单）' },
  { value: 'AddPaymentInfo', label: 'AddPaymentInfo（填写支付信息）' },
  { value: 'InitiateCheckout', label: 'InitiateCheckout（发起结账）' },
  { value: 'Purchase', label: 'Purchase（购买）' },
  { value: 'Lead', label: 'Lead（潜在客户）' },
  { value: 'CompleteRegistration', label: 'CompleteRegistration（完成注册）' },
  { value: 'Contact', label: 'Contact（发起联系）' },
  { value: 'Subscribe', label: 'Subscribe（订阅）' },
  { value: 'StartTrial', label: 'StartTrial（开始试用）' },
  { value: 'SubmitApplication', label: 'SubmitApplication（提交申请）' },
  { value: 'Schedule', label: 'Schedule（预约）' },
  { value: 'FindLocation', label: 'FindLocation（查找位置）' },
  { value: 'Donate', label: 'Donate（捐赠）' },
  { value: 'CustomizeProduct', label: 'CustomizeProduct（定制商品）' },
];

export const FACEBOOK_STANDARD_EVENT_SET = new Set(
  CLOAK_REPORT_EVENTS.map((o) => o.value),
);

export const CLOAK_CUSTOM_REPORT_EVENT_RE = /^[A-Za-z][A-Za-z0-9_]{1,62}$/;

export function validateReportEventName(_rule, value, callback) {
  const v = (value || '').trim();
  if (!v) {
    callback(new Error('请选择或输入上报事件'));
    return;
  }
  if (FACEBOOK_STANDARD_EVENT_SET.has(v) || CLOAK_CUSTOM_REPORT_EVENT_RE.test(v)) {
    callback();
    return;
  }
  callback(
    new Error(
      '须为 Meta 标准事件名，或字母开头的自定义名（仅字母、数字、下划线，2～64 字符）',
    ),
  );
}

export function reportEventCellLabel(code) {
  const raw = (code || '').trim();
  if (!raw) return '-';
  const hit = CLOAK_REPORT_EVENTS.find((o) => o.value === raw);
  if (hit) return hit.label;
  return `${raw}（自定义）`;
}

export function rowIsUsable(row) {
  return row && (row.is_usable === true || row.bridge_html_present === true);
}

export function maskToken(token) {
  if (!token) return '-';
  if (token.length <= 10) return '******';
  return `${token.slice(0, 6)}******${token.slice(-4)}`;
}

export function formatJson(value) {
  if (!value) return '-';
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}
