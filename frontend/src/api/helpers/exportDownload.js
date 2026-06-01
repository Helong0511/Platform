/**
 * 列表 Excel 导出：统一下载与「无数据」错误处理
 */
import { requestBlobDownload, extractErrorMessage, handleError } from '../../utils/api';
import { ElMessage } from 'element-plus';
import { getWarningMessage } from '../../utils/messages';

const DEFAULT_NO_DATA_KEYWORDS = ['无数据', '不能导出', '没有可导出'];

/**
 * @param {Object} requestConfig axios 请求配置（url/method/params）
 * @param {Object} options
 * @param {string} options.defaultFilename
 * @param {() => void} [options.onSuccess]
 * @param {boolean} [options.warnOnNoData] 无数据时是否弹出警告（默认 true）
 * @param {string[]} [options.noDataKeywords]
 * @param {boolean} [options.rethrowNoData] 无数据时是否继续 throw（默认 true）
 */
export async function requestListExport(requestConfig, options = {}) {
  const {
    defaultFilename,
    onSuccess,
    warnOnNoData = true,
    noDataKeywords = DEFAULT_NO_DATA_KEYWORDS,
    rethrowNoData = true
  } = options;

  try {
    return await requestBlobDownload(requestConfig, {
      defaultFilename,
      onSuccess
    });
  } catch (error) {
    const errorMsg = extractErrorMessage(error) || '导出失败';
    const isNoData = noDataKeywords.some((kw) => errorMsg.includes(kw));
    if (isNoData) {
      if (warnOnNoData) {
        ElMessage.warning(getWarningMessage('NO_DATA_TO_EXPORT'));
      }
      if (rethrowNoData) {
        throw error;
      }
      return null;
    }
    handleError(error);
    throw error;
  }
}
