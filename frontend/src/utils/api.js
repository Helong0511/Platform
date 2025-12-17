/**
 * API响应处理工具
 * 统一处理前后端API响应格式，确保数据解析的一致性
 * 
 * 标准响应格式：
 * {
 *   code: number,      // 错误码（200表示成功）
 *   message: string,   // 错误信息
 *   detail?: string,   // 详细错误信息（可选）
 *   data?: any         // 响应数据（可选）
 * }
 */

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
  
  // 确保分页字段存在
  return {
    code: normalized.code || 200,
    message: normalized.message || 'success',
    data: normalized.data || [],
    total: normalized.total || 0,
    page: normalized.page || 1,
    page_size: normalized.page_size || 10,
    total_pages: normalized.total_pages || Math.ceil((normalized.total || 0) / (normalized.page_size || 10))
  };
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
 * 确保CSRF令牌存在
 * 如果CSRF令牌不存在，通过发送GET请求获取
 * @param {Function} getRequestFn - 获取数据的函数（用于触发GET请求获取CSRF令牌）
 * @returns {Promise<boolean>} 是否成功获取CSRF令牌
 */
export const ensureCsrfToken = async (getRequestFn = null) => {
  // 检查CSRF令牌是否存在
  let csrfToken = sessionStorage.getItem('csrf_token');
  
  if (csrfToken) {
    return true; // 已存在，直接返回
  }
  
  // 如果提供了获取数据的函数，使用它来获取CSRF令牌
  if (getRequestFn && typeof getRequestFn === 'function') {
    let requestSucceeded = false;
    try {
      await getRequestFn();
      requestSucceeded = true;
    } catch (error) {
      // 检查响应中是否有CSRF令牌（即使请求失败，响应头中也可能有CSRF令牌）
      if (error.response?.headers) {
        const csrfTokenFromResponse = error.response.headers['x-csrf-token'] || error.response.headers['X-CSRF-Token'];
        if (csrfTokenFromResponse) {
          sessionStorage.setItem('csrf_token', csrfTokenFromResponse);
          return true;
        }
      }
      
      // 如果错误是401，可能是认证问题，不应该继续
      if (error.response?.status === 401) {
        throw error; // 重新抛出401错误
      }
    }
    
    // 等待一小段时间，确保响应拦截器已经处理完响应头
    await new Promise(resolve => setTimeout(resolve, 150));
    csrfToken = sessionStorage.getItem('csrf_token');
    if (csrfToken) {
      return true;
    }
  }
  
  // 如果没有提供函数，或者提供的函数失败，尝试发送一个简单的GET请求
  try {
    const axios = (await import('axios')).default;
    // 尝试多个轻量级的GET请求端点，增加成功率
    const endpoints = [
      '/api/v1/users/stats',
      '/api/v1/products/?page_size=1',
      '/api/v1/clients/?page_size=1',
      '/api/v1/short-links/?page_size=1',
      '/api/v1/dashboard/stats'
    ];
    
    for (const endpoint of endpoints) {
      try {
        await axios.get(endpoint);
        // 等待一小段时间，确保响应拦截器已经处理完响应头
        await new Promise(resolve => setTimeout(resolve, 150));
        csrfToken = sessionStorage.getItem('csrf_token');
        if (csrfToken) {
          return true;
        }
      } catch (error) {
        // 检查响应中是否有CSRF令牌
        if (error.response?.headers) {
          const csrfTokenFromResponse = error.response.headers['x-csrf-token'] || error.response.headers['X-CSRF-Token'];
          if (csrfTokenFromResponse) {
            sessionStorage.setItem('csrf_token', csrfTokenFromResponse);
            return true;
          }
        }
        
        // 如果错误是401，可能是认证问题，不应该继续
        if (error.response?.status === 401) {
          throw error; // 重新抛出401错误
        }
      }
    }
    
    // 所有端点都失败了
    return false;
  } catch (error) {
    // 如果错误是401，可能是认证问题，不应该继续
    if (error.response?.status === 401) {
      throw error; // 重新抛出401错误
    }
    return false;
  }
};

