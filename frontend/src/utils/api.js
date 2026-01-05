/**
 * API响应处理工具模块
 * 
 * 功能说明：
 * 统一处理前后端API响应格式，确保数据解析的一致性，包括：
 * - 响应标准化：将后端响应转换为统一格式
 * - 分页数据处理：处理分页响应的嵌套结构
 * - 错误处理：统一提取和显示错误信息
 * - CSRF令牌管理：自动刷新和管理CSRF令牌
 * - 文件下载处理：处理文件下载响应
 * - 请求封装：封装axios请求，添加统一配置
 * 
 * 标准响应格式：
 * {
 *   code: number,      // 错误码（200表示成功，其他表示错误）
 *   message: string,   // 错误信息（简要描述）
 *   detail?: string,   // 详细错误信息（可选，用于显示给用户）
 *   data?: any         // 响应数据（可选，成功时包含实际数据）
 * }
 * 
 * 分页响应格式：
 * {
 *   code: 200,
 *   message: "success",
 *   data: {
 *     data: [...],        // 数据列表
 *     total: 100,          // 总记录数
 *     page: 1,             // 当前页码
 *     page_size: 10,       // 每页条数
 *     total_pages: 10     // 总页数
 *   }
 * }
 * 
 * 错误处理：
 * - 自动提取错误信息（优先使用detail，其次使用message）
 * - 统一显示错误提示（使用Element Plus的ElMessage）
 * - 支持错误码判断（401表示未授权，403表示禁止访问等）
 * - 自动处理token过期（401时清除认证信息并跳转登录）
 * 
 * CSRF令牌管理：
 * - 自动从响应头获取CSRF令牌（X-CSRF-Token）
 * - 自动在请求头中添加CSRF令牌（X-CSRF-Token）
 * - 支持令牌刷新（refreshCsrfToken函数）
 * - 支持请求前刷新令牌（refreshCsrfTokenBeforeRequest函数）
 * 
 * 使用示例：
 * ```javascript
 * // 基本请求
 * const response = await request({
 *   url: '/api/v1/users/',
 *   method: 'get',
 *   params: { page: 1, page_size: 10 }
 * }, { paginated: true });
 * 
 * // 分页请求
 * const paginatedData = await request({
 *   url: '/api/v1/users/',
 *   method: 'get',
 *   params: { page: 1 }
 * }, { paginated: true });
 * 
 * // 只获取数据
 * const userData = await request({
 *   url: '/api/v1/users/1',
 *   method: 'get'
 * }, { returnDataOnly: true });
 * ```
 * 
 * @module utils/api
 */

// 静态导入所有依赖，避免Vite构建警告（动态导入与静态导入混用）
import logger from './logger';
import axios from 'axios';
import { ElMessage } from 'element-plus';

/**
 * 标准化API响应处理
 * @param {Object} response - axios响应对象
 * @param {Object} options - 配置选项
 * @param {boolean} options.throwOnError - 是否在错误时抛出异常（默认：true）
 * @param {boolean} options.returnDataOnly - 是否只返回data字段（默认：false）
 * @returns {Object} 标准化后的响应数据
 */
export const normalizeResponse = (response, options = {}) => {
  const { 
    throwOnError = true,
    returnDataOnly = false 
  } = options;

  // 检查响应是否存在
  if (!response || !response.data) {
    if (throwOnError) {
      throw new Error('响应数据格式错误');
    }
    return returnDataOnly ? null : { 
      code: 500, 
      message: '响应数据格式错误', 
      data: null 
    };
  }

  const responseData = response.data;

  // 如果已经是标准格式（有code字段）
  if (responseData.code !== undefined) {
    // 检查是否成功（code === 200 表示成功）
    if (responseData.code !== 200 && throwOnError) {
      // 优先使用 detail，其次使用 message
      const errorMsg = responseData.detail || responseData.message || '请求失败';
      const error = new Error(errorMsg);
      // 附加错误码和原始响应数据
      error.code = responseData.code;
      error.responseData = responseData;
      throw error;
    }
    return returnDataOnly ? responseData.data : responseData;
  }

  // 如果不是标准格式，尝试标准化
  // 假设数据在responseData中
  if (Array.isArray(responseData)) {
    return returnDataOnly ? responseData : {
      code: 200,
      message: 'success',
      data: responseData
    };
  }

  // 如果是对象，尝试提取data字段
  if (responseData.data !== undefined) {
    return returnDataOnly ? responseData.data : {
      code: 200,
      message: 'success',
      ...responseData
    };
  }

  // 默认情况
  return returnDataOnly ? responseData : {
    code: 200,
    message: 'success',
    data: responseData
  };
};

