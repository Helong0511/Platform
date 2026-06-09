/**
 * 组合式函数 - 数据页通用筛选级联
 * @file composables/useDataPageFilterCascade.js
 */
import { ref, nextTick } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getClientsWithData,
  getProductsWithData,
  getCountriesWithData
} from '../api/ad-data';
import {
  getClientsWithTBSearchData,
  getProductsWithTBSearchData,
  getCountriesWithTBSearchData
} from '../api/tb-search-data';
import { extractErrorMessage, isErrorHandled } from '../utils/api';

function getDateRangeFromForm(searchForm) {
  if (searchForm.dateRange?.length === 2) {
    return {
      startDate: searchForm.dateRange[0],
      endDate: searchForm.dateRange[1]
    };
  }
  return { startDate: null, endDate: null };
}

function fixSelectDisplay() {
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
}

const AD_DATA_API = {
  getClients: (start, end) => getClientsWithData(start, end),
  getProducts: (clientId, start, end) => getProductsWithData(clientId, start, end),
  getCountries: (clientId, productId, start, end) =>
    getCountriesWithData(clientId, productId, start, end),
  filterCountriesAdvanced: true
};

const TB_SEARCH_API = {
  getClients: (start, end) => getClientsWithTBSearchData(start, end),
  getProducts: (clientId, start, end) => getProductsWithTBSearchData(clientId, start, end),
  getCountries: (clientId, productId, start, end) =>
    getCountriesWithTBSearchData(clientId, productId, start, end),
  filterCountriesAdvanced: false
};

/**
 * @param {Object} options
 * @param {import('vue').Ref} options.searchForm
 * @param {boolean} [options.includeCountry=false]
 * @param {'ad-data'|'tb-search'} [options.source='ad-data']
 * @param {Object} [options.api] 自定义 API，覆盖 source
 */
/**
 * 组合式函数 - 数据页通用筛选级联
 * @returns {Object} 响应式状态与业务操作方法
 */
export function useDataPageFilterCascade({
  searchForm,
  includeCountry = false,
  source = 'ad-data',
  api: apiOverride = null
}) {
  const api =
    apiOverride || (source === 'tb-search' ? TB_SEARCH_API : AD_DATA_API);

  // users 响应式状态
  const users = ref([{ label: '全部客户', value: '' }]);
  const filterProducts = ref([{ label: '全部产品', value: '' }]);
  // filterCountries 响应式状态
  const filterCountries = ref([{ code: '', name_zh: '全部区域' }]);

  const fetchClientsWithData = async () => {
    try {
      const { startDate, endDate } = getDateRangeFromForm(searchForm.value);
      const result = await api.getClients(startDate, endDate);
      const data = result?.data || [];
      users.value = [
        { label: '全部客户', value: '' },
        ...data
          .filter((item) => item?.id != null)
          .map((item) => ({
            label: item.full_name || '未知客户',
            value: item.id
          }))
      ];
    } catch {
      users.value = [{ label: '全部客户', value: '' }];
    }
  };

  const fetchFilterProducts = async (clientId) => {
    try {
      const { startDate, endDate } = getDateRangeFromForm(searchForm.value);
      const result = await api.getProducts(clientId || null, startDate, endDate);
      const data = result?.data || [];
      const productOptions = data
        .filter((item) => item?.id != null)
        .map((item) => ({
          label: item.name || '未知产品',
          value: String(item.id),
          id: item.id
        }))
        .sort((a, b) => Number(b.id) - Number(a.id));

      filterProducts.value = [{ label: '全部产品', value: '' }, ...productOptions];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterProducts.value = [{ label: '全部产品', value: '' }];
    }
  };

  const fetchFilterCountries = async (clientId = null, productId = null) => {
    if (!includeCountry) return;
    try {
      const { startDate, endDate } = getDateRangeFromForm(searchForm.value);
      const result = await api.getCountries(
        clientId || null,
        productId || null,
        startDate,
        endDate
      );
      const data = result?.data || [];
      let countryOptions;
      if (api.filterCountriesAdvanced) {
        countryOptions = data
          .filter((item) => item?.code != null && item.code !== '' && item.code !== 'ZZ')
          .map((item) => ({
            code: item.code,
            name_zh: item.name_zh || item.code
          }))
          .filter((item, index, self) => index === self.findIndex((t) => t.code === item.code))
          .sort((a, b) => a.name_zh.localeCompare(b.name_zh, 'zh-CN'));
      } else {
        countryOptions = data.map((item) => ({
          code: item.code,
          name_zh: item.name_zh || item.code
        }));
      }
      filterCountries.value = [{ code: '', name_zh: '全部区域' }, ...countryOptions];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterCountries.value = [{ code: '', name_zh: '全部区域' }];
    }
  };

  const handleFilterClientChange = async (clientId) => {
    searchForm.value.productId = '';
    if (includeCountry) {
      searchForm.value.countryCode = '';
    }
    await fetchFilterProducts(clientId || null);
    if (includeCountry) {
      await fetchFilterCountries(clientId || null, null);
    }
    fixSelectDisplay();
  };

  const handleFilterProductChange = async () => {
    if (!includeCountry) return;
    const clientId = searchForm.value.clientId || null;
    const productId = searchForm.value.productId
      ? parseInt(searchForm.value.productId, 10)
      : null;
    await fetchFilterCountries(clientId, productId);
    if (searchForm.value.countryCode) {
      const exists = filterCountries.value.some(
        (c) => c.code === searchForm.value.countryCode
      );
      if (!exists) {
        searchForm.value.countryCode = '';
      }
    }
    fixSelectDisplay();
  };

  const handleCountryChange = () => {
    fixSelectDisplay();
  };

  const reloadFiltersAfterDateChange = async (isAdmin) => {
    if (isAdmin) {
      await fetchClientsWithData();
    }
    await fetchFilterProducts(searchForm.value.clientId || null);
    if (includeCountry) {
      await fetchFilterCountries(
        searchForm.value.clientId || null,
        searchForm.value.productId ? parseInt(searchForm.value.productId, 10) : null
      );
    }
  };

  const loadAllFilterOptions = async (isAdmin) => {
    if (isAdmin) {
      await fetchClientsWithData();
    }
    await fetchFilterProducts(searchForm.value.clientId || null);
    if (includeCountry) {
      const productId = searchForm.value.productId
        ? parseInt(searchForm.value.productId, 10)
        : null;
      await fetchFilterCountries(searchForm.value.clientId || null, productId);
    }
  };

  return {
    users,
    filterProducts,
    filterCountries,
    fetchClientsWithData,
    fetchFilterProducts,
    fetchFilterCountries,
    handleFilterClientChange,
    handleFilterProductChange,
    handleCountryChange,
    reloadFiltersAfterDateChange,
    loadAllFilterOptions
  };
}

/** @deprecated 使用 useDataPageFilterCascade({ source: 'ad-data' }) */
export function useAdDataFilterCascade(options) {
  return useDataPageFilterCascade({ ...options, source: 'ad-data' });
}
