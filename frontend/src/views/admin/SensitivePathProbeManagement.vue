<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header">敏感路径拦截日志</div>
      </template>

      <div class="toolbar">
        <el-select v-model="statsDays" style="width: 140px">
          <el-option :value="1" label="近1天" />
          <el-option :value="7" label="近7天" />
          <el-option :value="30" label="近30天" />
          <el-option :value="90" label="近90天" />
        </el-select>
        <el-input-number v-model="cleanupDays" :min="1" :max="3650" />
        <el-button type="warning" @click="handleCleanup">清理过期日志</el-button>
        <el-button @click="refreshAll">刷新全部</el-button>
      </div>

      <div class="charts">
        <el-card class="chart-card" shadow="never">
          <template #header>TOP IP 命中次数</template>
          <div ref="topIpChartRef" class="chart"></div>
        </el-card>
        <el-card class="chart-card" shadow="never">
          <template #header>TOP 路径命中次数</template>
          <div ref="topPathChartRef" class="chart"></div>
        </el-card>
      </div>

      <el-card shadow="never" style="margin-bottom: 16px;">
        <template #header>黑名单IP</template>
        <div class="block-row">
          <el-input v-model="blockForm.blocked_ip" placeholder="IP地址" style="width: 220px" />
          <el-input v-model="blockForm.reason" placeholder="封禁原因（可选）" style="width: 320px" />
          <el-button type="danger" @click="handleAddBlockedIp">一键封禁IP</el-button>
        </div>
        <el-table v-loading="blockedLoading" :data="blockedIps" stripe style="margin-top: 12px;">
          <el-table-column prop="blocked_ip" label="IP" width="200" />
          <el-table-column prop="reason" label="原因" min-width="220" show-overflow-tooltip />
          <el-table-column prop="is_active" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'danger' : 'info'">{{ row.is_active ? '已封禁' : '已解封' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button
                v-if="row.is_active"
                type="primary"
                link
                @click="handleUnblock(row)"
              >
                解封
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <div class="filters">
        <el-input v-model="filters.client_ip" placeholder="客户端IP" clearable style="width: 180px" />
        <el-input v-model="filters.request_path" placeholder="请求路径关键字" clearable style="width: 260px" />
        <el-input v-model="filters.matched_rule" placeholder="命中规则" clearable style="width: 220px" />
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="tableData" stripe>
        <el-table-column prop="created_at" label="拦截时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="method" label="方法" width="90" />
        <el-table-column prop="client_ip" label="IP" width="160" />
        <el-table-column prop="request_path" label="请求路径" min-width="340" show-overflow-tooltip />
        <el-table-column prop="query_string" label="Query" min-width="240" show-overflow-tooltip />
        <el-table-column prop="matched_rule" label="命中规则" min-width="180" show-overflow-tooltip />
        <el-table-column prop="user_agent" label="User-Agent" min-width="280" show-overflow-tooltip />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.client_ip && row.client_ip !== 'unknown'"
              type="danger"
              link
              @click="handleQuickBlock(row)"
            >
              封禁IP
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import {
  addSensitiveBlockedIp,
  cleanupSensitivePathProbeLogs,
  getSensitiveBlockedIps,
  getSensitivePathProbeLogs,
  getSensitivePathTopStats,
  unblockSensitiveBlockedIp,
} from '@/api/sensitive-path-probes'
import { formatDate } from '@/utils/date'

const loading = ref(false)
const blockedLoading = ref(false)
const tableData = ref([])
const blockedIps = ref([])
const filters = reactive({
  client_ip: '',
  request_path: '',
  matched_rule: '',
})
const blockForm = reactive({
  blocked_ip: '',
  reason: '',
})
const statsDays = ref(7)
const cleanupDays = ref(90)
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})
const topIpChartRef = ref(null)
const topPathChartRef = ref(null)
let topIpChart = null
let topPathChart = null

const loadData = async () => {
  loading.value = true
  try {
    const res = await getSensitivePathProbeLogs({
      page: pagination.page,
      page_size: pagination.pageSize,
      client_ip: filters.client_ip || undefined,
      request_path: filters.request_path || undefined,
      matched_rule: filters.matched_rule || undefined,
    })
    tableData.value = res.data || []
    pagination.total = res.total || 0
  } catch (e) {
    ElMessage.error(e?.message || '加载敏感路径拦截日志失败')
  } finally {
    loading.value = false
  }
}