/**
 * 处理分页响应
 * @param {Object} response - axios响应对象
 * @returns {Object} 标准化后的分页数据
 */
export const normalizePaginatedResponse = (response) => {
  const normalized = normalizeResponse(response, { returnDataOnly: false });
  
  // 处理嵌套的 data 字段（后端返回的格式是 { code: 200, data: { data: [...], total: ..., page: ..., page_size: ... } }）
  let paginatedData = normalized.data || {};
  
  // 如果 data 是一个对象且包含 data 字段，说明是嵌套的分页响应
  // 检查 paginatedData 是否有 data 属性（数组）和 total 属性（数字）
  if (paginatedData && 
      typeof paginatedData === 'object' && 
      !Array.isArray(paginatedData) && 
      paginatedData.data !== undefined && 
      Array.isArray(paginatedData.data) &&
      typeof paginatedData.total !== 'undefined') {
    // 使用嵌套的 data 对象
    const result = {
      code: normalized.code || 200,
      message: normalized.message || 'success',
      data: paginatedData, // 返回整个 AdDataListResponse 对象 { data: [...], total: ..., page: ..., page_size: ... }
      total: paginatedData.total || 0,
      page: paginatedData.page || 1,
      page_size: paginatedData.page_size || 10,
      total_pages: paginatedData.total_pages || Math.ceil((paginatedData.total || 0) / (paginatedData.page_size || 10))
    };
    
    return result;
  }
  
  // 如果不是嵌套格式，检查是否 normalized.data 本身就是数组（扁平格式）
  if (Array.isArray(normalized.data)) {
    const result = {
      code: normalized.code || 200,
      message: normalized.message || 'success',
      data: normalized.data || [],
      total: normalized.total || normalized.data.length || 0,
      page: normalized.page || 1,
      page_size: normalized.page_size || 10,
      total_pages: normalized.total_pages || Math.ceil((normalized.total || normalized.data.length || 0) / (normalized.page_size || 10))
    };
    
    return result;
  }
  
  // 其他情况，使用扁平格式（兼容旧格式）
  const result = {
    code: normalized.code || 200,
    message: normalized.message || 'success',
    data: normalized.data || [],
    total: normalized.total || 0,
    page: normalized.page || 1,
    page_size: normalized.page_size || 10,
    total_pages: normalized.total_pages || Math.ceil((normalized.total || 0) / (normalized.page_size || 10))
  };
  
  return result;
};

/**
 * 安全获取嵌套数据
 * @param {Object} obj - 对象
 * @param {String} path - 路径，如 'data.items'
 * @param {*} defaultValue - 默认值
 * @returns {*} 获取的值或默认值
 */
export const safeGet = (obj, path, defaultValue = null) => {
  if (!obj || typeof obj !== 'object') {
    return defaultValue;
  }

  const keys = path.split('.');
  let current = obj;

  for (const key of keys) {
    if (current === null || current === undefined) {
      return defaultValue;
    }
    current = current[key];
  }

  return current !== undefined ? current : defaultValue;
};

/**
 * 提取错误消息
 * @param {Error} error - 错误对象
 * @returns {String} 错误消息
 */
