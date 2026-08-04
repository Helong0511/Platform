/**
 * 请求缓存工具模块
 * 
 * 功能说明：
 * - 提供API请求响应缓存功能，减少重复请求
 * - 支持缓存策略配置（TTL、缓存键生成、缓存失效）
 * - 支持内存缓存和localStorage持久化缓存
 * - 支持请求去重（相同请求合并）
 * 
 * 使用场景：
 * - 列表数据查询（如广告数据列表、客户列表）
 * - 配置数据获取（如国家列表、产品列表）
 * - 高频查询但数据变化不频繁的接口
 * 
 * @module utils/requestCache
 */

import { logger } from './logger.js';

/**
 * 缓存存储类
 * 
 * 支持内存缓存和localStorage持久化缓存
 */
class CacheStorage {
  constructor() {
    this.memoryCache = new Map();
    this.storageKeyPrefix = 'app_request_cache_';
  }

  /**
   * 获取缓存键（带前缀）
   */
  getStorageKey(key) {
    return `${this.storageKeyPrefix}${key}`;
  }

  /**
   * 设置内存缓存
   */
  setMemory(key, value, ttl) {
    const expiresAt = Date.now() + ttl;
    this.memoryCache.set(key, {
      value,
      expiresAt
    });
  }

  /**
   * 获取内存缓存
   */
  getMemory(key) {
    const item = this.memoryCache.get(key);
    if (!item) return null;
    
    // 检查是否过期
    if (Date.now() > item.expiresAt) {
      this.memoryCache.delete(key);
      return null;
    }
    
    return item.value;
  }

  /**
   * 设置localStorage缓存
   */
  setLocalStorage(key, value, ttl) {
    try {
      const expiresAt = Date.now() + ttl;
      const item = {
        value,
        expiresAt
      };
      localStorage.setItem(this.getStorageKey(key), JSON.stringify(item));
    } catch (e) {
      logger.warn('localStorage设置失败:', e);
    }
  }

  /**
   * 获取localStorage缓存
   */
  getLocalStorage(key) {
    try {
      const itemStr = localStorage.getItem(this.getStorageKey(key));
      if (!itemStr) return null;
      
      const item = JSON.parse(itemStr);
      
      // 检查是否过期
      if (Date.now() > item.expiresAt) {
        localStorage.removeItem(this.getStorageKey(key));
        return null;
      }
      
      return item.value;
    } catch (e) {
      logger.warn('localStorage读取失败:', e);
      return null;
    }
  }

  /**
   * 删除缓存
   */
  delete(key) {
    this.memoryCache.delete(key);
    try {
      localStorage.removeItem(this.getStorageKey(key));
    } catch (e) {
      logger.warn('localStorage删除失败:', e);
    }
  }

  /**
   * 清空所有缓存
   */
  clear() {
    this.memoryCache.clear();
    try {
      // 删除所有以前缀开头的缓存
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith(this.storageKeyPrefix)) {
          localStorage.removeItem(key);
        }
      });
    } catch (e) {
      logger.warn('localStorage清空失败:', e);
    }
  }
}

// 全局缓存存储实例
const cacheStorage = new CacheStorage();

/**
 * 默认缓存配置
 */
const DEFAULT_CONFIG = {
  // 缓存过期时间（毫秒），默认5分钟
  ttl: 5 * 60 * 1000,
  // 是否使用localStorage持久化（页面刷新后仍有效）
  persist: false,
  // 是否启用 GET 响应缓存（可与 cacheUrlPatterns 组合：全局 false + 白名单）
  enabled: true,
  // 是否合并相同的请求（避免并发请求重复）
  dedup: true,
  // 可选：仅这些 URL 模式启用响应缓存（正则或子串）
  cacheUrlPatterns: null,
  // 可选：自定义是否缓存当前请求（优先级高于 cacheUrlPatterns）
  cacheWhen: null,
};

