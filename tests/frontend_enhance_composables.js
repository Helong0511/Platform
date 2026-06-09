/**
 * 为 composables 中 ref/reactive 状态字段补充行内中文注释
 */
import fs from 'fs';
import path from 'path';

const COMP = path.resolve('frontend/src/composables');
const STATE_HINTS = {
  loading: '数据加载中',
  tableData: '表格当前页数据',
  list: '列表数据',
  pagination: '分页状态 { page, pageSize/page_size, total }',
  searchForm: '筛选表单字段',
  searchKeyword: '关键词搜索',
  filterAdvertiser: '按广告主（上游）筛选',
  filterPublisher: '按渠道（下游）筛选',
  filterStatus: '按状态筛选',
  filterActive: '按激活状态筛选',
  advertiserList: '广告主下拉选项',
  publisherList: '渠道下拉选项',
  clientList: '客户下拉选项',
  productList: '产品下拉选项',
  offerList: 'Offer 下拉选项',
  form: '编辑表单数据',
  formData: '表单数据',
  dialogVisible: '弹窗显隐',
  visible: '面板/弹窗显隐',
  selectedRow: '当前选中行',
  currentId: '当前编辑记录 ID',
  detail: '详情数据',
  options: '下拉/配置选项',
  columns: '表格列配置',
  columnVisibility: '列显隐映射（持久化到 localStorage）',
  stats: '统计数据',
  records: '记录列表',
  total: '总条数',
  error: '错误信息',
  submitting: '提交中状态',
  isEdit: '是否为编辑模式',
};

let enhanced = 0;

for (const f of fs.readdirSync(COMP).filter((x) => x.endsWith('.js'))) {
  const fp = path.join(COMP, f);
  let lines = fs.readFileSync(fp, 'utf8').split('\n');
  let changed = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = line.match(/^(\s*)const\s+(\w+)\s*=\s*(ref|reactive)\s*\(/);
    if (!m) continue;
    const [, indent, name] = m;
    const prev = lines[i - 1] || '';
    const prev2 = lines[i - 2] || '';
    if (prev.trim().startsWith('//') || prev.trim().startsWith('*') || prev.includes('----')) continue;
    if (prev2.trim().startsWith('//')) continue;

    const hint = STATE_HINTS[name] || `${name} 响应式状态`;
    lines.splice(i, 0, `${indent}// ${hint}`);
    changed = true;
    i++;
  }

  if (changed) {
    fs.writeFileSync(fp, lines.join('\n'), 'utf8');
    enhanced++;
    console.log('enhanced:', f);
  }
}
console.log('composables enhanced:', enhanced);
