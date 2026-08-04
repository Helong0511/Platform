/**
 * 广告数据「来源 / 报表类型」下拉：从后端 metadata-options 拉取并缓存。
 * 新增上游只需改 app/core/ad_data_metadata.py。
 * 前端常量仅保留手工来源 + 稳定报表枚举作离线兜底，不再维护完整上游列表。
 */
import { computed, reactive } from 'vue';
import { getAdDataMetadataOptions } from '../api/ad-data';
import {
  AD_DATA_REPORT_TYPE_DETAIL_OPTIONS as FALLBACK_REPORT_DETAIL,
  AD_DATA_REPORT_TYPE_HINTS as FALLBACK_REPORT_HINTS,
  AD_DATA_REPORT_TYPE_LABELS as FALLBACK_REPORT_LABELS,
  AD_DATA_REPORT_TYPE_OTHER_OPTIONS as FALLBACK_REPORT_OTHER,
  AD_DATA_SOURCE_LABELS as FALLBACK_SOURCE_LABELS,
  AD_DATA_SOURCE_MANUAL_OPTIONS as FALLBACK_SOURCE_MANUAL,
  UPSTREAM_API_DATA_SOURCES as FALLBACK_UPSTREAM
} from '../constants/adDataDimension';

const state = reactive({
  loaded: false,
  loading: false,
  error: '',
  upstream: [...FALLBACK_UPSTREAM],
  manual: [...FALLBACK_SOURCE_MANUAL],
  sourceLabels: { ...FALLBACK_SOURCE_LABELS },
  reportDetail: [...FALLBACK_REPORT_DETAIL],
  reportOther: [...FALLBACK_REPORT_OTHER],
  reportLabels: { ...FALLBACK_REPORT_LABELS },
  reportHints: { ...FALLBACK_REPORT_HINTS }
});

let inflight = null;

function applyCatalog(catalog) {
  if (!catalog || typeof catalog !== 'object') return;
  const sources = catalog.data_sources || {};
  const reports = catalog.report_types || {};

  const upstream = (sources.upstream || [])
    .map((item) => (typeof item === 'string' ? item : item?.value))
    .filter(Boolean);
  const manual = (sources.manual || [])
    .map((item) => (typeof item === 'string' ? item : item?.value))
    .filter(Boolean);

  if (upstream.length) state.upstream = upstream;
  if (manual.length) state.manual = manual;
  if (sources.labels && typeof sources.labels === 'object') {
    state.sourceLabels = { ...FALLBACK_SOURCE_LABELS, ...sources.labels };
  }

  const detail = (reports.detail || [])
    .map((item) => (typeof item === 'string' ? item : item?.value))
    .filter(Boolean);
  const other = (reports.other || [])
    .map((item) => (typeof item === 'string' ? item : item?.value))
    .filter(Boolean);
  if (detail.length) state.reportDetail = detail;
  if (other.length) state.reportOther = other;
  if (reports.labels && typeof reports.labels === 'object') {
    state.reportLabels = { ...FALLBACK_REPORT_LABELS, ...reports.labels };
  }
  if (reports.hints && typeof reports.hints === 'object') {
    state.reportHints = { ...FALLBACK_REPORT_HINTS, ...reports.hints };
  }
  state.loaded = true;
  state.error = '';
}

export async function ensureAdDataMetadataOptions({ force = false } = {}) {
  if (state.loaded && !force) return state;
  if (inflight && !force) return inflight;

  state.loading = true;
  inflight = (async () => {
    try {
      const data = await getAdDataMetadataOptions();
      applyCatalog(data);
    } catch (err) {
      state.error = err?.message || String(err);
      // 保持 fallback，不阻断页面
      console.warn('[ad-data metadata-options] 拉取失败，使用前端兜底常量', err);
    } finally {
      state.loading = false;
      inflight = null;
    }
    return state;
  })();
  return inflight;
}

export function useAdDataMetadataOptions() {
  const upstreamSources = computed(() => state.upstream);
  const manualSources = computed(() => state.manual);
  const sourceLabels = computed(() => state.sourceLabels);
  const reportDetailTypes = computed(() => state.reportDetail);
  const reportOtherTypes = computed(() => state.reportOther);
  const reportLabels = computed(() => state.reportLabels);
  const reportHints = computed(() => state.reportHints);

  const formatSourceLabel = (value) => {
    const key = String(value || 'legacy').trim().toLowerCase() || 'legacy';
    return state.sourceLabels[key] || key;
  };

  const formatReportTypeLabel = (value) => {
    const key = String(value || 'legacy').trim().toLowerCase() || 'legacy';
    return state.reportLabels[key] || key;
  };

  const buildSourceOptions = (currentValue) => {
    const keys = new Set([...state.upstream, ...state.manual]);
    const raw = String(currentValue || '').trim().toLowerCase();
    if (raw) keys.add(raw);
    const ordered = [
      ...state.upstream,
      ...state.manual.filter((k) => keys.has(k)),
      ...[...keys].filter((k) => !state.upstream.includes(k) && !state.manual.includes(k))
    ];
    return [...new Set(ordered)].map((value) => ({
      value,
      label: `${formatSourceLabel(value)} (${value})`
    }));
  };

  const buildReportTypeOptions = (currentValue) => {
    const keys = new Set([...state.reportDetail, ...state.reportOther]);
    const raw = String(currentValue || '').trim().toLowerCase();
    if (raw) keys.add(raw);
    const ordered = [
      ...state.reportDetail,
      ...state.reportOther.filter((k) => keys.has(k)),
      ...[...keys].filter(
        (k) => !state.reportDetail.includes(k) && !state.reportOther.includes(k)
      )
    ];
    return [...new Set(ordered)].map((value) => ({
      value,
      label: formatReportTypeLabel(value),
      hint: state.reportHints[value] || ''
    }));
  };

  return {
    state,
    loaded: computed(() => state.loaded),
    loading: computed(() => state.loading),
    upstreamSources,
    manualSources,
    sourceLabels,
    reportDetailTypes,
    reportOtherTypes,
    reportLabels,
    reportHints,
    formatSourceLabel,
    formatReportTypeLabel,
    buildSourceOptions,
    buildReportTypeOptions,
    ensureAdDataMetadataOptions
  };
}
