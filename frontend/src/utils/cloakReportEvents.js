/**
 * Meta 标准事件与斗篷上报校验（与后端 app/schemas/cloak.py 一致）。
 */
export const CLOAK_TEST_REPORT_PHASES = [
  { value: 'postback', label: 'Postback 转化上报（转）', short: '转' },
  { value: 'click', label: '点击跳转上报（点）', short: '点' },
  { value: 'load', label: '加载完成上报（载）', short: '载' },
];

/**
 * 根据测试阶段从表格行读取对应的事件名、金额、货币（与后端 _resolve_test_report_params 一致）
 * @param {object|null} row 斗篷配置行
 * @param {'load'|'click'|'postback'} phase 上报阶段
 */
export function getTestPhaseEventMeta(row, phase) {
  if (!row) {
    return { event: '-', value: null, currency: 'USD' };
  }
  if (phase === 'load') {
    return {
      event: row.load_report_event || 'PageView',
      value: row.load_report_value,
      currency: row.load_report_currency || 'USD',
    };
  }
  if (phase === 'postback') {
    return {
      event: row.postback_report_event || 'Purchase',
      value: row.postback_report_value,
      currency: row.postback_report_currency || 'USD',
    };
  }
  return {
    event: row.report_event || 'ViewContent',
    value: row.report_value,
    currency: row.report_currency || 'USD',
  };
}

/**
 * 测试上报前校验：Purchase 须有效金额（postback 可留空走服务端测试默认）
 * @returns {string|null} 警告文案，null 表示可继续
 */
export function validateTestReportPhase(row, phase) {
  const { event, value } = getTestPhaseEventMeta(row, phase);
  if (event !== 'Purchase') {
    return null;
  }
  if (phase === 'postback' && (value == null || value === '')) {
    return null;
  }
  if (value == null || Number(value) <= 0) {
    const hit = CLOAK_TEST_REPORT_PHASES.find((o) => o.value === phase);
    return `当前为${hit?.label || phase}且事件为 Purchase，请先在编辑中保存有效金额后再测上报`;
  }
  return null;
}

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

/** Element Plus 表单校验器：Meta 标准事件或自定义事件命名规则 */
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

/** 列表「上报事件」列展示：标准事件显示中文说明，自定义事件标注「自定义」 */
export function reportEventCellLabel(code) {
  const raw = (code || '').trim();
  if (!raw) return '-';
  const hit = CLOAK_REPORT_EVENTS.find((o) => o.value === raw);
  if (hit) return hit.label;
  return `${raw}（自定义）`;
}

/** 斗篷是否可用：后端返回 is_usable 或 bridge_html_present 为真 */
export function rowIsUsable(row) {
  return row && (row.is_usable === true || row.bridge_html_present === true);
}

/** Token 脱敏展示（与后端 _mask_token 规则一致） */
export function maskToken(token) {
  if (!token) return '-';
  if (token.length <= 10) return '******';
  return `${token.slice(0, 6)}******${token.slice(-4)}`;
}

/** 测试上报结果 JSON 格式化，便于弹窗 pre 展示 */
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