export const extractErrorMessage = (error) => {
  if (error.response) {
    // 后端返回的错误（标准格式）
    const errorData = error.response.data;
    
    // 如果 errorData 是 Blob 对象，尝试解析（但不在这里解析，由调用方处理）
    if (errorData instanceof Blob) {
      // 对于 blob 响应，返回默认错误消息，具体错误由调用方从 blob 中解析
      return error.message || '请求失败';
    }
    
    // 优先使用 detail，其次使用 message
    if (errorData && typeof errorData === 'object' && errorData.detail) {
      return errorData.detail;
    }
    if (errorData && typeof errorData === 'object' && errorData.message) {
      return errorData.message;
    }
    
    // 兼容旧格式（直接是字符串）
    if (typeof errorData === 'string') {
      return errorData;
    }
    
    // 如果都没有，使用默认消息
    return error.message || '请求失败';
  }
  
  // 网络错误或其他错误
  if (error.message) {
    return error.message;
  }
  
  return '请求失败';
};

/**
 * 提取错误码
 * @param {Error} error - 错误对象
 * @returns {number|null} 错误码（如果存在）
 */
export const extractErrorCode = (error) => {
  if (error.code) {
    return error.code;
  }
  
  if (error.response?.data?.code) {
    return error.response.data.code;
  }
  
  // 根据 HTTP 状态码映射错误码
  if (error.response?.status) {
    const statusToCode = {
      400: 400,
      401: 401,
      403: 403,
      404: 404,
      405: 405,
      409: 409,
      422: 422,
      429: 429,
      500: 500,
      503: 503,
    };
    return statusToCode[error.response.status] || 500;
  }
  
  return null;
};

/**
 * 检查错误是否已被处理（如429限流错误已在拦截器中处理）
 * @param {Error} error - 错误对象
 * @returns {Boolean} 是否已被处理
 */
export const isErrorHandled = (error) => {
  // 429限流错误已在axios拦截器中处理，不需要重复显示
  if (error.response && error.response.status === 429) {
    return true;
  }
  // 401未授权错误已在axios拦截器中处理
  if (error.response && error.response.status === 401) {
    return true;
  }
  // 检查是否已标记为已处理
  return error._handled === true;
};

/**
 * 统一的API错误处理函数
 * 用于在组件的catch块中处理错误，避免重复显示已处理的错误
 * 
 * 注意：此函数是同步的，内部异步操作不会阻塞调用
 * 
 * @param {Error} error - 错误对象
 * @param {string} defaultMessage - 默认错误消息（当无法提取错误信息时使用）
 * @param {Object} options - 配置选项
 * @param {boolean} options.showMessage - 是否显示错误消息（默认：true）
 * @param {boolean} options.logError - 是否记录错误日志（默认：true）
 * @param {string} options.logContext - 日志上下文（用于标识错误来源）
 * @returns {boolean} 返回true表示错误已被处理（如401/403），返回false表示需要进一步处理
 * 
 * @example
 * // 基本使用
 * try {
 *   await someApiCall();
 * } catch (error) {
 *   handleApiError(error, '操作失败', { logContext: '提交数据' });
 * }
 * 
 * @example
 * // 不显示错误消息（仅记录日志）
 * try {
 *   await someApiCall();
 * } catch (error) {
 *   if (handleApiError(error, '操作失败', { showMessage: false })) {
 *     // 错误已被处理（401/403），可以提前返回
 *     return;
 *   }
 *   // 其他错误处理逻辑
 * }
 */
