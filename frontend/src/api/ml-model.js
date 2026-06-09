/**
 * 机器学习模型管理 API
 * @file api/ml-model.js
 */
import {
  request,
  requestUploadWithCsrfRetry,
  handleError
} from '../utils/api';
import { withCsrfMutate } from '../utils/csrfMutate';

const uploadExcelFile = (url, file, extraConfig = {}) => {
  const formData = new FormData();
  formData.append('file', file);
  return requestUploadWithCsrfRetry(
    {
      url,
      method: 'post',
      data: formData,
      ...extraConfig
    },
    { returnDataOnly: true, timeout: 60000 }
  );
};

/**
 * 验证Excel列名映射
 */
export const validateExcelData = async (file) => {
  try {
    return await uploadExcelFile('/api/v1/ml-model/validate', file);
  } catch (error) {
    handleError(error);
  }
};

export const getModelStatus = async () => {
  return request({
    url: '/api/v1/ml-model/status',
    method: 'get'
  }, { returnDataOnly: true });
};

export { getTimezone } from './app-config';

/**
 * parseExcelColumns 接口。
 */
export const parseExcelColumns = async (file) => {
  try {
    return await uploadExcelFile('/api/v1/ml-model/parse-excel', file);
  } catch (error) {
    handleError(error);
  }
};

/**
 * 保存Mapping。
 */
export const saveMapping = async (mapping) =>
  withCsrfMutate(() =>
    request(
      {
        url: '/api/v1/ml-model/save-mapping',
        method: 'post',
        data: mapping
      },
      { returnDataOnly: true }
    )
  );

/**
 * previewExcelData 接口。
 */
export const previewExcelData = async (file, rows = 10) => {
  try {
    return await uploadExcelFile(`/api/v1/ml-model/preview?rows=${rows}`, file);
  } catch (error) {
    handleError(error);
  }
};

/**
 * 导入Training Data。
 */
export const importTrainingData = async (file) => {
  try {
    return await uploadExcelFile('/api/v1/ml-model/import', file);
  } catch (error) {
    handleError(error);
  }
};
