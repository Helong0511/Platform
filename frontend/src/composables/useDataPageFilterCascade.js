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
import {
  emptyMultiFilterValue,
  isEmptyMultiFilter,
  normalizeMultiFilterArray,
  pruneMultiSelection,
  toCsvFilterValue
} from '../utils/multiFilterValues';

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
  const code = item.code == null || item.code === '' ? '' : String(item.code);
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
 * - 下拉选项 value 统一规范为字符串；表单选中值可能是数字等类型，仅对选中值做 String 化后与选项比对。
 * - 占位项（空字符串）只表示「全部」，不得与任意有效值相等，避免误保留失效选中值。
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
 * 将表单筛选字段值规范为字符串（与下拉 option 类型一致）。
 * @param {import('vue').Ref<Record<string, unknown>>} form 筛选表单 ref
 * @param {string} field 字段名
 * @returns {boolean} 发生写回时返回 true（含数字 123 → 字符串 '123' 等类型变化）
 */
function normalizeFilterFieldToString(form, field) {
  const current = form.value[field];
  const normalized = String(current);
  if (normalized !== current) {
    form.value[field] = normalized;
    return true;
  }
  return false;
}

/**
 * @param {Object} options
 * @param {import('vue').Ref} options.searchForm
 * @param {boolean} [options.includeCountry=false]
 * @param {boolean} [options.includeDimension=false]
 * @param {'ad-data'|'tb-search'} [options.source='ad-data']
 * @param {Object} [options.api] 自定义 API，覆盖 source
 * @param {() => string|number|null|undefined} [options.getUserId] 当前用户 ID，用于统计维度偏好持久化
 * @param {boolean} [options.fixedDimension=false] 固定维度页（不读写 localStorage 偏好）
 * @param {boolean} [options.multiSelect=false] 客户/产品/国家/广告单元是否多选
 * @param {() => boolean|null} [options.getEnableCountryFilter] 页面是否展示国家筛选
 * @param {() => boolean|null} [options.getEnableAdUnitFilter] 页面是否展示广告单元筛选
 */
