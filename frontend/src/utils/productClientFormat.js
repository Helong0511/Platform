/**
 * 产品管理弹窗：客户名称与分配历史格式化工具。
 */
import { formatDate } from './dateFormat';

export function formatProductOptionLabel(product) {
  if (!product?.name) return '';

  const ownerName = product.user_full_name || product.full_name || '';
  if (!ownerName) {
    return product.name;
  }
  return `${ownerName} · ${product.name}`;
}

export function formatClientFullName(clientInfo) {
  if (!clientInfo) return '未知客户';

  const parts = [];
  if (clientInfo.company_name) parts.push(clientInfo.company_name);
  if (clientInfo.contact_person) parts.push(`(${clientInfo.contact_person})`);
  if (clientInfo.phone) parts.push(`- ${clientInfo.phone}`);

  return parts.length > 0 ? parts.join(' ') : '未知客户';
}

export function formatAssignmentDateRange(assignment) {
  if (assignment.end_date) {
    return `${formatDate(assignment.start_date)} - ${formatDate(assignment.end_date)}`;
  }
  return `${formatDate(assignment.start_date)} - 至今`;
}

export function formatAssignmentClientFullName(assignment) {
  if (!assignment) return '未知客户';

  if (assignment.user_full_name) {
    return assignment.user_full_name;
  }

  const parts = [];
  if (assignment.company_name) parts.push(assignment.company_name);
  if (assignment.contact_person) parts.push(`(${assignment.contact_person})`);
  if (assignment.phone) parts.push(`- ${assignment.phone}`);

  return parts.length > 0 ? parts.join(' ') : (assignment.client_name || '未知客户');
}

export function getTodayDateString() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getYesterdayDateString() {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const year = yesterday.getFullYear();
  const month = String(yesterday.getMonth() + 1).padStart(2, '0');
  const day = String(yesterday.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** 将 API 日期或 YYYY-MM-DD 规范为 YYYY-MM-DD（避免时区解析偏移） */
export function toDateStringOnly(value) {
  if (!value) return '';
  const str = String(value);
  return str.length >= 10 ? str.slice(0, 10) : str;
}

/** 在 YYYY-MM-DD 上加减天数，返回 YYYY-MM-DD */
export function addDaysToDateString(dateStr, days) {
  const normalized = toDateStringOnly(dateStr);
  if (!normalized) return '';
  const [year, month, day] = normalized.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + days);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}
