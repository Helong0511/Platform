/**
 * 工具模块 - CRUD API 工厂：生成标准增删改查方法
 * @file utils/crudApi.js
 */
import { request } from './api';
import { csrfBeforeMutate } from './csrfMutate';

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function extractResourceName(basePath) {
  const parts = basePath.split('/').filter((p) => p);
  const lastPart = parts[parts.length - 1];
  if (lastPart.endsWith('s')) {
    return lastPart.slice(0, -1);
  }
  return lastPart;
}

/**
 * @param {string} basePath
 * @param {Object} [options]
 * @param {Object} [options.customMethods]
 * @param {string} [options.resourceName] Pascal 名前缀，如 DeductionConfig
 * @param {boolean} [options.paginated]
 * @param {boolean} [options.listTrailingSlash] 列表 URL 是否带尾部斜杠，默认 true
 * @param {string[]} [options.include] 生成的方法：list|get|create|update|delete
 * @param {Object} [options.methodNames] 覆盖方法名 { list, get, create, update, delete }
 *   解构返回值时必须使用此处定义的名称（勿用默认 get${Resource}s 等别名，否则会得到 undefined）
 * @param {Function} [options.beforeMutate] create/update/delete 前执行（如刷新 CSRF）
 * @param {boolean} [options.csrfOnMutate] 为 true 时在 beforeMutate 前先刷新 CSRF
 * @param {string} [options.csrfEndpoint] csrfOnMutate 使用的 GET 端点
 * @param {Object} [options.listOptions] 传给 request 的列表选项
 * @param {Object} [options.getOptions] 传给 request 的详情选项
 * @param {Object} [options.mutateOptions] 传给 request 的写操作选项
 */
/**
 * 创建Crud Api。
 */
export function createCrudApi(basePath, options = {}) {
  const {
    customMethods = {},
    resourceName = null,
    paginated = true,
    listTrailingSlash = true,
    include = ['list', 'get', 'create', 'update', 'delete'],
    methodNames = {},
    beforeMutate = null,
    csrfOnMutate = false,
    csrfEndpoint = undefined,
    listOptions = {},
    getOptions = {},
    mutateOptions = {}
  } = options;

  const runBeforeMutate = async () => {
    if (csrfOnMutate) {
      await csrfBeforeMutate(csrfEndpoint);
    }
    if (beforeMutate) {
      await beforeMutate();
    }
  };

  const resource = resourceName || extractResourceName(basePath);
  const Resource = capitalize(resource);
  const Resources = `${Resource}s`;
  const listUrl = listTrailingSlash ? `${basePath}/` : basePath;

  const names = {
    list: methodNames.list || `get${Resources}`,
    get: methodNames.get || `get${Resource}`,
    create: methodNames.create || `create${Resource}`,
    update: methodNames.update || `update${Resource}`,
    delete: methodNames.delete || `delete${Resource}`
  };

  const runMutate = async (fn) => {
    if (csrfOnMutate || beforeMutate) {
      await runBeforeMutate();
    }
    return fn();
  };

  const api = {};

  if (include.includes('list')) {
    api[names.list] = (params = {}) =>
      request(
        { url: listUrl, method: 'get', params },
        { paginated, ...listOptions }
      );
  }

  if (include.includes('get')) {
    api[names.get] = (id, reqOptions = {}) =>
      request(
        { url: `${basePath}/${id}`, method: 'get' },
        { returnDataOnly: true, ...getOptions, ...reqOptions }
      );
  }

  if (include.includes('create')) {
    api[names.create] = (data) =>
      runMutate(() =>
        request(
          { url: listTrailingSlash ? `${basePath}/` : basePath, method: 'post', data },
          { returnDataOnly: true, ...mutateOptions }
        )
      );
  }

  if (include.includes('update')) {
    api[names.update] = (id, data) =>
      runMutate(() =>
        request(
          { url: `${basePath}/${id}`, method: 'put', data },
          { returnDataOnly: true, ...mutateOptions }
        )
      );
  }

  if (include.includes('delete')) {
    api[names.delete] = (id) =>
      runMutate(() =>
        request(
          { url: `${basePath}/${id}`, method: 'delete' },
          { returnDataOnly: true, ...mutateOptions }
        )
      );
  }

  return {
    ...api,
    ...customMethods
  };
}

/**
 * 创建Multiple Crud Apis。
 */
export function createMultipleCrudApis(configs) {
  const result = {};
  configs.forEach((config) => {
    const { basePath, ...opts } = config;
    Object.assign(result, createCrudApi(basePath, opts));
  });
  return result;
}
