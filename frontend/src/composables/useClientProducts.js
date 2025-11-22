import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { getProductList, createProduct, updateProduct, deleteProduct } from '../api/product';
import { logger } from '../utils/logger';
import { extractErrorMessage, isErrorHandled, ensureCsrfToken } from '../utils/api';

/**
 * 客户产品管理 Composable
 * 处理产品相关的操作
 */
export function useClientProducts() {
  const productDialogVisible = ref(false);
  const currentClientIdForProducts = ref(null);
  const currentClientName = ref('');
  const products = ref([]);
  const productLoading = ref(false);

  /**
   * 打开产品管理对话框
   * @param {Object} client - 客户对象
   */
  const openProductDialog = (client) => {
    currentClientIdForProducts.value = client.id;
    // 使用 full_name（如果传入），否则使用 company_name，最后使用默认值
    currentClientName.value = client.full_name || client.company_name || '未知客户';
    productDialogVisible.value = true;
    fetchProductsForClient(client.id);
  };

  /**
   * 获取客户的产品列表
   * @param {number} clientId - 客户ID
   */
  const fetchProductsForClient = async (clientId) => {
    try {
      productLoading.value = true;
      const response = await getProductList({
        client_id: clientId,
        page_size: 100
      });
      products.value = response.data || [];
      // 响应拦截器会自动处理CSRF令牌，这里不需要额外操作
    } catch (error) {
      // 即使请求失败，响应拦截器也可能已经处理了CSRF令牌
      // 所以这里不重新抛出错误，让调用方决定如何处理
      if (!isErrorHandled(error)) {
        const errorMsg = extractErrorMessage(error);
        ElMessage.error(errorMsg);
      }
      products.value = [];
      // 不重新抛出错误，因为CSRF令牌可能已经获取到了
      // 调用方可以通过检查CSRF令牌是否存在来决定是否继续
    } finally {
      productLoading.value = false;
    }
  };

  /**
   * 保存产品
   * @param {Object} params - 产品数据 { id, data, callback }
   * @returns {Promise<boolean>} 是否保存成功
   */
  const saveProduct = async ({ id, data, callback }) => {
    try {
      // 如果是更新操作且只更新 client_id（转移产品），只验证 client_id
      const isTransferProduct = id && data.client_id && !data.name && data.ecpm_deduct_ratio === undefined && data.revenue_deduct_ratio === undefined;
      
      if (!isTransferProduct) {
        // 创建或完整更新产品时，验证所有必要字段
        if (!data.name || data.name.trim() === '') {
          const errorMsg = '产品名称不能为空';
          logger.error('saveProduct: 验证失败 -', errorMsg);
          ElMessage.error(errorMsg);
          if (callback) {
            callback(false);
          }
          return false;
        }
        
        if (data.ecpm_deduct_ratio === undefined || data.ecpm_deduct_ratio === null) {
          const errorMsg = 'eCPM减扣比例不能为空';
          logger.error('saveProduct: 验证失败 -', errorMsg);
          ElMessage.error(errorMsg);
          if (callback) {
            callback(false);
          }
          return false;
        }
        
        if (data.revenue_deduct_ratio === undefined || data.revenue_deduct_ratio === null) {
          const errorMsg = '收益减扣比例不能为空';
          logger.error('saveProduct: 验证失败 -', errorMsg);
          ElMessage.error(errorMsg);
          if (callback) {
            callback(false);
          }
          return false;
        }
      }
      
      // 验证 client_id（所有操作都需要）
      if (!data.client_id) {
        const errorMsg = '客户ID不能为空';
        logger.error('saveProduct: 验证失败 -', errorMsg);
        ElMessage.error(errorMsg);
        if (callback) {
          callback(false);
        }
        return false;
      }
      
      // 确保CSRF令牌存在：如果没有，先发送一个GET请求获取
      let csrfToken = sessionStorage.getItem('csrf_token');
      
      if (!csrfToken) {
        try {
          const csrfTokenExists = await ensureCsrfToken(() => fetchProductsForClient(currentClientIdForProducts.value));
          
          if (!csrfTokenExists) {
            // 再次检查，因为响应拦截器可能已经处理了
            csrfToken = sessionStorage.getItem('csrf_token');
            
            if (!csrfToken) {
              logger.error('saveProduct: 无法获取CSRF令牌，操作已取消');
              ElMessage.error('无法获取安全令牌，请刷新页面后重试');
              if (callback) {
                callback(false);
              }
              return false;
            }
          }
        } catch (error) {
          logger.error('saveProduct: 获取CSRF令牌时出错:', error);
          // 如果是401错误，不应该继续
          if (error.response?.status === 401) {
            throw error;
          }
          // 再次检查CSRF令牌（响应拦截器可能已经处理了）
          csrfToken = sessionStorage.getItem('csrf_token');
          if (!csrfToken) {
            logger.error('saveProduct: 无法获取CSRF令牌，操作已取消');
            ElMessage.error('无法获取安全令牌，请刷新页面后重试');
            if (callback) {
              callback(false);
            }
            return false;
          }
        }
      }
      
      // 最终确认CSRF令牌存在
      csrfToken = sessionStorage.getItem('csrf_token');
      if (!csrfToken) {
        logger.error('saveProduct: CSRF令牌最终检查失败，操作已取消');
        ElMessage.error('安全令牌验证失败，请刷新页面后重试');
        if (callback) {
          callback(false);
        }
        return false;
      }
      
      // 在发送请求前再次确认CSRF令牌存在
      csrfToken = sessionStorage.getItem('csrf_token');
      if (!csrfToken) {
        logger.error('saveProduct: 发送请求前CSRF令牌检查失败，操作已取消');
        ElMessage.error('安全令牌验证失败，请刷新页面后重试');
        if (callback) {
          callback(false);
        }
        return false;
      }
      
      if (!id) {
        logger.debug('saveProduct: 创建新产品');
        await createProduct(data);
        ElMessage.success('产品创建成功');
      } else {
        logger.debug('saveProduct: 更新产品，id =', id);
        // 再次确认CSRF令牌存在（防止在异步操作期间被清除）
        const finalCsrfToken = sessionStorage.getItem('csrf_token');
        if (!finalCsrfToken) {
          logger.error('saveProduct: 更新产品前CSRF令牌检查失败，操作已取消');
          ElMessage.error('安全令牌验证失败，请刷新页面后重试');
          if (callback) {
            callback(false);
          }
          return false;
        }
        await updateProduct(id, data);
        ElMessage.success('产品更新成功');
      }
      
      logger.debug('saveProduct: API 调用成功，刷新产品列表');
      await fetchProductsForClient(currentClientIdForProducts.value);
      
      // 如果有回调函数，调用它表示成功
      if (callback) {
        logger.debug('saveProduct: 调用回调 true');
        callback(true);
      }
      return true;
    } catch (error) {
      logger.error('saveProduct: 保存失败', error);
      logger.error('saveProduct: error.response =', error.response);
      logger.error('saveProduct: error.message =', error.message);
      
      if (!error.message?.includes('取消') && !error.message?.includes('validate')) {
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          logger.error('saveProduct: 显示错误消息 -', errorMsg);
          ElMessage.error(errorMsg);
        }
      }
      // 如果有回调函数，调用它表示失败
      if (callback) {
        logger.debug('saveProduct: 调用回调 false (错误)');
        callback(false);
      }
      return false;
    }
  };

  /**
   * 删除产品
   * @param {number} id - 产品ID
   * @returns {Promise<boolean>} 是否删除成功
   */
  const removeProduct = async (id) => {
    try {
      // 确保CSRF令牌存在
      await ensureCsrfToken(() => fetchProductsForClient(currentClientIdForProducts.value));
      
      productLoading.value = true;
      await deleteProduct(id);
      await fetchProductsForClient(currentClientIdForProducts.value);
      ElMessage.success('产品删除成功');
      return true;
    } catch (error) {
      if (!error.message?.includes('取消')) {
        if (!isErrorHandled(error)) {
          const errorMsg = extractErrorMessage(error);
          ElMessage.error(errorMsg);
        }
      }
      return false;
    } finally {
      productLoading.value = false;
    }
  };

  return {
    productDialogVisible,
    currentClientIdForProducts,
    currentClientName,
    products,
    productLoading,
    openProductDialog,
    fetchProductsForClient,
    saveProduct,
    removeProduct
  };
}

