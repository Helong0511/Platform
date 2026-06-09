/**
 * 前端消息常量
 * 与后端错误消息保持一致，确保前后端消息的统一性
 * 
 * 使用方式：
 * import { getErrorMessage, getSuccessMessage } from '@/utils/messages';
 * 
 * // 错误消息（优先使用后端返回的detail或message）
 * const errorMsg = extractErrorMessage(error) || getErrorMessage('OPERATION_FAILED');
 * ElMessage.error(errorMsg);
 * 
 * // 成功消息
 * ElMessage.success(getSuccessMessage('CREATE_SUCCESS'));
 */
/** 操作类型与资源类型枚举常量 */
export const OperationType = {
  // 通用操作
  CREATE: 'CREATE',
  UPDATE: 'UPDATE',
  DELETE: 'DELETE',
  GET: 'GET',
  EXPORT: 'EXPORT',
  IMPORT: 'IMPORT',
  SAVE: 'SAVE',
  CANCEL: 'CANCEL',
  
  // 资源类型
  USER: 'USER',
  CLIENT: 'CLIENT',
  PRODUCT: 'PRODUCT',
  TASK: 'TASK',
  DATA: 'DATA',
  LOG: 'LOG',
  MAPPING: 'MAPPING',
};

/**
 * 成功消息映射
 */
const SUCCESS_MESSAGES = {
  // 通用成功消息
  'CREATE_SUCCESS': '创建成功',
  'UPDATE_SUCCESS': '更新成功',
  'DELETE_SUCCESS': '删除成功',
  'SAVE_SUCCESS': '保存成功',
  'OPERATION_SUCCESS': '操作成功',
  'EXPORT_SUCCESS': '导出成功',
  'IMPORT_SUCCESS': '导入成功',
  
  // 用户相关
  'USER_CREATE_SUCCESS': '用户创建成功',
  'USER_UPDATE_SUCCESS': '用户更新成功',
  'USER_DELETE_SUCCESS': '用户删除成功',
  'USER_EXPORT_SUCCESS': '用户数据导出成功',
  
  // 客户相关
  'CLIENT_CREATE_SUCCESS': '客户创建成功',
  'CLIENT_UPDATE_SUCCESS': '客户更新成功',
  'CLIENT_DELETE_SUCCESS': '客户删除成功',
  'CLIENT_EXPORT_SUCCESS': '客户数据导出成功',
  
  // 产品相关
  'PRODUCT_CREATE_SUCCESS': '产品创建成功',
  'PRODUCT_UPDATE_SUCCESS': '产品更新成功',
  'PRODUCT_DELETE_SUCCESS': '产品删除成功',
  
  // 定时任务相关
  'TASK_CREATE_SUCCESS': '定时任务创建成功',
  'TASK_UPDATE_SUCCESS': '定时任务更新成功',
  'TASK_TRIGGER_SUCCESS': '任务已触发，正在后台执行',
  'TASK_LOCK_RELEASED': '任务锁已释放',
  
  // 数据相关
  'DATA_UPDATE_SUCCESS': '数据更新成功',
  'DATA_EXPORT_SUCCESS': '数据导出成功',
  'DATA_IMPORT_SUCCESS': '数据导入成功',
  'DATA_DELETE_SUCCESS': '删除成功',
  'DATA_BATCH_DELETE_SUCCESS': (count) => `成功删除 ${count} 条数据`,
  
  // 映射相关
  'MAPPING_SAVE_SUCCESS': '映射规则保存成功',
  'MAPPING_VALIDATE_SUCCESS': '列名映射验证完成！',
  
  // 其他
  'LOGIN_SUCCESS': '登录成功',
  'LOGOUT_SUCCESS': '已退出登录',
  'STATUS_REFRESHED': '状态已刷新',
  'COPIED_TO_CLIPBOARD': '已复制到剪贴板',
};

/**
 * 警告消息映射
 */
const WARNING_MESSAGES = {
  'NO_DATA_TO_EXPORT': '无数据，不能导出',
  'SELECT_DATA_TO_DELETE': '请选择要删除的数据',
  'SELECT_FILE': '请先选择Excel文件',
  'MAPPING_INCOMPLETE': '请为所有必需字段选择对应的Excel列',
  'PREVIEW_DATA_EMPTY': '预览数据为空，请检查Excel文件内容',
  'FIELDS_EMPTY': '字段信息为空，请检查映射规则',
  'PRODUCT_NOT_FOUND': '原产品可能已不存在，请重新选择产品',
  'NO_PRODUCT_INFO': '无法获取产品信息，请先查询数据',
  'SELECT_PRODUCT_OR_QUERY': '请先选择产品或查询数据，以便确定要导出的客户',
  'NO_CLIENT_ID': '无法确定客户ID，请先查询数据',
  'NO_CLIENT_INFO': '该客户用户还没有关联的客户信息，请先编辑用户并创建客户信息',
  'FORM_VALIDATION_FAILED': '请检查表单填写是否正确',
  'GET_DETAIL_FAILED': '获取详情失败，使用列表数据',
  'UNAUTHORIZED': '未授权，请先登录',
};

