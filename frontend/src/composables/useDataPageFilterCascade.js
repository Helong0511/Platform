/**
 * 组合式函数 - 数据页通用筛选级联
 * @file composables/useDataPageFilterCascade.js
 */
import { ref, nextTick, watch } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getClientsWithData,
  getProductsWithData,
  getCountriesWithData,
  getAdUnitsWithData
} from '../api/ad-data';
import {
  getClientsWithTBSearchData,
  getProductsWithTBSearchData,
  getCountriesWithTBSearchData
} from '../api/tb-search-data';
import { extractErrorMessage, isErrorHandled } from '../utils/api';
import {
  DEFAULT_AD_DATA_DIMENSION,
  loadAdDataDimensionPreference,
  saveAdDataDimensionPreference,
  showAdUnitFilterForDimension,
  showCountryFilterForDimension,
  isAdUnitCountryDimension
} from '../constants/adDataDimension';

/** 国家筛选项展示：二字代码 + 中文名（无中文名或与代码相同时仅显示代码） */
export function formatCountryFilterLabel(country) {
  if (!country?.code) {
    return country?.name_zh || '全部区域';
  }
  const name = (country.name_zh || '').trim();
  if (!name || name === country.code) {
    return country.code;
  }
  return `${country.code} ${name}`;
}

function normalizeCountryOption(item) {
  const code = item.code;
  const name_zh = item.name_zh || code;
  return {
    code,
    name_zh,
    label: formatCountryFilterLabel({ code, name_zh })
  };
}

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
  getCountries: (clientId, productId, start, end, dimension, adUnit) =>
    getCountriesWithData(clientId, productId, start, end, dimension, adUnit),
  getAdUnits: (clientId, productId, start, end, dimension, countryCode) =>
    getAdUnitsWithData(clientId, productId, start, end, dimension, countryCode),
  filterCountriesAdvanced: true,
  supportsDimension: true
};

const TB_SEARCH_API = {
  getClients: (start, end) => getClientsWithTBSearchData(start, end),
  getProducts: (clientId, start, end) => getProductsWithTBSearchData(clientId, start, end),
  getCountries: (clientId, productId, start, end) =>
    getCountriesWithTBSearchData(clientId, productId, start, end),
  getAdUnits: null,
  filterCountriesAdvanced: false,
  supportsDimension: false
};

/**
 * 判断筛选项是否为空（未选择 / 「全部」占位）。
 * @param {unknown} value 表单或下拉项的值
 * @returns {boolean} 为空时返回 true
 */
function isEmptyFilterValue(value) {
  return value == null || value === '';
}

/**
 * 判断下拉选项是否与表单当前选中值一致（用于 prune 时校验是否仍有效）。
 *
 * 业务约定：
 * - 产品、客户等 ID 类下拉：选项 value 统一为字符串；表单里可能是数字，仅做 String 化后与选项比对。
 * - 占位项（空字符串）只表示「全部」，不得与任意有效 ID 相等，避免误保留失效选中值。
 *
 * @param {unknown} optionValue 下拉项 value
 * @param {unknown} selectedValue 表单当前选中值
 * @returns {boolean} 二者表示同一有效选项时返回 true
 */
function isFilterOptionSelected(optionValue, selectedValue) {
  if (isEmptyFilterValue(selectedValue)) {
    return isEmptyFilterValue(optionValue);
  }
  if (isEmptyFilterValue(optionValue)) {
    return false;
  }
  return optionValue === String(selectedValue);
}

/**
 * @param {Object} options
 * @param {import('vue').Ref} options.searchForm
 * @param {boolean} [options.includeCountry=false]
 * @param {boolean} [options.includeDimension=false]
 * @param {'ad-data'|'tb-search'} [options.source='ad-data']
 * @param {Object} [options.api] 自定义 API，覆盖 source
 * @param {() => string|number|null|undefined} [options.getUserId] 当前用户 ID，用于统计维度偏好持久化
 */
