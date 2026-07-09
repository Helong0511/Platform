/**
 * XSS防护工具模块
 * 
 * 功能说明：
 * - 提供输入验证和XSS攻击防护
 * - 支持HTML内容过滤和转义
 * - 提供DOM安全操作方法
 * - 支持白名单标签和属性过滤
 * 
 * 安全特性：
 * - 自动转义HTML特殊字符
 * - 过滤危险HTML标签和属性
 * - 防止JavaScript代码注入
 * - 防止CSS表达式攻击
 * 
 * @module utils/xssFilter
 */

/**
 * HTML特殊字符转义映射表
 */
const HTML_ESCAPE_MAP = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#x27;',
  '/': '&#x2F;',
  '`': '&#x60;',
  '=': '&#x3D;'
};

/**
 * HTML特殊字符反转义映射表
 */
const HTML_UNESCAPE_MAP = {};
Object.keys(HTML_ESCAPE_MAP).forEach(key => {
  HTML_UNESCAPE_MAP[HTML_ESCAPE_MAP[key]] = key;
});

/**
 * 需整棵移除、不可保留子节点的危险标签（含文本子节点也会执行/注入）
 */
const DROP_TAGS_ENTIRELY = new Set([
  'script', 'style', 'iframe', 'object', 'embed', 'link', 'meta', 'noscript', 'template'
]);

/**
 * 允许的HTML标签白名单
 */
const ALLOWED_TAGS = [
  'a', 'abbr', 'acronym', 'address', 'article', 'aside', 'b', 'bdi', 'bdo',
  'blockquote', 'body', 'br', 'caption', 'cite', 'code', 'col', 'colgroup',
  'dd', 'del', 'details', 'dfn', 'div', 'dl', 'dt', 'em', 'fieldset',
  'figcaption', 'figure', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'header', 'hr', 'i', 'img', 'input', 'ins', 'kbd', 'label',
  'legend', 'li', 'main', 'mark', 'nav', 'ol',
  'optgroup', 'option', 'p', 'param', 'picture', 'pre', 'q', 's', 'samp',
  'section', 'select', 'small', 'source', 'span', 'strong',
  'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'textarea',
  'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track', 'u', 'ul', 'var', 'video'
];

/**
 * 允许的HTML属性白名单
 */
const ALLOWED_ATTRIBUTES = [
  'accept', 'accept-charset', 'accesskey', 'action', 'align', 'alt', 'async',
  'autocomplete', 'autofocus', 'autoplay', 'bgcolor', 'border', 'capture',
  'cellpadding', 'cellspacing', 'challenge', 'charset', 'checked', 'cite',
  'class', 'color', 'cols', 'colspan', 'content', 'contenteditable',
  'contextmenu', 'controls', 'coords', 'data-*', 'datetime', 'default',
  'defer', 'dir', 'dirname', 'disabled', 'download', 'draggable', 'dropzone',
  'enctype', 'for', 'form', 'formaction', 'formenctype', 'formmethod',
  'formnovalidate', 'formtarget', 'headers', 'height', 'hidden', 'high',
  'href', 'hreflang', 'http-equiv', 'icon', 'id', 'integrity', 'ismap',
  'itemprop', 'kind', 'label', 'lang', 'language', 'list', 'loop', 'low',
  'max', 'maxlength', 'media', 'method', 'min', 'multiple', 'muted',
  'name', 'novalidate', 'open', 'optimum', 'pattern', 'placeholder',
  'poster', 'preload', 'readonly', 'rel', 'required', 'reversed', 'rows',
  'rowspan', 'sandbox', 'scope', 'scoped', 'selected', 'shape', 'size',
  'sizes', 'span', 'spellcheck', 'src', 'srcdoc', 'srclang', 'srcset',
  'start', 'step', 'style', 'tabindex', 'target', 'title', 'translate',
  'type', 'usemap', 'value', 'width', 'wrap'
];

/**
 * 危险协议列表（拆分字面量，避免 ESLint no-script-url 误报）
 */
const JS_PROTO = 'java' + 'script:';
const VB_PROTO = 'vb' + 'script:';
const DANGEROUS_PROTOCOLS = [JS_PROTO, VB_PROTO, 'data:', 'file:', 'ftp:', 'blob:'];

/**
 * 危险事件处理属性
 */