const loadBlockedIps = async () => {
  blockedLoading.value = true
  try {
    const res = await getSensitiveBlockedIps({
      page: 1,
      page_size: 50,
      is_active: true,
    })
    blockedIps.value = res.data || []
  } catch (e) {
    ElMessage.error(e?.message || '加载黑名单IP失败')
  } finally {
    blockedLoading.value = false
  }
}

const renderBarChart = (chartRef, chartInstanceRef, title, rows) => {
  if (!chartRef.value) return chartInstanceRef
  const names = rows.map(item => item.name)
  const counts = rows.map(item => item.count)
  const instance = chartInstanceRef || echarts.init(chartRef.value)
  instance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 80 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { interval: 0, rotate: 20 },
    },
    yAxis: { type: 'value' },
    series: [{
      name: title,
      type: 'bar',
      data: counts,
      itemStyle: { color: '#409EFF' },
    }],
  })
  return instance
}

const loadTopStats = async () => {
  try {
    const data = await getSensitivePathTopStats({ days: statsDays.value, limit: 10 })
    await nextTick()
    topIpChart = renderBarChart(topIpChartRef, topIpChart, '命中次数', data?.top_ips || [])
    topPathChart = renderBarChart(topPathChartRef, topPathChart, '命中次数', data?.top_paths || [])
  } catch (e) {
    ElMessage.error(e?.message || '加载TOP统计失败')
  }
}

const handleAddBlockedIp = async () => {
  if (!blockForm.blocked_ip.trim()) {
    ElMessage.warning('请先输入IP地址')
    return
  }
  try {
    await addSensitiveBlockedIp({
      blocked_ip: blockForm.blocked_ip.trim(),
      reason: blockForm.reason.trim() || undefined,
    })
    ElMessage.success('IP封禁成功')
    blockForm.blocked_ip = ''
    blockForm.reason = ''
    await loadBlockedIps()
  } catch (e) {
    ElMessage.error(e?.message || 'IP封禁失败')
  }
}

const handleUnblock = async (row) => {
  try {
    await ElMessageBox.confirm(`确认解封 IP ${row.blocked_ip} 吗？`, '解封确认', {
      type: 'warning',
    })
    await unblockSensitiveBlockedIp(row.id)
    ElMessage.success('IP已解封')
    await loadBlockedIps()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || 'IP解封失败')
    }
  }
}

const handleQuickBlock = async (row) => {
  blockForm.blocked_ip = row.client_ip
  blockForm.reason = `来自敏感路径拦截日志，路径: ${row.request_path}`
  await handleAddBlockedIp()
}

const handleCleanup = async () => {
  try {
    await ElMessageBox.confirm(
      `确认清理 ${cleanupDays.value} 天前的敏感路径拦截日志吗？`,
      '清理确认',
      { type: 'warning' }
    )
    const res = await cleanupSensitivePathProbeLogs({ retention_days: cleanupDays.value })
    ElMessage.success(`清理完成，删除 ${res?.deleted_count ?? 0} 条`)
    await loadData()
    await loadTopStats()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || '日志清理失败')
    }
  }
}

const refreshAll = async () => {
  await Promise.all([loadData(), loadBlockedIps(), loadTopStats()])
}

const handleSearch = () => {
  pagination.page = 1
  loadData()
}

const handleReset = () => {
  filters.client_ip = ''
  filters.request_path = ''
  filters.matched_rule = ''
  pagination.page = 1
  loadData()
}

const handleSizeChange = (size) => {
  pagination.pageSize = size
  pagination.page = 1
  loadData()
}

const handleCurrentChange = (page) => {
  pagination.page = page
  loadData()
}

onMounted(refreshAll)

onBeforeUnmount(() => {
  if (topIpChart) topIpChart.dispose()
  if (topPathChart) topPathChart.dispose()
})
</script>

<style scoped>
.page { padding: 20px; }
.header { font-size: 18px; font-weight: 600; }
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.chart-card { min-height: 320px; }
.chart { width: 100%; height: 260px; }
.block-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.filters { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }
@media (max-width: 1024px) {
  .charts { grid-template-columns: 1fr; }
}
</style>