/**
 * 错误消息前缀映射（用于API调用失败时的提示）
 * 注意：实际错误消息应优先使用后端返回的detail或message
 */
const ERROR_PREFIXES = {
  'GET_USER_LIST': '获取用户列表失败',
  'GET_USER_DETAIL': '获取用户详情失败',
  'CREATE_USER': '创建用户失败',
  'UPDATE_USER': '更新用户失败',
  'DELETE_USER': '删除用户失败',
  'EXPORT_USER': '导出用户数据失败',
  'GET_USER_STATS': '获取用户统计信息失败',
  
  'GET_CLIENT_LIST': '获取客户列表失败',
  'GET_CLIENT_DETAIL': '获取客户详情失败',
  'CREATE_CLIENT': '创建客户失败',
  'UPDATE_CLIENT': '更新客户失败',
  'DELETE_CLIENT': '删除客户失败',
  'EXPORT_CLIENT': '导出客户数据失败',
  
  'GET_PRODUCT_LIST': '获取产品列表失败',
  'GET_PRODUCT_DETAIL': '获取产品详情失败',
  
  'GET_TASK_LIST': '获取定时任务列表失败',
  'GET_TASK_DETAIL': '获取定时任务详情失败',
  'CREATE_TASK': '创建定时任务失败',
  'UPDATE_TASK': '更新定时任务失败',
  'TRIGGER_TASK': '触发定时任务失败',
  'RELEASE_TASK_LOCK': '释放任务锁失败',
  
  'GET_AD_DATA': '获取广告数据失败',
  'UPDATE_AD_DATA': '更新数据失败',
  'DELETE_AD_DATA': '删除失败',
  'BATCH_DELETE_AD_DATA': '批量删除失败',
  'EXPORT_AD_DATA': '导出数据失败',
  'GET_CLIENT_LIST_WITH_DATA': '获取有数据的客户列表失败',
  'GET_PRODUCT_LIST_WITH_DATA': '获取有数据的产品列表失败',
  
  'GET_AUDIT_LOG': '获取操作日志失败',
  'GET_AUDIT_LOG_DETAIL': '获取日志详情失败',
  'GET_AUDIT_LOG_STATS': '获取统计信息失败',
  
  'VALIDATE_EXCEL_COLUMNS': '验证Excel列名失败',
  'GET_MAPPING_STATUS': '获取映射规则状态失败',
  'PARSE_EXCEL_COLUMNS': '解析Excel列名失败',
  'SAVE_MAPPING': '保存映射规则失败',
  'PREVIEW_EXCEL_DATA': '预览Excel数据失败',
  'IMPORT_EXCEL': '导入Excel失败',
  
  'GET_DASHBOARD_STATS': '获取统计数据失败',
  'GET_TREND_DATA': '获取趋势数据失败',
};

/**
 * 获取成功消息
 * @param {string} key - 消息键
 * @param {...any} args - 消息参数（用于格式化）
 * @returns {string} 成功消息
 */
export const getSuccessMessage = (key, ...args) => {
  const message = SUCCESS_MESSAGES[key];
  if (typeof message === 'function') {
    return message(...args);
  }
  return message || '操作成功';
};

/**
 * 获取警告消息
 * @param {string} key - 消息键
 * @returns {string} 警告消息
 */
export const getWarningMessage = (key) => {
  return WARNING_MESSAGES[key] || '警告';
};

/**
 * 获取错误消息前缀（用于API调用失败时）
 * 注意：实际使用时应该优先使用后端返回的错误消息
 * @param {string} key - 错误键
 * @returns {string} 错误消息前缀
 */
export const getErrorMessagePrefix = (key) => {
  return ERROR_PREFIXES[key] || '操作失败';
};

/**
 * 格式化错误消息
 * 优先使用后端返回的detail或message，如果没有则使用前缀
 * @param {Error} error - 错误对象
 * @param {string} prefixKey - 错误前缀键（可选）
 * @returns {string} 格式化后的错误消息
 */
export const formatErrorMessage = (error, prefixKey = null) => {
  // 优先使用后端返回的错误消息
  if (error.response?.data?.detail) {
    return error.response.data.detail;
  }
  if (error.response?.data?.message) {
    return error.response.data.message;
  }
  
  // 如果有前缀键，使用前缀 + 错误消息
  if (prefixKey) {
    const prefix = getErrorMessagePrefix(prefixKey);
    const errorMsg = error.message || '未知错误';
    return `${prefix}: ${errorMsg}`;
  }
  
  // 否则直接返回错误消息
  return error.message || '请求失败';
};