export const handleApiError = (error, defaultMessage = '操作失败', options = {}) => {
  const {
    showMessage = true,
    logError = true,
    logContext = 'API调用'
  } = options;

  // 记录错误日志
  if (logError) {
    try {
      logger.error(`${logContext}失败:`, error);
    } catch (e) {
      // 如果logger调用失败，使用console作为后备
      console.error(`${logContext}失败:`, error);
    }
  }

  // 检查是否是401未授权错误（token过期）
  // 如果是401错误，axios拦截器已经处理了（清除认证信息并跳转到登录页）
  // 这里不需要重复显示错误信息，避免干扰用户体验
  if (error.response && error.response.status === 401) {
    // 401错误已被axios拦截器处理，直接返回true表示已处理
    return true;
  }

  // 检查是否是403错误（可能是CSRF token问题）
  // 403错误也可能已被axios拦截器处理（自动重试）
  if (error.response && error.response.status === 403) {
    // 如果错误已被处理（标记了_handled），不显示错误信息
    if (error._handled) {
      return true;
    }
    // 如果错误未被处理，继续显示错误信息
  }

  // 其他错误：显示具体错误信息（异步，不阻塞）
  if (showMessage) {
    // 使用立即执行的异步函数显示消息
    (async () => {
      try {
        const errorMsg = extractErrorMessage(error) || defaultMessage;
        ElMessage.error(errorMsg);
      } catch (e) {
        // 如果ElMessage导入失败，使用console（只记录一次，避免重复）
        console.error('显示错误消息失败:', e, '原始错误信息:', extractErrorMessage(error) || defaultMessage);
      }
    })();
  }

  // 返回false表示错误需要进一步处理（已显示错误消息）
  return false;
};

/**
 * 刷新CSRF令牌（通过发送GET请求）
 * @param {string} endpoint - 用于刷新令牌的端点，默认为 '/api/v1/dashboard/stats'
 * @returns {Promise<void>}
 */
export const refreshCsrfToken = async (endpoint = '/api/v1/dashboard/stats') => {
  try {
    // 发送一个轻量级的GET请求来刷新CSRF令牌
    const response = await axios.get(endpoint);
    
    // 直接从响应头获取CSRF令牌（不依赖响应拦截器）
    const { extractAndSaveCsrfToken } = await import('./csrfToken');
    extractAndSaveCsrfToken(response);
    
    // 额外等待一小段时间，确保响应拦截器也处理完成
    await new Promise(resolve => setTimeout(resolve, 50));
  } catch (error) {
    // 即使请求失败，响应头中也可能有CSRF令牌
    const { extractAndSaveCsrfToken } = await import('./csrfToken');
    extractAndSaveCsrfToken(error);
  }
};

/**
 * 确保CSRF令牌存在
 * 如果CSRF令牌不存在，通过发送GET请求获取
 * @param {Function} getRequestFn - 获取数据的函数（用于触发GET请求获取CSRF令牌）
 * @returns {Promise<boolean>} 是否成功获取CSRF令牌
 */
export const ensureCsrfToken = async (getRequestFn = null) => {
  const { getCsrfToken, extractAndSaveCsrfToken, fetchCsrfTokenFromEndpoints } = await import('./csrfToken');
  
  // 检查CSRF令牌是否存在
  let csrfToken = getCsrfToken();
  
  if (csrfToken) {
    return true; // 已存在，直接返回
  }
  
  // 如果提供了获取数据的函数，使用它来获取CSRF令牌
  if (getRequestFn && typeof getRequestFn === 'function') {
    try {
      await getRequestFn();
    } catch (error) {
      // 检查响应中是否有CSRF令牌（即使请求失败，响应头中也可能有CSRF令牌）
      const csrfTokenFromResponse = extractAndSaveCsrfToken(error);
      if (csrfTokenFromResponse) {
        return true;
      }
      
      // 如果错误是401，可能是认证问题，不应该继续
      if (error.response?.status === 401) {
        throw error; // 重新抛出401错误
      }
    }
    
    // 等待一小段时间，确保响应拦截器已经处理完响应头
    await new Promise(resolve => setTimeout(resolve, 150));
    csrfToken = getCsrfToken();
    if (csrfToken) {
      return true;
    }
  }
  
  // 如果没有提供函数，或者提供的函数失败，尝试发送一个简单的GET请求
  try {
    csrfToken = await fetchCsrfTokenFromEndpoints();
    if (csrfToken) {
      return true;
    }
    return false;
  } catch (error) {
    // 如果错误是401，可能是认证问题，不应该继续
    if (error.response?.status === 401) {
      throw error; // 重新抛出401错误
    }
    return false;
  }
};