const DANGEROUS_EVENTS = [
  'onclick', 'ondblclick', 'onmousedown', 'onmouseup', 'onmouseover',
  'onmousemove', 'onmouseout', 'onkeydown', 'onkeyup', 'onkeypress',
  'onload', 'onunload', 'onabort', 'onerror', 'onresize', 'onscroll',
  'onselect', 'onchange', 'onsubmit', 'onreset', 'onfocus', 'onblur',
  'onbeforeunload', 'onhashchange', 'oninput', 'oninvalid', 'onmessage',
  'onoffline', 'ononline', 'onpopstate', 'onprogress', 'onreadystatechange',
  'onstorage', 'onwheel', 'oncontextmenu', 'ondrag', 'ondragend',
  'ondragenter', 'ondragleave', 'ondragover', 'ondragstart', 'ondrop',
  'onshow', 'ontoggle', 'oncopy', 'oncut', 'onpaste'
];

/**
 * 转义HTML特殊字符
 * 
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
export function escapeHtml(str) {
  if (!str || typeof str !== 'string') {
    return str;
  }
  return str.replace(/[&<>"'`=/]/g, char => HTML_ESCAPE_MAP[char] || char);
}

/**
 * 反转义HTML特殊字符
 * 
 * @param {string} str - 转义后的字符串
 * @returns {string} 原始字符串
 */
export function unescapeHtml(str) {
  if (!str || typeof str !== 'string') {
    return str;
  }
  return str.replace(/&[^;]+;/g, entity => HTML_UNESCAPE_MAP[entity] || entity);
}

/**
 * 验证URL安全性
 * 
 * @param {string} url - 待验证的URL
 * @returns {boolean} 是否安全
 */
export function isUrlSafe(url) {
  if (!url || typeof url !== 'string') {
    return false;
  }
  
  const lowerUrl = url.toLowerCase().trim();
  
  // 检查危险协议
  for (const protocol of DANGEROUS_PROTOCOLS) {
    if (lowerUrl.startsWith(protocol)) {
      return false;
    }
  }
  
  // 检查javascript伪协议的其他形式
  if (lowerUrl.includes('javascript') || lowerUrl.includes('vbscript')) {
    // 检查是否是真正的URL（包含://）
    if (!lowerUrl.includes('://')) {
      return false;
    }
    // 检查是否是javascript:协议的变体
    if (lowerUrl.match(/javascript\s*:/i)) {
      return false;
    }
  }
  
  return true;
}

/** 无子节点的 void 元素，序列化时使用自闭合形式 */
const VOID_ELEMENTS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
  'meta', 'param', 'source', 'track', 'wbr',
]);

