/**
 * 解析认证接口响应（兼容标准包装与历史裸 JSON）
 * @param {Object} responseData - axios response.data
 * @returns {Object} token 载荷 { access_token, refresh_token, token_type, user }
 */
export const parseAuthResponseData = (responseData) => {
  const raw = responseData || {};
  if (raw.code !== undefined) {
    if (raw.code !== 200) {
      const errorMsg = raw.detail || raw.message || '认证失败';
      const error = new Error(errorMsg);
      error.code = raw.code;
      error.response = { data: raw };
      throw error;
    }
    return raw.data || {};
  }
  return raw;
};