export function useDataPageFilterCascade({
  searchForm,
  includeCountry = false,
  includeDimension = false,
  source = 'ad-data',
  api: apiOverride = null,
  getUserId = null
}) {
  const api =
    apiOverride || (source === 'tb-search' ? TB_SEARCH_API : AD_DATA_API);

  const users = ref([{ label: '全部客户', value: '' }]);
  const filterProducts = ref([{ label: '全部产品', value: '' }]);
  const filterCountries = ref([{ code: '', name_zh: '全部区域', label: '全部区域' }]);
  const filterAdUnits = ref([{ value: '', label: '全部广告单元' }]);

  const getDimension = () =>
    includeDimension
      ? searchForm.value.dimension || DEFAULT_AD_DATA_DIMENSION
      : null;

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
            value: String(item.id)
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

  const fetchFilterCountries = async (clientId = null, productId = null, adUnit = null) => {
    if (!includeCountry && !includeDimension) return;
    const dimension = getDimension();
    if (includeDimension && !showCountryFilterForDimension(dimension)) {
      filterCountries.value = [{ code: '', name_zh: '全部区域', label: '全部区域' }];
      return;
    }
    try {
      const { startDate, endDate } = getDateRangeFromForm(searchForm.value);
      const result = await api.getCountries(
        clientId || null,
        productId || null,
        startDate,
        endDate,
        dimension,
        adUnit || null
      );
      const data = result?.data || [];
      let countryOptions;
      if (api.filterCountriesAdvanced) {
        countryOptions = data
          .filter((item) => item?.code != null && item.code !== '' && item.code !== 'ZZ')
          .map((item) => normalizeCountryOption({
            code: item.code,
            name_zh: item.name_zh || item.code
          }))
          .filter((item, index, self) => index === self.findIndex((t) => t.code === item.code))
          .sort((a, b) => a.name_zh.localeCompare(b.name_zh, 'zh-CN'));
      } else {
        countryOptions = data.map((item) => normalizeCountryOption({
          code: item.code,
          name_zh: item.name_zh || item.code
        }));
      }
      filterCountries.value = [
        { code: '', name_zh: '全部区域', label: '全部区域' },
        ...countryOptions
      ];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterCountries.value = [{ code: '', name_zh: '全部区域', label: '全部区域' }];
    }
  };

  const getClientId = () => searchForm.value.clientId || null;

  const getProductId = () =>
    searchForm.value.productId ? parseInt(searchForm.value.productId, 10) : null;

  const fetchFilterAdUnits = async (clientId = null, productId = null, countryCode = null) => {
    if (!includeDimension || !api.getAdUnits) return;
    const dimension = getDimension();
    if (!showAdUnitFilterForDimension(dimension)) {
      filterAdUnits.value = [{ value: '', label: '全部广告单元' }];
      return;
    }
    try {
      const { startDate, endDate } = getDateRangeFromForm(searchForm.value);
      const result = await api.getAdUnits(
        clientId || null,
        productId || null,
        startDate,
        endDate,
        dimension,
        countryCode || null
      );
      const data = result?.data || [];
      const adUnitOptions = data
        .filter((item) => item?.value)
        .map((item) => ({
          value: item.value,
          label: item.label || item.value
        }))
        .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));

      filterAdUnits.value = [{ value: '', label: '全部广告单元' }, ...adUnitOptions];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterAdUnits.value = [{ value: '', label: '全部广告单元' }];
    }
  };

  const reloadSecondaryFilters = async () => {
    const clientId = getClientId();
    const productId = getProductId();
    const dimension = getDimension();

    if (includeDimension && isAdUnitCountryDimension(dimension)) {
      await fetchFilterAdUnits(clientId, productId, null);
      await fetchFilterCountries(clientId, productId, searchForm.value.adUnit || null);
      return;
    }

    const countryCode = searchForm.value.countryCode || null;
    await fetchFilterCountries(clientId, productId);
    await fetchFilterAdUnits(clientId, productId, countryCode);
  };

  /** 剔除当前条件下已失效的筛选项（日期/客户变更后调用） */
  const pruneInvalidFilterSelections = (isAdmin = false) => {
    let changed = false;

    if (isAdmin && searchForm.value.clientId) {
      const clientExists = users.value.some((u) =>
        isFilterOptionSelected(u.value, searchForm.value.clientId)
      );
      if (!clientExists) {
        searchForm.value.clientId = '';
        searchForm.value.productId = '';
        if (includeCountry || includeDimension) {
          searchForm.value.countryCode = '';
        }
        if (includeDimension) {
          searchForm.value.adUnit = '';
        }
        changed = true;
      } else {
        searchForm.value.clientId = String(searchForm.value.clientId);
      }
    }

    if (searchForm.value.productId) {
      const productExists = filterProducts.value.some((p) =>
        isFilterOptionSelected(p.value, searchForm.value.productId)
      );
      if (!productExists) {
        searchForm.value.productId = '';
        if (includeCountry || includeDimension) {
          searchForm.value.countryCode = '';
        }
        if (includeDimension) {
          searchForm.value.adUnit = '';
        }
        changed = true;
      } else {
        searchForm.value.productId = String(searchForm.value.productId);
      }
    }

    if (searchForm.value.countryCode) {
      const countryExists = filterCountries.value.some(
        (c) => c.code === searchForm.value.countryCode
      );
      if (!countryExists) {
        searchForm.value.countryCode = '';
        changed = true;
      }
    }

    if (searchForm.value.adUnit) {
      const adUnitExists = filterAdUnits.value.some(
        (u) => u.value === searchForm.value.adUnit
      );
      if (!adUnitExists) {
        searchForm.value.adUnit = '';
        if (includeDimension && isAdUnitCountryDimension(getDimension())) {
          searchForm.value.countryCode = '';
        }
        changed = true;
      }
    }

    return changed;
  };

  const handleFilterClientChange = async () => {
    const clientId = getClientId();
    searchForm.value.productId = '';
    if (includeCountry || includeDimension) {
      searchForm.value.countryCode = '';
    }
    if (includeDimension) {
      searchForm.value.adUnit = '';
    }
    await fetchFilterProducts(clientId);
    await reloadSecondaryFilters();
    fixSelectDisplay();
  };

  const handleFilterProductChange = async () => {
    if (includeDimension) {
      searchForm.value.countryCode = '';
      searchForm.value.adUnit = '';
    } else if (!includeCountry) {
      return;
    }
    await reloadSecondaryFilters();
    fixSelectDisplay();
  };

  const handleDimensionChange = async () => {
    if (includeDimension && getUserId) {
      const userId = getUserId();
      if (userId != null && userId !== '') {
        saveAdDataDimensionPreference(userId, searchForm.value.dimension);
      }
    }
    searchForm.value.countryCode = '';
    searchForm.value.adUnit = '';
    await reloadSecondaryFilters();
    fixSelectDisplay();
  };

  const handleCountryChange = () => {
    fixSelectDisplay();
  };

  const handleAdUnitChange = async () => {
    if (includeDimension && isAdUnitCountryDimension(getDimension())) {
      searchForm.value.countryCode = '';
      await fetchFilterCountries(
        getClientId(),
        getProductId(),
        searchForm.value.adUnit || null
      );
    }
    fixSelectDisplay();
  };

  const reloadFiltersAfterDateChange = async (isAdmin) => {
    if (isAdmin) {
      await fetchClientsWithData();
    }
    await fetchFilterProducts(getClientId());
    await reloadSecondaryFilters();
    pruneInvalidFilterSelections(isAdmin);
  };

  const loadAllFilterOptions = async (isAdmin) => {
    if (isAdmin) {
      await fetchClientsWithData();
    }
    await fetchFilterProducts(getClientId());
    await reloadSecondaryFilters();
    pruneInvalidFilterSelections(isAdmin);
  };

  if (includeDimension && getUserId) {
    watch(
      () => getUserId(),
      (userId) => {
        if (userId == null || userId === '') {
          return;
        }
        const saved = loadAdDataDimensionPreference(userId);
        if (searchForm.value.dimension !== saved) {
          searchForm.value.dimension = saved;
        }
      }
    );
  }

  return {
    users,
    filterProducts,
    filterCountries,
    filterAdUnits,
    fetchClientsWithData,
    fetchFilterProducts,
    fetchFilterCountries,
    fetchFilterAdUnits,
    handleFilterClientChange,
    handleFilterProductChange,
    handleDimensionChange,
    handleCountryChange,
    handleAdUnitChange,
    reloadFiltersAfterDateChange,
    loadAllFilterOptions,
    pruneInvalidFilterSelections
  };
}
