/**
 * 带 TTL 缓存与请求去重的详情拉取
 * @file utils/cachedDetailFetch.js
 *
 * 创建详情缓存器，避免重复请求同一 ID，支持过期时间与并发去重。
 */
export function createCachedDetailFetcher(options = {}) {
  const ttlMs = options.ttlMs ?? 5 * 60 * 1000;
  const maxEntries = options.maxEntries ?? 50;
  const errorCacheMs = options.errorCacheMs ?? 30 * 1000;

  const cache = new Map();
  const inFlight = new Set();

  const get = async (id, fetchFn, reqOptions = {}) => {
    const { useCache = true, silent = false } = reqOptions;

    if (useCache && cache.has(id)) {
      const cached = cache.get(id);
      if (cached.expiresAt > Date.now()) {
        return cached.data;
      }
      cache.delete(id);
    }

    if (inFlight.has(id)) {
      let retries = 0;
      while (inFlight.has(id) && retries < 20) {
        await new Promise((r) => setTimeout(r, 100));
        retries += 1;
        if (cache.has(id)) {
          const cached = cache.get(id);
          if (cached.expiresAt > Date.now()) {
            return cached.data;
          }
        }
      }
    }

    inFlight.add(id);
    try {
      const data = await fetchFn(id, reqOptions);
      if (cache.size >= maxEntries) {
        const firstKey = cache.keys().next().value;
        cache.delete(firstKey);
      }
      cache.set(id, { data, expiresAt: Date.now() + ttlMs });
      return data;
    } catch (error) {
      const status = error.response?.status;
      if (status !== 429 && status !== 500) {
        cache.set(id, { data: null, expiresAt: Date.now() + errorCacheMs });
      }
      if (status === 429 && silent) {
        throw error;
      }
      throw error;
    } finally {
      inFlight.delete(id);
    }
  };

  const clear = (id = null) => {
    if (id != null) {
      cache.delete(id);
    } else {
      cache.clear();
    }
  };

  return { get, clear };
}
