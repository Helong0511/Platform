/**
 * 工具模块 - 转化总览字段格式化
 * @file utils/conversionSummaryFormat.js
 */
import { ElMessage } from 'element-plus';

/** 当月首日与末日（YYYY-MM-DD，本地时区） */
export function getDefaultMonthDateRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
  const formatDate = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };
  return [formatDate(start), formatDate(end)];
}

/** 客户侧转化数展示（受 Cap 限制） */
export function getDisplayConversion(conversions, cap, isAdmin) {
  if (!isAdmin && cap > 0) {
    return Math.min(conversions, cap);
  }
  return conversions;
}

/** Element Plus 表格汇总行 */
export function buildConversionTableSummaries(param, summaryData, isAdmin) {
  const { columns, data } = param;
  const sums = [];
  const totalClicks = data.reduce((sum, item) => sum + (Number(item.click_count) || 0), 0);
  const totalConversions = summaryData.total_conversions || 0;
  const totalCr = totalClicks > 0 ? ((totalConversions / totalClicks) * 100).toFixed(2) : '0.00';
  const totalPo = summaryData.total_po || 0;
  const totalPoAfterDiscount = summaryData.total_po_after_discount || 0;
  const totalProfit = summaryData.total_profit || 0;

  columns.forEach((column, index) => {
    const prop = column.property;
    if (!prop) {
      sums[index] = index === 0 ? '汇总' : '';
      return;
    }
    if (prop === 'click_count') sums[index] = totalClicks;
    else if (prop === 'conversion_count') sums[index] = totalConversions;
    else if (prop === 'cr') sums[index] = `${totalCr}%`;
    else if (prop === 'po' && isAdmin) sums[index] = totalPo.toFixed(2);
    else if (prop === 'po_after_discount') sums[index] = totalPoAfterDiscount.toFixed(2);
    else if (prop === 'profit' && isAdmin) sums[index] = totalProfit.toFixed(2);
    else sums[index] = '';
  });
  return sums;
}

/** 导出当前表格为 CSV（Excel 可打开） */
export function exportConversionStatsCsv(statsList, isAdmin) {
  if (!statsList?.length) {
    ElMessage.warning('没有数据可导出');
    return;
  }
  const headers = [
    'Offer ID',
    'Offer Name',
    'Advertiser',
    'Publisher',
    'Click',
    'Conversion',
    'CR',
    'Revenue',
    'Pub Revenue',
    'Profit',
    '上游单价',
    '下游单价',
    'GEO',
  ];
  const csvData = [headers.join(',')];
  statsList.forEach((row) => {
    csvData.push(
      [
        row.offer_id || '',
        `"${row.offer_name || ''}"`,
        `"${row.advertiser_name || ''}"`,
        `"${row.publisher_name || ''}"`,
        row.click_count || 0,
        row.conversion_count || 0,
        `${row.cr || 0}%`,
        isAdmin ? (row.po || 0).toFixed(2) : '',
        (row.po_after_discount || 0).toFixed(2),
        isAdmin ? (row.po ? (row.po - (row.po_after_discount || 0)).toFixed(2) : '0.00') : '',
        isAdmin ? (row.adv_po || 0).toFixed(2) : '',
        (row.pub_po || 0).toFixed(2),
        row.geo || '',
      ].join(','),
    );
  });
  const bom = '\ufeff';
  const blob = new Blob([bom + csvData.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `转化总览_${new Date().toISOString().slice(0, 10)}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  ElMessage.success('导出成功');
}
