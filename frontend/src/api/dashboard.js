import axios from 'axios';
import { normalizeResponse, extractErrorMessage } from '../utils/api';

// 获取仪表盘统计数据
export const getDashboardStats = async (period = 'week') => {
  try {
    const response = await axios.get(`/api/v1/dashboard/stats?period=${period}`);
    // 后端已返回标准格式，直接使用 normalizeResponse
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    throw new Error('获取仪表盘统计数据失败: ' + errorMsg);
  }
};

// 注意：getRecentAdData 和 getTodayMetrics 已移除，因为后端API未实现

// 获取趋势数据
export const getTrendData = async (period = 'week') => {
  try {
    const response = await axios.get(`/api/v1/dashboard/trends?period=${period}`);
    // 后端已返回标准格式，直接使用 normalizeResponse
    return normalizeResponse(response, { returnDataOnly: true });
  } catch (error) {
    const errorMsg = extractErrorMessage(error);
    throw new Error('获取趋势数据失败: ' + errorMsg);
  }
};