/**
 * 统一的错误处理函数
 * 用于在 catch 块中统一处理错误
 * @param {Error} error - 错误对象
 * @param {Object} options - 选项
 * @param {boolean} options.silent - 是否静默处理（不显示错误消息，默认：false）
 * @param {Function} options.customHandler - 自定义错误处理函数
 * @returns {void}
 */
export const handleError = (error, options = {}) => {
  const { silent = false, customHandler } = options;
  
  // 如果错误已被处理（如429限流），直接抛出
  if (isErrorHandled(error)) {
    throw error;
  }
  
  // 如果有自定义处理函数，使用自定义处理
  if (customHandler && typeof customHandler === 'function') {
    customHandler(error);
    throw error;
  }
  
  // 如果不是静默模式，显示错误消息
  if (!silent) {
    const errorMsg = extractErrorMessage(error);
    ElMessage.error(errorMsg);
  }
  
  // 重新抛出错误，让调用方可以处理
  throw error;
};

/**
 * 统一的CSRF Token刷新函数
 * 用于在需要CSRF token的请求前刷新token
 * @param {string} endpoint - 用于刷新token的端点（可选）
 * @returns {Promise<void>}
 */
export const refreshCsrfTokenBeforeRequest = async (endpoint = null) => {
  // 如果提供了端点，使用该端点刷新token
  if (endpoint) {
    await refreshCsrfToken(endpoint);
  }
  
  // 确保token存在
  await ensureCsrfToken();
};

/**
 * 统一的文件下载处理函数
 * @param {Object} response - axios响应对象
 * @param {string} defaultFilename - 默认文件名
 * @param {Function} onSuccess - 成功回调（可选）
 * @returns {void}
 */
export const handleFileDownload = (response, defaultFilename = 'download.xlsx', onSuccess = null) => {
  try {
    // 从响应头获取文件名
    const contentDisposition = response.headers['content-disposition'];
    let filename = defaultFilename;
    
    if (contentDisposition) {
      // 支持 UTF-8 编码的文件名
      const utf8Match = contentDisposition.match(/filename\*=UTF-8''(.+)/);
      if (utf8Match && utf8Match[1]) {
        filename = decodeURIComponent(utf8Match[1]);
      } else {
        const match = contentDisposition.match(/filename=(.*)/);
        if (match && match[1]) {
          filename = decodeURIComponent(match[1]);
        }
      }
    }
    
    // 创建下载链接
    const blob = new Blob([response.data]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    
    // 调用成功回调
    if (onSuccess && typeof onSuccess === 'function') {
      onSuccess(filename);
    }
  } catch (error) {
    logger.error('文件下载处理失败:', error);
    throw error;
  }
};

/**
 * 统一的请求函数（封装 axios）
 * 用于简化API调用，自动处理响应格式化和错误处理
 * @param {Object} config - axios 配置对象
 * @param {Object} options - 额外选项
 * @param {boolean} options.returnDataOnly - 是否只返回data字段（默认：false）
 * @param {boolean} options.paginated - 是否为分页响应（默认：false）
 * @param {boolean} options.silent - 是否静默处理错误（不显示错误消息，默认：false）
 * @returns {Promise} 返回处理后的响应数据
 */
export const request = async (config, options = {}) => {
  const {
    returnDataOnly = false,
    paginated = false,
    silent = false
  } = options;
  
  try {
    const response = await axios(config);
    
    // 如果是文件下载（blob响应），直接返回原始响应
    if (config.responseType === 'blob') {
      return response;
    }
    
    // 如果是分页响应，使用 normalizePaginatedResponse
    if (paginated) {
      return normalizePaginatedResponse(response);
    }
    
    // 使用 normalizeResponse 处理响应
    return normalizeResponse(response, { returnDataOnly });
  } catch (error) {
    // 使用统一的错误处理函数
    handleError(error, { silent });
  }
};

