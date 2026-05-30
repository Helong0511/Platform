/**
 * Cron 表达式前端基本格式校验（详细语义由后端校验）。
 */
export function validateCronExpression(rule, value, callback) {
  if (!value) {
    callback(new Error('请输入Cron表达式'));
    return;
  }
  const trimmedValue = value.trim();
  const parts = trimmedValue.split(/\s+/);
  if (parts.length !== 5) {
    callback(
      new Error('Cron表达式格式错误：应为5个字段（分 时 日 月 星期），用空格分隔\n例如: 0 0 * * *'),
    );
    return;
  }
  const [minute, hour, day, month, weekday] = parts;
  if (!minute || !hour || !day || !month || !weekday) {
    callback(new Error('Cron表达式格式错误：每个字段不能为空'));
    return;
  }

  const fieldPattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+)$/;
  const monthPattern =
    /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$/i;
  const weekdayPattern =
    /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+|SUN|MON|TUE|WED|THU|FRI|SAT)$/i;
  const dayPattern = /^(\*|\?|\d+(-\d+)?(\/\d+)?|(\d+,)+\d+|L|LW|\d+W)$/;

  const checkNumeric = (field, min, max, label, pattern) => {
    if (pattern.test(field)) return true;
    const num = parseInt(field, 10);
    if (!Number.isNaN(num) && num >= min && num <= max) return true;
    callback(new Error(`${label}字段无效`));
    return false;
  };

  if (!checkNumeric(minute, 0, 59, '分钟', fieldPattern)) return;
  if (!checkNumeric(hour, 0, 23, '小时', fieldPattern)) return;
  if (!dayPattern.test(day) && (parseInt(day, 10) < 1 || parseInt(day, 10) > 31)) {
    callback(new Error('日期字段无效'));
    return;
  }
  if (!monthPattern.test(month) && (parseInt(month, 10) < 1 || parseInt(month, 10) > 12)) {
    callback(new Error('月份字段无效'));
    return;
  }
  if (!weekdayPattern.test(weekday) && (parseInt(weekday, 10) < 0 || parseInt(weekday, 10) > 7)) {
    callback(new Error('星期字段无效'));
    return;
  }
  callback();
}

export const SCHEDULED_TASK_EDIT_RULES = {
  task_name: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 1, max: 100, message: '任务名称长度在 1 到 100 个字符', trigger: 'blur' },
  ],
  cron_expression: [
    { required: true, message: '请输入Cron表达式', trigger: 'blur' },
    { validator: validateCronExpression, trigger: 'blur' },
  ],
};

/** 需要日期参数的手动触发任务名称 */
export const DATE_RELATED_TASK_NAMES = [
  'Addermobi API获取数据',
  'Skymobi API获取数据',
  'yangyangdeyi API获取数据',
  'zhisuo API获取数据',
  'TQT API获取数据',
];