/** style 属性值中禁止出现的危险片段 */
const DANGEROUS_STYLE_VALUE = /expression|javascript|vbscript|behavior|-moz-binding|-ms-behavior|@import|<|>|\\|`/i;

/**
 * 使用 DOMParser 解析 HTML（不挂载到活动文档，避免 innerHTML 解析阶段的副作用）
 * @param {string} html
 * @returns {HTMLElement} 包裹解析结果的临时容器
 */
function parseHtmlToContainer(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const container = document.createElement('div');
  while (doc.body.firstChild) {
    container.appendChild(doc.body.firstChild);
  }
  return container;
}

/**
 * 将过滤后的 DOM 节点序列化为 HTML 字符串（属性值与文本均转义，避免 innerHTML 往返引入风险）
 * @param {Node} node
 * @returns {string}
 */
function serializeNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    return escapeHtml(node.textContent);
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return '';
  }

  const tagName = node.tagName.toLowerCase();
  const attrParts = [];
  for (const attr of node.attributes) {
    attrParts.push(`${attr.name}="${escapeHtml(attr.value)}"`);
  }
  const attrStr = attrParts.length ? ` ${attrParts.join(' ')}` : '';

  if (VOID_ELEMENTS.has(tagName)) {
    return `<${tagName}${attrStr}>`;
  }

  const children = Array.from(node.childNodes).map(serializeNode).join('');
  return `<${tagName}${attrStr}>${children}</${tagName}>`;
}

function serializeContainerChildren(container) {
  return Array.from(container.childNodes).map(serializeNode).join('');
}

/**
 * 过滤HTML内容（移除危险标签和属性）
 * 
 * @param {string} html - 原始HTML内容
 * @param {Object} options - 过滤选项
 * @param {string[]} options.allowedTags - 允许的标签列表
 * @param {string[]} options.allowedAttributes - 允许的属性列表
 * @param {boolean} options.stripUnknownTags - 是否移除未知标签（默认true）
 * @returns {string} 过滤后的HTML内容
 */
export function filterHtml(html, options = {}) {
  if (!html || typeof html !== 'string') {
    return html;
  }
  
  const {
    allowedTags = ALLOWED_TAGS,
    allowedAttributes = ALLOWED_ATTRIBUTES,
    stripUnknownTags = true
  } = options;
  
  const container = parseHtmlToContainer(html);
  
  // 危险标签整棵移除；可剥离标签先过滤子树再提升子节点，避免未过滤内容外泄
  const filterElementAttributes = (node) => {
    const attributes = Array.from(node.attributes);
    for (const attr of attributes) {
      const attrName = attr.name.toLowerCase();

      if (DANGEROUS_EVENTS.includes(attrName)) {
        node.removeAttribute(attr.name);
        continue;
      }

      const isAllowed = allowedAttributes.includes(attrName) ||
        attrName.startsWith('data-') ||
        attrName.startsWith('aria-');

      if (!isAllowed) {
        node.removeAttribute(attr.name);
        continue;
      }

      if (attrName === 'href' || attrName === 'src' || attrName === 'action') {
        if (!isUrlSafe(attr.value)) {
          node.removeAttribute(attr.name);
        }
      }

      if (attrName === 'style') {
        const safeStyle = filterStyle(attr.value);
        // 危险样式全部剔除后移除 style 属性（预期行为，避免留空或残留未转义内容）
        node.removeAttribute(attr.name);
        if (safeStyle) {
          node.setAttribute('style', safeStyle);
        }
      }
    }
  };

  const filterNode = (node) => {
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return;
    }

    const tagName = node.tagName.toLowerCase();

    if (!allowedTags.includes(tagName)) {
      if (DROP_TAGS_ENTIRELY.has(tagName)) {
        node.parentNode?.removeChild(node);
        return;
      }
      if (!stripUnknownTags) {
        let child = node.firstChild;
        while (child) {
          const nextChild = child.nextSibling;
          filterNode(child);
          child = nextChild;
        }
        filterElementAttributes(node);
        return;
      }
      let child = node.firstChild;
      while (child) {
        const nextChild = child.nextSibling;
        filterNode(child);
        child = nextChild;
      }
      const parent = node.parentNode;
      if (parent) {
        while (node.firstChild) {
          parent.insertBefore(node.firstChild, node);
        }
        parent.removeChild(node);
      }
      return;
    }

    let child = node.firstChild;
    while (child) {
      const nextChild = child.nextSibling;
      filterNode(child);
      child = nextChild;
    }

    filterElementAttributes(node);
  };
  
  filterNode(container);

  return serializeContainerChildren(container);
}

/** 仅拦截 IE/旧版浏览器 XSS 相关属性名（精确匹配，勿用 includes 误伤 filter/animation） */
const BLOCKED_STYLE_PROPERTY_NAMES = new Set([
  'behavior',
  '-moz-binding',
  'binding',
]);

/**
 * 校验单条 CSS 声明的值是否安全
 * @param {string} value
 * @returns {boolean}
 */
function isStyleDeclarationValueSafe(value) {
  if (!value || typeof value !== 'string') {
    return false;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }
  if (DANGEROUS_STYLE_VALUE.test(trimmed)) {
    return false;
  }
  // 内联 style 禁止 url()，避免 javascript:/data: 等协议注入
  if (/url\s*\(/i.test(trimmed)) {
    return false;
  }
  return true;
}

function isStylePropertyNameBlocked(key) {
  const lowerKey = key.trim().toLowerCase();
  if (BLOCKED_STYLE_PROPERTY_NAMES.has(lowerKey)) {
    return true;
  }
  // 历史 IE expression 属性（非标准，极少见）
  return lowerKey === 'expression' || lowerKey.endsWith('-expression');
}

/**
 * 过滤CSS样式（移除危险声明，保留 filter / animation / transition 等标准属性）
 *
 * @param {string} style - 原始CSS样式字符串
 * @returns {string} 过滤后的CSS样式
 */
export function filterStyle(style) {
  if (!style || typeof style !== 'string') {
    return '';
  }
  
  // 移除CSS表达式和javascript伪协议（[^;]* 覆盖 expression 内嵌套括号）
  let filtered = style
    .replace(/expression\s*\([^;]*/gi, '')
    .replace(/javascript\s*:/gi, '')
    .replace(/vbscript\s*:/gi, '')
    .replace(/@import\s+[^;]+/gi, '')
    .replace(/url\s*\(\s*['"]?\s*javascript:/gi, '')
    .replace(/url\s*\(\s*['"]?\s*data:/gi, '');
  
  const properties = filtered.split(';').map(p => p.trim()).filter(p => p);
  const safeProperties = [];
  
  for (const property of properties) {
    const colonIndex = property.indexOf(':');
    if (colonIndex === -1) continue;

    const key = property.slice(0, colonIndex).trim();
    const value = property.slice(colonIndex + 1).trim();
    if (!key || !value) continue;

    if (isStylePropertyNameBlocked(key)) {
      continue;
    }

    if (/expression|behavior|binding/i.test(value)) {
      continue;
    }

    if (!isStyleDeclarationValueSafe(value)) {
      continue;
    }
    
    safeProperties.push(`${key}: ${value}`);
  }
  
  return safeProperties.join('; ');
}

/**
 * 安全设置DOM元素的innerHTML
 * 
 * @param {HTMLElement} element - DOM元素
 * @param {string} html - HTML内容
 * @param {Object} options - 过滤选项
 */
export function setSafeInnerHTML(element, html, options = {}) {
  if (!element || !(element instanceof HTMLElement)) {
    return;
  }
  
  const filteredHtml = filterHtml(html, options);
  element.innerHTML = filteredHtml;
}

/**
 * 安全获取用户输入（自动转义）
 * 
 * @param {string} input - 用户输入
 * @returns {string} 转义后的输入
 */
export function sanitizeInput(input) {
  if (input === null || input === undefined) {
    return '';
  }
  
  if (typeof input !== 'string') {
    input = String(input);
  }
  
  return escapeHtml(input);
}

/**
 * 验证输入是否包含潜在危险内容
 * 
 * @param {string} input - 用户输入
 * @returns {Object} 验证结果
 * @returns {boolean} result.isSafe - 是否安全
 * @returns {string[]} result.issues - 发现的安全问题列表
 */
export function validateInput(input) {
  if (!input || typeof input !== 'string') {
    return { isSafe: true, issues: [] };
  }
  
  const issues = [];
  const lowerInput = input.toLowerCase();
  
  // 检查HTML标签
  if (/<[^>]+>/.test(input)) {
    issues.push('发现HTML标签');
  }
  
  // 检查 javascript / vbscript 协议
  if (lowerInput.includes(JS_PROTO) ||
      lowerInput.match(/java\s*script\s*:/)) {
    issues.push('发现JavaScript代码');
  }
  
  // 检查 vbscript 协议
  if (lowerInput.includes(VB_PROTO) ||
      lowerInput.match(/vb\s*script\s*:/)) {
    issues.push('发现VBScript代码');
  }
  
  // 检查data URI
  if (lowerInput.startsWith('data:') ||
      lowerInput.match(/data:\s*[^,]+,/)) {
    issues.push('发现data URI');
  }
  
  // 检查事件处理属性
  for (const event of DANGEROUS_EVENTS) {
    if (lowerInput.includes(event)) {
      issues.push(`发现事件处理属性: ${event}`);
      break;
    }
  }
  
  // 检查CSS表达式
  if (lowerInput.includes('expression(')) {
    issues.push('发现CSS表达式');
  }
  
  // 检查on*属性（更通用的检查）
  if (/on\w+\s*=/.test(lowerInput)) {
    issues.push('发现事件绑定');
  }
  
  return {
    isSafe: issues.length === 0,
    issues
  };
}

/**
 * 生成安全的URL参数
 * 
 * @param {Object} params - 参数对象
 * @returns {string} 安全的URL参数字符串
 */
export function buildSafeQueryString(params) {
  if (!params || typeof params !== 'object') {
    return '';
  }
  
  const safeParams = {};
  for (const key in params) {
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      safeParams[encodeURIComponent(key)] = encodeURIComponent(String(params[key]));
    }
  }
  
  return new URLSearchParams(safeParams).toString();
}

/**
 * Vue指令：v-safe-html
 * 
 * 提供安全的HTML渲染，自动过滤危险内容
 */
export const vSafeHtml = {
  mounted(el, binding) {
    setSafeInnerHTML(el, binding.value, binding.arg || {});
  },
  updated(el, binding) {
    if (binding.value !== binding.oldValue) {
      setSafeInnerHTML(el, binding.value, binding.arg || {});
    }
  }
};

/**
 * XSS防护工具类
 */
export class XSSFilter {
  /**
   * 转义HTML
   */
  static escape(str) {
    return escapeHtml(str);
  }
  
  /**
   * 反转义HTML
   */
  static unescape(str) {
    return unescapeHtml(str);
  }
  
  /**
   * 过滤HTML内容
   */
  static filter(html, options) {
    return filterHtml(html, options);
  }
  
  /**
   * 验证URL安全性
   */
  static isUrlSafe(url) {
    return isUrlSafe(url);
  }
  
  /**
   * 验证输入安全性
   */
  static validate(input) {
    return validateInput(input);
  }
  
  /**
   * 清理输入（转义特殊字符）
   */
  static sanitize(input) {
    return sanitizeInput(input);
  }
  
  /**
   * 安全设置innerHTML
   */
  static setInnerHTML(element, html, options) {
    return setSafeInnerHTML(element, html, options);
  }
  
  /**
   * 构建安全的查询字符串
   */
  static buildQueryString(params) {
    return buildSafeQueryString(params);
  }
}

export default XSSFilter;