/**
 * 默认 GET 缓存白名单（配置类下拉；不含会随上游入库变化的筛选项）。
 * products/clients/countries-with-data 已移出：入库后若不失效，管理端强刷前看不到新产品。
 */
export const DEFAULT_GET_CACHE_URL_PATTERNS = [
  /^\/api\/v1\/countries(?:\/|$)/,
];

/**
 * 判断 GET 请求是否命中缓存白名单。
 * @param {Object} requestConfig - axios 配置
 * @param {Array<RegExp|string>} patterns - URL 模式
 */
export function shouldCacheGetRequest(requestConfig, patterns = DEFAULT_GET_CACHE_URL_PATTERNS) {
  if (!requestConfig || requestConfig.skipRequestCache) {
    return false;
  }
  const method = (requestConfig.method || 'get').toLowerCase();
  if (method !== 'get') {
    return false;
  }
  const url = requestConfig.url || '';
  if (!patterns?.length) {
    return false;
  }
  return patterns.some((pattern) => {
    if (pattern instanceof RegExp) {
      return pattern.test(url);
    }
    return url.includes(String(pattern));
  });
}

function shouldUseCacheForRequest(requestConfig, config) {
  if (requestConfig?.skipRequestCache) {
    return false;
  }
  if (typeof config.cacheWhen === 'function') {
    return config.cacheWhen(requestConfig);
  }
  if (config.cacheUrlPatterns?.length) {
    return shouldCacheGetRequest(requestConfig, config.cacheUrlPatterns);
  }
  return Boolean(config.enabled);
}

function shouldDedupForRequest(requestConfig, config) {
  if (requestConfig?.skipRequestCache) {
    return false;
  }
  return Boolean(config.dedup);
}

/**
 * 正在进行的请求映射（用于请求去重）
 */
const pendingRequests = new Map();

/**
 * 创建去重占位 Promise，供并发请求共享同一 in-flight 结果。
 */
function createDedupEntry() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/**
 * 从 pendingRequests 条目中取出可 await 的 Promise（兼容 dedup 对象与裸 Promise）。
 */
function getInflightPromise(inflight) {
  if (inflight && typeof inflight === 'object' && inflight.promise instanceof Promise) {
    return inflight.promise;
  }
  if (inflight instanceof Promise) {
    return inflight;
  }
  return null;
}

/**
 * 从 pendingRequests 移除去重占位（支持缺失 cacheKey 时按引用兜底扫描）。
 */
function releasePendingDedup(dedup, requestConfig) {
  if (!dedup) {
    return;
  }
  const cacheKey = dedup.cacheKey || generateCacheKey(requestConfig);
  if (cacheKey) {
    const inflight = pendingRequests.get(cacheKey);
    if (inflight === dedup || inflight?.promise === dedup.promise) {
      pendingRequests.delete(cacheKey);
      return;
    }
  }
  for (const [key, entry] of pendingRequests.entries()) {
    if (entry === dedup || entry?.promise === dedup.promise) {
      pendingRequests.delete(key);
      return;
    }
  }
}

/**
 * 在后台执行去重主请求：任务完全结束后再 resolve/reject，并统一清理 pending。
 * 避免 fire-and-forget 链上 rethrow 导致未捕获拒绝。
 */
function launchDedupRequest(dedup, requestConfig, task) {
  void task()
    .then((result) => {
      dedup.resolve(result);
    })
    .catch((error) => {
      dedup.reject(error);
    })
    .finally(() => {
      releasePendingDedup(dedup, requestConfig);
    });
}

/**
 * 释放去重占位并通知等待方。
 * 只要存在 __cacheDedup 即表示已写入 pendingRequests，必须清理。
 */
function settleDedupRequest(requestConfig, outcome) {
  const dedup = requestConfig?.__cacheDedup;
  if (!dedup) {
    return;
  }
  if (outcome === 'resolve') {
    dedup.resolve(requestConfig.__cacheDedupResult);
  } else {
    dedup.reject(requestConfig.__cacheDedupError ?? new Error('请求失败'));
  }
  releasePendingDedup(dedup, requestConfig);
}