export function useDataPageFilterCascade({
  searchForm,
  includeCountry = false,
  includeDimension = false,
  source = 'ad-data',
  api: apiOverride = null,
  getUserId = null,
  fixedDimension = false,
  multiSelect = false,
  getEnableCountryFilter = null,
  getEnableAdUnitFilter = null,
  defaultDimension = DEFAULT_AD_DATA_DIMENSION,
  loadDimensionPreference = loadAdDataDimensionPreference,
  saveDimensionPreference = saveAdDataDimensionPreference
}) {
  const api =
    apiOverride || (source === 'tb-search' ? TB_SEARCH_API : AD_DATA_API);

  const users = ref([{ label: '全部客户', value: '' }]);
  const filterProducts = ref([{ label: '全部产品', value: '' }]);
  const filterCountries = ref([{ code: '', name_zh: '全部区域', label: '全部区域' }]);
  const filterAdUnits = ref([{ value: '', label: '全部广告单元' }]);

  const getDimension = () =>
    includeDimension
      ? searchForm.value.dimension || defaultDimension
      : null;

  const clearFilterField = (field) => {
    searchForm.value[field] = emptyMultiFilterValue(multiSelect);
  };

  const getClientFilterParam = () =>
    multiSelect ? toCsvFilterValue(searchForm.value.clientId) : (searchForm.value.clientId || null);

  const getProductFilterParam = () =>
    multiSelect ? toCsvFilterValue(searchForm.value.productId) : (searchForm.value.productId || null);

  const getCountryFilterParam = () =>
    multiSelect ? toCsvFilterValue(searchForm.value.countryCode) : (searchForm.value.countryCode || null);

  const getAdUnitFilterParam = () =>
    multiSelect ? toCsvFilterValue(searchForm.value.adUnit) : (searchForm.value.adUnit || null);

  const shouldLoadCountryOptions = () => {
    if (typeof getEnableCountryFilter === 'function' && getEnableCountryFilter() === false) {
      return false;
    }
    if (!includeCountry && !includeDimension) {
      return false;
    }
    if (includeDimension) {
      return showCountryFilterForDimension(getDimension());
    }
    return true;
  };

  const shouldLoadAdUnitOptions = () => {
    if (typeof getEnableAdUnitFilter === 'function' && getEnableAdUnitFilter() === false) {
      return false;
    }
    if (!includeDimension || !api.getAdUnits) {
      return false;
    }
    return showAdUnitFilterForDimension(getDimension());
  };

  /** 清除与当前统计维度不兼容的筛选项（避免 ad_unit 维度残留国家筛选导致查无数据） */
  const pruneDimensionAwareFilters = () => {
    if (!includeDimension) {
      return false;
    }
    const dimension = getDimension();
    let changed = false;
    if (!showCountryFilterForDimension(dimension) && !isEmptyMultiFilter(searchForm.value.countryCode)) {
      clearFilterField('countryCode');
      changed = true;
    }
    if (!showAdUnitFilterForDimension(dimension) && !isEmptyMultiFilter(searchForm.value.adUnit)) {
      clearFilterField('adUnit');
      changed = true;
    }
    return changed;
  };

  const fetchClientsWithData = async () => {
    try {
      const { startDate, endDate } = getDateRangeFromForm(searchForm.value);
      const result = await api.getClients(startDate, endDate);
      const data = result?.data || [];
      users.value = data
          .filter((item) => item?.id != null)
          .map((item) => ({
            label: item.full_name || '未知客户',
            value: String(item.id)
          }));
      if (!multiSelect) {
        users.value = [{ label: '全部客户', value: '' }, ...users.value];
      }
    } catch {
      users.value = multiSelect ? [] : [{ label: '全部客户', value: '' }];
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

      filterProducts.value = multiSelect
        ? productOptions
        : [{ label: '全部产品', value: '' }, ...productOptions];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterProducts.value = multiSelect ? [] : [{ label: '全部产品', value: '' }];
    }
  };

  const fetchFilterCountries = async (clientId = null, productId = null, adUnit = null) => {
    if (!includeCountry && !includeDimension) return;
    const dimension = getDimension();
    if (includeDimension && !showCountryFilterForDimension(dimension)) {
      filterCountries.value = multiSelect
        ? []
        : [{ code: '', name_zh: '全部区域', label: '全部区域' }];
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
          .filter((item) => item?.code != null && item.code !== '')
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
      filterCountries.value = multiSelect
        ? countryOptions
        : [{ code: '', name_zh: '全部区域', label: '全部区域' }, ...countryOptions];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterCountries.value = multiSelect
        ? []
        : [{ code: '', name_zh: '全部区域', label: '全部区域' }];
    }
  };

  const fetchFilterAdUnits = async (clientId = null, productId = null, countryCode = null) => {
    if (!includeDimension || !api.getAdUnits) return;
    const dimension = getDimension();
    if (!showAdUnitFilterForDimension(dimension)) {
      filterAdUnits.value = multiSelect ? [] : [{ value: '', label: '全部广告单元' }];
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
        .filter((item) => item?.value != null && item.value !== '')
        .map((item) => {
          const value = String(item.value);
          return {
            value,
            label: item.label || value
          };
        })
        .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));

      filterAdUnits.value = multiSelect
        ? adUnitOptions
        : [{ value: '', label: '全部广告单元' }, ...adUnitOptions];
    } catch (error) {
      if (!isErrorHandled(error)) {
        ElMessage.error(extractErrorMessage(error));
      }
      filterAdUnits.value = multiSelect ? [] : [{ value: '', label: '全部广告单元' }];
    }
  };

  const getClientId = () => getClientFilterParam();

  const getProductId = () => {
    const raw = getProductFilterParam();
    if (!raw) return null;
    if (multiSelect) {
      const first = normalizeMultiFilterArray(searchForm.value.productId)[0];
      return first ? parseInt(first, 10) : null;
    }
    return parseInt(searchForm.value.productId, 10);
  };

  const reloadSecondaryFilters = async () => {
    const clientId = getClientFilterParam();
    const productId = getProductFilterParam();
    const dimension = getDimension();
    const loadCountries = shouldLoadCountryOptions();
    const loadAdUnits = shouldLoadAdUnitOptions();

    if (!loadCountries) {
      filterCountries.value = multiSelect
        ? []
        : [{ code: '', name_zh: '全部区域', label: '全部区域' }];
    }
    if (!loadAdUnits) {
      filterAdUnits.value = multiSelect ? [] : [{ value: '', label: '全部广告单元' }];
    }

    if (includeDimension && isAdUnitCountryDimension(dimension)) {
      if (loadAdUnits) {
        await fetchFilterAdUnits(clientId, productId, null);
      }
      if (loadCountries) {
        await fetchFilterCountries(clientId, productId, getAdUnitFilterParam());
      }
      return;
    }

    if (loadCountries) {
      await fetchFilterCountries(clientId, productId);
    }
    if (loadAdUnits) {
      await fetchFilterAdUnits(clientId, productId, getCountryFilterParam());
    }
  };

  const pruneFieldSelection = (field, options, getOptionValue) => {
    if (multiSelect) {
      const pruned = pruneMultiSelection(searchForm.value[field], options, getOptionValue);
      const current = normalizeMultiFilterArray(searchForm.value[field]);
      if (pruned.length !== current.length || pruned.some((value, index) => value !== current[index])) {
        searchForm.value[field] = pruned;
        return true;
      }
      return false;
    }

    if (!isEmptyMultiFilter(searchForm.value[field])) {
      const exists = options.some((option) =>
        isFilterOptionSelected(getOptionValue(option), searchForm.value[field])
      );
      if (!exists) {
        clearFilterField(field);
        return true;
      }
      if (normalizeFilterFieldToString(searchForm, field)) {
        return true;
      }
    }
    return false;
  };

  /** 剔除当前条件下已失效的筛选项（日期/客户变更后调用） */
  const pruneInvalidFilterSelections = (isAdmin = false) => {
    let changed = false;

    if (isAdmin && !isEmptyMultiFilter(searchForm.value.clientId)) {
      if (pruneFieldSelection('clientId', users.value, (item) => item.value)) {
        clearFilterField('productId');
        if (includeCountry || includeDimension) {
          clearFilterField('countryCode');
        }
        if (includeDimension) {
          clearFilterField('adUnit');
        }
        changed = true;
      }
    }

    if (!isEmptyMultiFilter(searchForm.value.productId)) {
      if (pruneFieldSelection('productId', filterProducts.value, (item) => item.value)) {
        if (includeCountry || includeDimension) {
          clearFilterField('countryCode');
        }
        if (includeDimension) {
          clearFilterField('adUnit');
        }
        changed = true;
      }
    }

    if (!isEmptyMultiFilter(searchForm.value.countryCode)) {
      if (pruneFieldSelection('countryCode', filterCountries.value, (item) => item.code)) {
        changed = true;
      }
    }

    if (!isEmptyMultiFilter(searchForm.value.adUnit)) {
      if (pruneFieldSelection('adUnit', filterAdUnits.value, (item) => item.value)) {
        if (includeDimension && isAdUnitCountryDimension(getDimension())) {
          clearFilterField('countryCode');
        }
        changed = true;
      }
    }

    return changed;
  };

  const handleFilterClientChange = async () => {
    clearFilterField('productId');
    if (includeCountry || includeDimension) {
      clearFilterField('countryCode');
    }
    if (includeDimension) {
      clearFilterField('adUnit');
    }
    await fetchFilterProducts(getClientFilterParam());
    await reloadSecondaryFilters();
    fixSelectDisplay();
  };

  const handleFilterProductChange = async () => {
    if (includeDimension) {
      clearFilterField('countryCode');
      clearFilterField('adUnit');
    } else if (!includeCountry) {
      return;
    } else {
      clearFilterField('countryCode');
    }
    await reloadSecondaryFilters();
    fixSelectDisplay();
  };

  const handleDimensionChange = async () => {
    if (includeDimension && getUserId) {
      const userId = getUserId();
      if (userId != null && userId !== '') {
        saveDimensionPreference(userId, searchForm.value.dimension);
      }
    }
    clearFilterField('countryCode');
    clearFilterField('adUnit');
    pruneDimensionAwareFilters();
    await reloadSecondaryFilters();
    fixSelectDisplay();
  };

  const handleCountryChange = async () => {
    if (includeDimension) {
      const dimension = getDimension();
      if (isAdUnitCountryDimension(dimension)) {
        if (!multiSelect) {
          clearFilterField('adUnit');
        }
        await fetchFilterAdUnits(
          getClientFilterParam(),
          getProductFilterParam(),
          getCountryFilterParam()
        );
        await fetchFilterCountries(getClientFilterParam(), getProductFilterParam(), null);
      } else if (showAdUnitFilterForDimension(dimension)) {
        if (!multiSelect) {
          clearFilterField('adUnit');
        }
        await fetchFilterAdUnits(
          getClientFilterParam(),
          getProductFilterParam(),
          getCountryFilterParam()
        );
      }
    }
    fixSelectDisplay();
  };

  const handleAdUnitChange = async () => {
    if (includeDimension && isAdUnitCountryDimension(getDimension())) {
      if (!multiSelect) {
        clearFilterField('countryCode');
      }
      await fetchFilterCountries(
        getClientFilterParam(),
        getProductFilterParam(),
        getAdUnitFilterParam()
      );
    }
    fixSelectDisplay();
  };

  /** 日期变更后按级联顺序刷新筛选项：先校验客户，再产品，再国家/广告单元 */
  const reloadFiltersAfterDateChange = async (isAdmin) => {
    if (isAdmin) {
      await fetchClientsWithData();
      pruneInvalidFilterSelections(true);
    }

    await fetchFilterProducts(getClientFilterParam());
    if (pruneInvalidFilterSelections(isAdmin)) {
      await fetchFilterProducts(getClientFilterParam());
    }

    await reloadSecondaryFilters();
    pruneInvalidFilterSelections(isAdmin);
    fixSelectDisplay();
  };

  const loadAllFilterOptions = async (isAdmin) => {
    await reloadFiltersAfterDateChange(isAdmin);
  };

  if (includeDimension && getUserId && !fixedDimension) {
    watch(
      () => getUserId(),
      (userId) => {
        if (userId == null || userId === '') {
          return;
        }
        const saved = loadDimensionPreference(userId);
        if (searchForm.value.dimension !== saved) {
          searchForm.value.dimension = saved;
          pruneDimensionAwareFilters();
        }
      }
    );
  }

  if (includeDimension && !fixedDimension) {
    watch(
      () => searchForm.value.dimension,
      () => {
        pruneDimensionAwareFilters();
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
    reloadSecondaryFilters,
    loadAllFilterOptions,
    pruneInvalidFilterSelections
  };
}
