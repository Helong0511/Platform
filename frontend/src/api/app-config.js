/**
 * 应用级配置 API（时区等），与具体业务模块解耦
 */
import { request } from '../utils/api';

/**
 * 获取应用时区
 * @returns {Promise<string>}
 */
export const getTimezone = async () => {
  try {
    const data = await request({
      url: '/api/v1/ml-model/timezone',
      method: 'get'
    }, { returnDataOnly: true });
    return data?.timezone || 'Asia/Shanghai';
  } catch {
    return 'Asia/Shanghai';
  }
};
