<template>
  <div class="ad-data-health-page">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span>广告数据健康巡检</span>
          <el-tag type="info" size="small">标准粒度：日期 + 产品 + 来源</el-tag>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 告警 -->
        <el-tab-pane label="告警" name="alerts">
          <el-form :inline="true" class="filter-form" @submit.prevent>
            <el-form-item label="日期">
              <el-date-picker v-model="alertQuery.stat_date" type="date" value-format="YYYY-MM-DD" clearable />
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="alertQuery.alert_type" clearable placeholder="全部" style="width: 160px">
                <el-option label="倒扣vs标准" value="baseline_drop" />
                <el-option label="昨天缺数" value="missing" />
                <el-option label="连续断档" value="streak" />
                <el-option label="昨有今无" value="today_gap" />
                <el-option label="日环比跌幅" value="dod_drop" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadAlerts">查询</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="alerts" v-loading="alertsLoading" stripe border size="small">
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column prop="alert_type" label="类型" width="120">
              <template #default="{ row }">{{ alertTypeLabel(row.alert_type) }}</template>
            </el-table-column>
            <el-table-column prop="stat_date" label="业务日" width="110" />
            <el-table-column prop="product_name" label="产品" min-width="160" show-overflow-tooltip />
            <el-table-column prop="data_source" label="来源" width="100" />
            <el-table-column prop="metric" label="指标" width="120">
              <template #default="{ row }">{{ metricLabel(row.metric) }}</template>
            </el-table-column>
            <el-table-column label="标准→当前" width="160">
              <template #default="{ row }">
                {{ fmtNum(row.baseline_value) }} → {{ fmtNum(row.current_value) }}
              </template>
            </el-table-column>
            <el-table-column label="跌幅" width="90">
              <template #default="{ row }">
                {{ row.drop_ratio != null ? (row.drop_ratio * 100).toFixed(1) + '%' : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="说明" min-width="220" show-overflow-tooltip />
            <el-table-column label="已通知" width="80">
              <template #default="{ row }">
                <el-tag :type="row.notified ? 'success' : 'info'" size="small">
                  {{ row.notified ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div class="pager">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="alertsTotal"
              v-model:current-page="alertPage"
              :page-size="50"
              @current-change="loadAlerts"
            />
          </div>
        </el-tab-pane>

        <!-- 标准数据 -->
        <el-tab-pane label="标准数据" name="baselines">
          <el-form :inline="true" class="filter-form" @submit.prevent>
            <el-form-item label="标准日">
              <el-date-picker v-model="baselineQuery.stat_date" type="date" value-format="YYYY-MM-DD" clearable />
            </el-form-item>
            <el-form-item label="来源">
              <el-input v-model="baselineQuery.data_source" clearable placeholder="如 zhisuo" style="width: 140px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadBaselines">查询</el-button>
              <el-button @click="doFreeze(false)">冻结昨天</el-button>
              <el-button type="danger" plain @click="doFreeze(true)">强制重冻</el-button>
            </el-form-item>
          </el-form>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="每天 00:30 自动冻结「昨天」；粒度=日期+产品+来源；指标=请求数 + 收益(扣前)。优先 cross 报表。"
            class="mb-12"
          />
          <el-table :data="baselines" v-loading="baselinesLoading" stripe border size="small">
            <el-table-column prop="stat_date" label="标准日" width="110" />
            <el-table-column prop="product_name" label="产品" min-width="160" show-overflow-tooltip />
            <el-table-column prop="data_source" label="来源" width="100" />
            <el-table-column prop="request_count" label="请求数" width="100" />
            <el-table-column prop="revenue_before" label="收益(扣前)" width="120">
              <template #default="{ row }">{{ fmtNum(row.revenue_before) }}</template>
            </el-table-column>
            <el-table-column prop="row_count" label="明细行" width="90" />
            <el-table-column prop="frozen_at" label="冻结时间" width="160" />
            <el-table-column prop="freeze_batch_id" label="批次" min-width="140" show-overflow-tooltip />
          </el-table>
          <div class="pager">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="baselinesTotal"
              v-model:current-page="baselinePage"
              :page-size="50"
              @current-change="loadBaselines"
            />
          </div>
        </el-tab-pane>

        <!-- 重点关注 -->
        <el-tab-pane label="重点关注" name="watch">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="mb-12"
            title="支持回车、逗号（,，）、分号、空格等自动拆分。生效日（含）起盯，失效日（含）止；生效空=立即，失效空=长期。窗口内上游 API 全部跑完后单独发 Telegram；日常巡检也会强制纳入监控池。"
          />
          <el-form v-loading="settingsLoading" label-width="120px" class="watch-form">
            <el-form-item label="生效日期">
              <el-date-picker
                v-model="settings.watch_effective_date"
                type="date"
                value-format="YYYY-MM-DD"
                clearable
                placeholder="空=立即生效"
                style="width: 220px"
              />
            </el-form-item>
            <el-form-item label="失效日期">
              <el-date-picker
                v-model="settings.watch_expire_date"
                type="date"
                value-format="YYYY-MM-DD"
                clearable
                placeholder="空=长期有效"
                style="width: 220px"
              />
              <el-tag
                v-if="settings.watch_window_status_label"
                :type="settings.watch_window_active ? 'success' : 'info'"
                size="small"
                class="hint"
              >
                {{ settings.watch_window_status_label }}
              </el-tag>
            </el-form-item>
            <el-form-item label="关注产品">
              <el-input
                v-model="settings.watch_products"
                type="textarea"
                :rows="10"
                placeholder="粘贴即可，例如：&#10;https://top01.turskeserije.com.tr&#10;top02.turskeserije.com.tr, top03.turskeserije.com.tr&#10;或：top04.turskeserije.com.tr，top05.turskeserije.com.tr"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="settingsSaving" @click="saveWatchProducts">保存关注配置</el-button>
              <el-button type="success" :loading="watchChecking" @click="doWatchCheck(true)">
                立即检查并发 Telegram
              </el-button>
              <el-button :loading="watchChecking" @click="doWatchCheck(false)">仅检查不通知</el-button>
              <span v-if="settings.updated_at" class="hint">上次更新：{{ settings.updated_at }}</span>
            </el-form-item>
          </el-form>
          <el-table
            v-if="watchItems.length"
            :data="watchItems"
            stripe
            border
            size="small"
            class="mb-12"
          >
            <el-table-column prop="input_name" label="输入" min-width="180" show-overflow-tooltip />
            <el-table-column prop="product_name" label="匹配产品" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.product_name || '（库中暂无）' }}</template>
            </el-table-column>
            <el-table-column label="今日有数据" width="110">
              <template #default="{ row }">
                <el-tag :type="row.has_today_data ? 'success' : 'danger'" size="small">
                  {{ row.has_today_data ? '有' : '无' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="row_count" label="行数" width="80" />
            <el-table-column prop="request_count" label="请求数" width="100" />
            <el-table-column label="收益(扣前)" width="120">
              <template #default="{ row }">{{ fmtNum(row.revenue_before) }}</template>
            </el-table-column>
            <el-table-column label="来源" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                {{ (row.data_sources || []).join(', ') || '-' }}
              </template>
            </el-table-column>
          </el-table>
          <el-input
            v-if="watchOutput"
            v-model="watchOutput"
            type="textarea"
            :rows="12"
            readonly
            placeholder="检查结果摘要"
          />
        </el-tab-pane>

        <!-- 规则配置 -->
        <el-tab-pane label="规则配置" name="settings">
          <el-form v-loading="settingsLoading" label-width="160px" class="settings-form">
            <el-form-item label="跌幅阈值">
              <el-input-number v-model="settings.drop_ratio" :min="0" :max="1" :step="0.01" :precision="4" />
              <span class="hint">默认 0.02 = 2%</span>
            </el-form-item>
            <el-form-item label="请求数地板">
              <el-input-number v-model="settings.request_floor" :min="0" :step="10" />
            </el-form-item>
            <el-form-item label="收益地板">
              <el-input-number v-model="settings.revenue_floor" :min="0" :step="0.1" :precision="4" />
            </el-form-item>
            <el-form-item label="倒扣 vs 日标准">
              <el-switch v-model="settings.enable_baseline_drop" />
            </el-form-item>
            <el-form-item label="昨天缺数">
              <el-switch v-model="settings.enable_missing" />
            </el-form-item>
            <el-form-item label="连续断档">
              <el-switch v-model="settings.enable_streak" />
            </el-form-item>
            <el-form-item label="昨有今无">
              <el-switch v-model="settings.enable_today_gap" />
            </el-form-item>
            <el-form-item label="昨天vs前天日环比">
              <el-switch v-model="settings.enable_dod_drop" />
            </el-form-item>
            <el-form-item label="发送 Telegram">
              <el-switch v-model="settings.enable_telegram" />
            </el-form-item>
            <el-form-item label="告警冷却(小时)">
              <el-input-number v-model="settings.cooldown_hours" :min="0" :max="168" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="settingsSaving" @click="saveSettings">保存</el-button>
              <span v-if="settings.updated_at" class="hint">上次更新：{{ settings.updated_at }}</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 手动执行 -->
        <el-tab-pane label="手动执行" name="run">
          <el-space wrap>
            <el-button type="primary" :loading="running" @click="doRun(true)">跑巡检并发 Telegram</el-button>
            <el-button :loading="running" @click="doRun(false)">跑巡检（不发 Telegram）</el-button>
            <el-button @click="doFreeze(false)">冻结昨天标准</el-button>
          </el-space>
          <el-divider />
          <el-input
            v-model="runOutput"
            type="textarea"
            :rows="18"
            readonly
            placeholder="执行结果摘要会显示在这里"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchHealthAlerts,
  fetchHealthBaselines,
  fetchHealthSettings,
  freezeHealthBaseline,
  runHealthScan,
  runWatchProductsCheck,
  updateHealthSettings,
} from '@/api/adDataHealth'

const activeTab = ref('alerts')

const alerts = ref([])
const alertsTotal = ref(0)
const alertsLoading = ref(false)
const alertPage = ref(1)
const alertQuery = reactive({ stat_date: '', alert_type: '' })

const baselines = ref([])
const baselinesTotal = ref(0)
const baselinesLoading = ref(false)
const baselinePage = ref(1)
const baselineQuery = reactive({ stat_date: '', data_source: '' })

const settingsLoading = ref(false)
const settingsSaving = ref(false)
const settings = reactive({
  drop_ratio: 0.02,
  request_floor: 100,
  revenue_floor: 1,
  enable_baseline_drop: true,
  enable_missing: true,
  enable_streak: true,
  enable_today_gap: true,
  enable_dod_drop: true,
  enable_telegram: true,
  cooldown_hours: 24,
  watch_products: '',
  watch_effective_date: '',
  watch_expire_date: '',
  watch_window_active: false,
  watch_window_status: '',
  watch_window_status_label: '',
  updated_at: '',
})

const running = ref(false)
const runOutput = ref('')
const watchChecking = ref(false)
const watchOutput = ref('')
const watchItems = ref([])

function alertTypeLabel(t) {
  return (
    {
      baseline_drop: '倒扣vs标准',
      missing: '昨天缺数',
      streak: '连续断档',
      today_gap: '昨有今无',
      dod_drop: '日环比跌幅',
    }[t] || t
  )
}

function metricLabel(m) {
  return (
    {
      presence: '有无数据',
      revenue_after: '结算收益',
      revenue_before: '收益(扣前)',
      request_count: '请求数',
    }[m] || m || '-'
  )
}

function fmtNum(v) {
  if (v == null || v === '') return '-'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 })
}

async function loadAlerts() {
  alertsLoading.value = true
  try {
    const res = await fetchHealthAlerts({
      stat_date: alertQuery.stat_date || undefined,
      alert_type: alertQuery.alert_type || undefined,
      limit: 50,
      offset: (alertPage.value - 1) * 50,
    })
    alerts.value = res.items || []
    alertsTotal.value = res.total || 0
  } catch (e) {
    ElMessage.error(e?.message || '加载告警失败')
  } finally {
    alertsLoading.value = false
  }
}

async function loadBaselines() {
  baselinesLoading.value = true
  try {
    const res = await fetchHealthBaselines({
      stat_date: baselineQuery.stat_date || undefined,
      data_source: baselineQuery.data_source || undefined,
      limit: 50,
      offset: (baselinePage.value - 1) * 50,
    })
    baselines.value = res.items || []
    baselinesTotal.value = res.total || 0
  } catch (e) {
    ElMessage.error(e?.message || '加载标准失败')
  } finally {
    baselinesLoading.value = false
  }
}

async function loadSettings() {
  settingsLoading.value = true
  try {
    const res = await fetchHealthSettings()
    Object.assign(settings, res)
    if (settings.watch_products == null) settings.watch_products = ''
    if (settings.watch_effective_date == null) settings.watch_effective_date = ''
    if (settings.watch_expire_date == null) settings.watch_expire_date = ''
  } catch (e) {
    ElMessage.error(e?.message || '加载配置失败（请先执行 sql/ad_data_health_tables.sql）')
  } finally {
    settingsLoading.value = false
  }
}

async function saveSettings() {
  settingsSaving.value = true
  try {
    await updateHealthSettings({ ...settings })
    ElMessage.success('已保存')
    await loadSettings()
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    settingsSaving.value = false
  }
}

async function saveWatchProducts() {
  settingsSaving.value = true
  try {
    await updateHealthSettings({
      watch_products: settings.watch_products || '',
      watch_effective_date: settings.watch_effective_date || '',
      watch_expire_date: settings.watch_expire_date || '',
    })
    ElMessage.success('重点关注配置已保存')
    await loadSettings()
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    settingsSaving.value = false
  }
}

async function doWatchCheck(sendTelegram) {
  watchChecking.value = true
  try {
    const res = await runWatchProductsCheck({ send_telegram: sendTelegram })
    watchItems.value = res.items || []
    watchOutput.value = res.summary_text || JSON.stringify(res, null, 2)
    if (res.reason === 'empty_watch_list') {
      ElMessage.warning('请先填写并保存重点关注产品')
    } else {
      ElMessage.success(
        `检查完成：有数据 ${res.with_data || 0} / 无数据 ${res.without_data || 0}` +
          (sendTelegram ? `，Telegram=${res.sent}` : '')
      )
    }
  } catch (e) {
    ElMessage.error(e?.message || '重点关注检查失败')
  } finally {
    watchChecking.value = false
  }
}

async function doFreeze(force) {
  if (force) {
    await ElMessageBox.confirm(
      '将删除该日已有标准并按当前库重写，确认继续？',
      '强制重冻',
      { type: 'warning' }
    )
  }
  try {
    const res = await freezeHealthBaseline({
      stat_date: baselineQuery.stat_date || undefined,
      force,
    })
    ElMessage.success(
      res.skipped
        ? `已跳过：${res.reason}`
        : `已冻结 ${res.stat_date}，写入 ${res.inserted} 行`
    )
    runOutput.value = JSON.stringify(res, null, 2)
    if (baselineQuery.stat_date || !force) {
      await loadBaselines()
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '冻结失败')
  }
}

async function doRun(sendTelegram) {
  running.value = true
  try {
    const res = await runHealthScan({ send_telegram: sendTelegram })
    runOutput.value = res.summary_text || JSON.stringify(res, null, 2)
    ElMessage.success(
      `巡检完成：报告告警 ${res.report_alerts}，倒扣 ${res.baseline_drop_alerts}，Telegram=${res.telegram_sent}`
    )
    await loadAlerts()
  } catch (e) {
    ElMessage.error(e?.message || '巡检失败')
  } finally {
    running.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'alerts') loadAlerts()
  if (tab === 'baselines') loadBaselines()
  if (tab === 'settings' || tab === 'watch') loadSettings()
})

onMounted(() => {
  loadAlerts()
  loadSettings()
})
</script>

<style scoped>
.ad-data-health-page {
  padding: 12px;
}
.header-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.filter-form {
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.settings-form {
  max-width: 640px;
}
.watch-form {
  max-width: 720px;
}
.hint {
  margin-left: 12px;
  color: #909399;
  font-size: 13px;
}
.mb-12 {
  margin-bottom: 12px;
}
</style>