/**
 * 等待方请求完成后释放去重状态；若主请求未清理则兜底删除 Map 条目。
 */
function clearWaiterDedupState(requestConfig) {
  if (!requestConfig?.__cacheDedupWaiter) {
    return;
  }
  const dedup = requestConfig.__cacheDedup;
  delete requestConfig.__cacheDedup;
  delete requestConfig.__cacheDedupWaiter;
  releasePendingDedup(dedup, requestConfig);
}


/**
 * 深拷贝可缓存载荷，避免共享引用被后续请求修改。
 */
function cloneCacheValue(value) {
  if (value === undefined || value === null) {
    return value;
  }
  try {
    if (typeof structuredClone === 'function') {
      return structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  } catch (e) {
    logger.warn('缓存数据克隆失败，将使用原值:', e);
    return value;
  }
}

/**
 * 从 axios 响应中提取可序列化的 data 载荷。
 */
function getResponseDataForCache(response) {
  if (response != null && typeof response === 'object' && Object.prototype.hasOwnProperty.call(response, 'data')) {
    return cloneCacheValue(response.data);
  }
  return cloneCacheValue(response);
}

/**
 * 用缓存 data 构造与 axios 兼容的响应对象。
 */
function buildCachedResponse(data, requestConfig) {
  return {
    data,
    status: 200,
    statusText: 'OK (cached)',
    config: requestConfig,
    headers: {}
  };
}

/**
 * 生成请求缓存键
 * 
 * @param {Object} config - axios配置对象
 * @returns {string} 缓存键
 */
function generateCacheKey(config) {
  const { url, method = 'get', params = {}, data = {} } = config;
  
  // 对于GET请求，使用URL+参数作为缓存键
  if (method.toLowerCase() === 'get') {
    const paramStr = JSON.stringify(params);
    return `${method}:${url}:${paramStr}`;
  }
  
  // 对于其他请求，不生成缓存键（不缓存）
  return null;
}

/**
 * 创建缓存装饰器
 *
 * @deprecated 请使用 axios 全局拦截器 {@link createCacheInterceptor}（见 axiosConfig.js）
 *
 * @param {Object} options - 缓存配置
 * @param {number} options.ttl - 缓存过期时间（毫秒），默认5分钟
 * @param {boolean} options.persist - 是否持久化到localStorage
 * @param {boolean} options.enabled - 是否启用缓存
 * @param {boolean} options.dedup - 是否合并相同请求
 * 
 * @returns {Function} 装饰器函数
 */
export function withCache(options = {}) {
  const config = { ...DEFAULT_CONFIG, ...options };
  
  return function(target, propertyKey, descriptor) {
    const originalMethod = descriptor.value;
    
    descriptor.value = async function(...args) {
      if (!config.enabled) {
        return originalMethod.apply(this, args);
      }
      
      // 获取请求配置（假设第一个参数是axios配置对象）
      const requestConfig = args[0];
      const cacheKey = generateCacheKey(requestConfig);
      
      if (!cacheKey) {
        return originalMethod.apply(this, args);
      }
      
      // 检查内存缓存
      let cachedData = cacheStorage.getMemory(cacheKey);
      
      // 如果内存缓存不存在，检查localStorage（仅当配置为持久化时）
      if (!cachedData && config.persist) {
        cachedData = cacheStorage.getLocalStorage(cacheKey);
      }
      
      // 如果有缓存，返回与 axios 响应结构一致的对象（data 为缓存载荷）
      if (cachedData !== null) {
        logger.debug(`命中缓存: ${cacheKey}`);
        return Promise.resolve(buildCachedResponse(cachedData, requestConfig));
      }
      
      // 请求去重：检查是否有相同请求正在进行
      if (config.dedup && pendingRequests.has(cacheKey)) {
        logger.debug(`请求去重: ${cacheKey}`);
        const inflight = pendingRequests.get(cacheKey);
        const pendingPromise = getInflightPromise(inflight);
        if (!pendingPromise) {
          pendingRequests.delete(cacheKey);
        } else {
          return pendingPromise;
        }
      }

      const dedup = config.dedup ? createDedupEntry() : null;
      if (dedup) {
        dedup.cacheKey = cacheKey;
        pendingRequests.set(cacheKey, dedup);
      }

      const runRequest = async () => {
        const response = await originalMethod.apply(this, args);
        const cachePayload = getResponseDataForCache(response);

        cacheStorage.setMemory(cacheKey, cachePayload, config.ttl);
        if (config.persist) {
          cacheStorage.setLocalStorage(cacheKey, cachePayload, config.ttl);
        }

        return response;
      };

      if (!dedup) {
        return runRequest();
      }

      launchDedupRequest(dedup, requestConfig, runRequest);
      return dedup.promise;
    };
    
    return descriptor;
  };
}

/**
 * 缓存工具类
 * 
 * 提供更灵活的缓存操作方式
 */
export class RequestCache {
  /**
   * 获取缓存数据
   * 
   * @param {string} key - 缓存键
   * @returns {any} 缓存数据，如果不存在或过期返回null
   */
  static get(key) {
    let data = cacheStorage.getMemory(key);
    if (data === null) {
      data = cacheStorage.getLocalStorage(key);
    }
    return data;
  }

  /**
   * 设置缓存数据
   * 
   * @param {string} key - 缓存键
   * @param {any} value - 缓存值
   * @param {number} ttl - 过期时间（毫秒），默认5分钟
   * @param {boolean} persist - 是否持久化到localStorage
   */
  static set(key, value, ttl = DEFAULT_CONFIG.ttl, persist = false) {
    cacheStorage.setMemory(key, value, ttl);
    if (persist) {
      cacheStorage.setLocalStorage(key, value, ttl);
    }
  }

  /**
   * 删除指定缓存
   * 
   * @param {string} key - 缓存键
   */
  static delete(key) {
    cacheStorage.delete(key);
  }

  /**
   * 清空所有缓存
   */
  static clear() {
    cacheStorage.clear();
    logger.info('已清空所有请求缓存');
  }

  /**
   * 根据URL模式删除缓存
   * 
   * @param {RegExp|string} pattern - URL模式（正则表达式或字符串）
   */
  static clearByPattern(pattern) {
    const regex = typeof pattern === 'string' ? new RegExp(pattern) : pattern;
    
    // 先收集再删除，避免迭代 Map 时同步 delete 导致漏删
    const memoryKeysToDelete = [];
    for (const key of cacheStorage.memoryCache.keys()) {
      if (regex.test(key)) {
        memoryKeysToDelete.push(key);
      }
    }
    memoryKeysToDelete.forEach((key) => {
      cacheStorage.memoryCache.delete(key);
    });
    
    // 清除localStorage缓存
    try {
      Object.keys(localStorage).forEach(storageKey => {
        if (storageKey.startsWith(cacheStorage.storageKeyPrefix)) {
          const key = storageKey.replace(cacheStorage.storageKeyPrefix, '');
          if (regex.test(key)) {
            localStorage.removeItem(storageKey);
          }
        }
      });
    } catch (e) {
      logger.warn('localStorage清除失败:', e);
    }
    
    logger.info(`已清除匹配模式 "${pattern}" 的缓存`);
  }
}

/**
 * 缓存拦截器工厂函数
 * 
 * 用于创建axios拦截器，自动处理请求缓存
 * 
 * @param {Object} options - 缓存配置
 * @returns {Object} 包含request和response拦截器的对象
 */
export function createCacheInterceptor(options = {}) {
  const config = { ...DEFAULT_CONFIG, ...options };
  
  return {
    /**
     * 请求拦截器
     * 
     * 在发送请求前检查缓存
     */
    request: async (requestConfig) => {
      const cacheKey = generateCacheKey(requestConfig);
      if (!cacheKey) {
        return requestConfig;
      }

      const useCache = shouldUseCacheForRequest(requestConfig, config);
      const useDedup = shouldDedupForRequest(requestConfig, config);
      if (!useCache && !useDedup) {
        return requestConfig;
      }

      // 检查缓存（仅白名单 / enabled 请求）
      if (useCache) {
        let cachedData = cacheStorage.getMemory(cacheKey);
        if (!cachedData && config.persist) {
          cachedData = cacheStorage.getLocalStorage(cacheKey);
        }

        if (cachedData !== null) {
          logger.debug(`命中缓存拦截器: ${cacheKey}`);
          return Promise.reject({
            _cached: true,
            data: cachedData,
            config: requestConfig
          });
        }
      }
      // 请求去重：等待已发起的 in-flight 请求（请求拦截器内注册占位 Promise）
      if (config.dedup && pendingRequests.has(cacheKey)) {
        logger.debug(`请求去重: ${cacheKey}`);
        const inflight = pendingRequests.get(cacheKey);
        const pendingPromise = getInflightPromise(inflight);
        if (!pendingPromise) {
          pendingRequests.delete(cacheKey);
        } else {
          requestConfig.__cacheDedup = inflight?.promise ? inflight : { promise: pendingPromise, cacheKey };
          requestConfig.__cacheDedupWaiter = true;
          return Promise.reject({
            _pending: true,
            promise: pendingPromise,
            config: requestConfig
          });
        }
      }

      if (config.dedup) {
        const dedup = createDedupEntry();
        dedup.cacheKey = cacheKey;
        pendingRequests.set(cacheKey, dedup);
        requestConfig.__cacheDedup = dedup;
      }
      
      return requestConfig;
    },
    
    /**
     * 响应拦截器
     * 
     * 在收到响应后存储缓存
     */
    response: async (response) => {
      const cacheKey = generateCacheKey(response.config);
      if (!cacheKey) {
        return response;
      }

      const useCache = shouldUseCacheForRequest(response.config, config);
      if (useCache) {
        const cachePayload = getResponseDataForCache(response);
        cacheStorage.setMemory(cacheKey, cachePayload, config.ttl);
        if (config.persist) {
          cacheStorage.setLocalStorage(cacheKey, cachePayload, config.ttl);
        }
      }

      if (response.config?.__cacheDedupWaiter) {
        clearWaiterDedupState(response.config);
      } else if (response.config?.__cacheDedup) {
        response.config.__cacheDedupResult = response;
        settleDedupRequest(response.config, 'resolve');
      } else if (config.dedup) {
        pendingRequests.delete(cacheKey);
      }
      
      return response;
    },
    
    /**
     * 错误拦截器
     * 
     * 处理缓存命中和请求去重的特殊情况
     */
    error: async (error) => {
      // 处理缓存命中的特殊错误
      if (error._cached) {
        if (error.config?.__cacheDedupWaiter) {
          clearWaiterDedupState(error.config);
        }
        // 返回缓存 data 作为成功响应
        return buildCachedResponse(error.data, error.config);
      }
      
      // 处理请求去重的特殊错误（等待 in-flight 请求，失败时透传真实错误）
      if (error._pending) {
        try {
          return await error.promise;
        } catch (pendingError) {
          return Promise.reject(pendingError);
        } finally {
          clearWaiterDedupState(error.config);
        }
      }

      if (error.config?.__cacheDedupWaiter) {
        clearWaiterDedupState(error.config);
      } else if (error.config?.__cacheDedup) {
        error.config.__cacheDedupError = error;
        settleDedupRequest(error.config, 'reject');
      } else if (error.config) {
        const cacheKey = generateCacheKey(error.config);
        if (cacheKey && config.dedup) {
          pendingRequests.delete(cacheKey);
        }
      }
      
      return Promise.reject(error);
    }
  };
}

export default RequestCache;