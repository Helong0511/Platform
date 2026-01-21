<template>
  <div class="conversion-summary">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><DataAnalysis /></el-icon>
            <span class="header-title">转化总览</span>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          class="filter-date-picker"
          @change="handleDateChange"
        />
        <el-select
          v-if="isAdmin"
          v-model="filterAdvertiser"
          placeholder="请选择广告主（可选）"
          clearable
          filterable
          class="filter-select"
          @change="handleAdvertiserChange"
        >
          <el-option
            v-for="adv in advertiserList"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
        </el-select>
        <el-select
          v-model="filterOffer"
          placeholder="请选择Offer（可选）"
          clearable
          filterable
          class="filter-select"
          @change="handleOfferChange"
        >
          <el-option
            v-for="offer in offerList"
            :key="offer.id"
            :label="`${offer.id} - ${offer.offer_name}`"
            :value="offer.id"
          />
        </el-select>
        <el-select
          v-if="isAdmin"
          v-model="filterPublisher"
          placeholder="请选择渠道（可选）"
          clearable
          filterable
          class="filter-select"
          @change="handlePublisherChange"
        >
          <el-option
            v-for="pub in publisherList"
            :key="pub.id"
            :label="pub.publisher_name"
            :value="pub.id"
          />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch" class="filter-button">查询</el-button>
        <el-button :icon="Refresh" @click="handleReset" class="filter-button">重置</el-button>
      </div>

      <!-- 统计卡片 -->
      <div class="stats-cards" v-loading="loading">
        <el-card class="stat-card">
          <el-statistic title="总点击" :value="summaryData.total_clicks || 0">
            <template #prefix>
              <el-icon :size="20"><Mouse /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card class="stat-card">
          <el-statistic :title="isAdmin ? '总转化' : '转化数'" :value="getDisplayConversion(summaryData.total_conversions, summaryData.conversion_cap)">
            <template #prefix>
              <el-icon :size="20"><Check /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card class="stat-card">
          <el-statistic title="转化率 (CR)" :value="summaryData.cr || 0" suffix="%">
            <template #prefix>
              <el-icon :size="20"><TrendCharts /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card v-if="isAdmin" class="stat-card">
          <el-statistic title="Revenue" :value="summaryData.total_po || 0" :precision="2">
            <template #prefix>
              <el-icon :size="20"><Money /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card class="stat-card">
          <el-statistic title="Pub Revenue" :value="summaryData.total_po_after_discount || 0" :precision="2">
            <template #prefix>
              <el-icon :size="20"><Money /></el-icon>
            </template>
          </el-statistic>
        </el-card>
        <el-card v-if="isAdmin" class="stat-card">
          <el-statistic title="Profit" :value="summaryData.total_profit || 0" :precision="2">
            <template #prefix>
              <el-icon :size="20"><Money /></el-icon>
            </template>
          </el-statistic>
        </el-card>
      </div>

      <!-- Offer统计表格 -->
      <el-card class="table-card" style="margin-top: 20px;">
        <template #header>
          <div class="table-header">
            <span>转化总览</span>
            <el-button 
              type="text" 
              :icon="Setting" 
              @click="columnSettingVisible = true"
              style="float: right;"
            >
              列设置
            </el-button>
          </div>
        </template>
        <div class="table-wrapper">
          <el-table
            :data="statsList"
            stripe
            style="width: 100%;"
            show-summary
            :summary-method="getSummaries"
          >
            <el-table-column 
              v-if="columnVisibility.offer_id" 
              prop="offer_id" 
              label="Offer ID" 
              width="100" 
              align="right" 
              fixed="left"
            >
              <template #default="scope">
                <el-link
                  v-if="scope.row.offer_id"
                  type="primary"
                  :underline="false"
                  @click="handleOfferClick(scope.row.offer_id)"
                  style="cursor: pointer;"
                >
                  {{ scope.row.offer_id }}
                </el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.offer_name" 
              prop="offer_name" 
              label="Offer Name" 
              min-width="250" 
              show-overflow-tooltip 
              fixed="left"
            >
              <template #default="scope">
                <el-link
                  v-if="scope.row.offer_name"
                  type="primary"
                  :underline="false"
                  @click="handleOfferClick(scope.row.offer_id)"
                  style="cursor: pointer;"
                >
                  {{ scope.row.offer_name }}
                </el-link>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.advertiser_name"
              prop="advertiser_name" 
              label="Advertiser" 
              min-width="100"
              show-overflow-tooltip
            />
            <el-table-column 
              v-if="columnVisibility.publisher_name"
              prop="publisher_name" 
              label="Publisher" 
              min-width="100" 
              show-overflow-tooltip 
            />
            <el-table-column 
              v-if="columnVisibility.click_count" 
              prop="click_count" 
              label="Click" 
              width="120" 
              align="right" 
            />
            <el-table-column 
              v-if="columnVisibility.conversion_count" 
              prop="conversion_count" 
              label="Conversion" 
              width="120" 
              align="right" 
            />
            <el-table-column 
              v-if="columnVisibility.cr" 
              prop="cr" 
              label="CR" 
              width="120" 
              align="right"
            >
              <template #default="scope">
                {{ scope.row.cr }}%
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.po"
              prop="po" 
              label="Revenue" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po !== undefined && scope.row.po !== null">{{ scope.row.po.toFixed(2) }}</span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.po_after_discount"
              prop="po_after_discount" 
              label="Pub Revenue" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po_after_discount !== undefined && scope.row.po_after_discount !== null">
                  {{ scope.row.po_after_discount.toFixed(2) }}
                </span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="isAdmin && columnVisibility.profit"
              prop="profit" 
              label="Profit" 
              width="150" 
              align="right"
            >
              <template #default="scope">
                <span v-if="scope.row.po !== undefined && scope.row.po !== null && scope.row.po_after_discount !== undefined && scope.row.po_after_discount !== null">
                  {{ (scope.row.po - scope.row.po_after_discount).toFixed(2) }}
                </span>
                <span v-else>0.00</span>
              </template>
            </el-table-column>
            <el-table-column 
              v-if="columnVisibility.geo"
              prop="geo" 
              label="GEO" 
              width="120" 
              align="center"
            >
              <template #default="scope">
                <span v-if="scope.row.geo">{{ scope.row.geo }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </el-card>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="400px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="offer_id" :disabled="true">Offer ID（固定显示）</el-checkbox>
        <el-checkbox label="offer_name" :disabled="true">Offer Name（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="advertiser_name">Advertiser</el-checkbox>
        <el-checkbox label="publisher_name">Publisher</el-checkbox>
        <el-checkbox label="click_count">Click</el-checkbox>
        <el-checkbox label="conversion_count">Conversion</el-checkbox>
        <el-checkbox label="cr">CR</el-checkbox>
        <el-checkbox v-if="isAdmin" label="po">Revenue</el-checkbox>
        <el-checkbox label="po_after_discount">Pub Revenue</el-checkbox>
        <el-checkbox v-if="isAdmin" label="profit">Profit</el-checkbox>
        <el-checkbox label="geo">GEO</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Search, Refresh, DataAnalysis, Mouse, Check, TrendCharts, Money, Setting } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getConversionSummary } from '@/api/conversionSummary'
import { getOffers } from '@/api/offer'
import { getPublishers } from '@/api/publisher'
import { getAdvertisers } from '@/api/advertiser'
import { logger } from '@/utils/logger'
import { useAuthStore } from '@/store'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)
const router = useRouter()

const loading = ref(false)
const dateRange = ref([])
const filterOffer = ref(null)
const filterAdvertiser = ref(null)
const filterPublisher = ref(null)
const columnSettingVisible = ref(false)

const offerList = ref([])
const advertiserList = ref([])
const publisherList = ref([])

// 存储所有可用的选项（从统计数据中提取）
const allAdvertisersFromStats = ref([])
const allOffersFromStats = ref([])
const allPublishersFromStats = ref([])
// 存储每个Offer对应的渠道ID集合（用于级联筛选）
const offerPublisherMap = ref(new Map())

const summaryData = reactive({
  total_clicks: 0,
  total_conversions: 0,
  cr: 0,
  total_po: 0,
  total_po_after_discount: 0,
  total_profit: 0,
  conversion_cap: 0, // 客户转化上限
  stats_list: []
})

const statsList = ref([])

// 列显示状态（默认全部显示）
const getDefaultColumnVisibility = () => ({
  offer_id: true,  // 固定显示
  offer_name: true,  // 固定显示
  advertiser_name: isAdmin.value,  // 仅管理员可见
  publisher_name: true,  // 所有用户可见
  click_count: true,
  conversion_count: true,
  cr: true,
  po: isAdmin.value,  // Revenue，仅管理员可见
  po_after_discount: true,  // Pub Revenue，所有用户可见
  profit: isAdmin.value,  // 仅管理员可见
  geo: true  // 所有用户可见
})

const columnVisibility = reactive(getDefaultColumnVisibility())

// 计算属性：将对象转换为数组，用于 el-checkbox-group
const columnVisibilityArray = computed({
  get: () => {
    return Object.keys(columnVisibility).filter(key => columnVisibility[key])
  },
  set: (value) => {
    // 当 checkbox-group 的值变化时，更新对象
    Object.keys(columnVisibility).forEach(key => {
      columnVisibility[key] = value.includes(key)
    })
  }
})

// 从localStorage加载列显示设置
const loadColumnVisibility = () => {
  try {
    const saved = localStorage.getItem('conversionSummary_columnVisibility')
    if (saved) {
      const savedVisibility = JSON.parse(saved)
      // 合并保存的设置和默认设置
      Object.assign(columnVisibility, getDefaultColumnVisibility(), savedVisibility)
      // 确保固定列始终显示
      columnVisibility.offer_id = true
      columnVisibility.offer_name = true
    }
  } catch (error) {
    logger.error('加载列显示设置失败:', error)
  }
}

// 保存列显示设置到localStorage
const saveColumnVisibility = () => {
  try {
    // 只保存可调整的列，不保存固定列
    const toSave = {
      advertiser_name: columnVisibility.advertiser_name,
      publisher_name: columnVisibility.publisher_name,
      click_count: columnVisibility.click_count,
      conversion_count: columnVisibility.conversion_count,
      cr: columnVisibility.cr,
      po: columnVisibility.po,
      po_after_discount: columnVisibility.po_after_discount,
      profit: columnVisibility.profit,
      geo: columnVisibility.geo
    }
    localStorage.setItem('conversionSummary_columnVisibility', JSON.stringify(toSave))
    columnSettingVisible.value = false
    ElMessage.success('列显示设置已保存')
  } catch (error) {
    logger.error('保存列显示设置失败:', error)
    ElMessage.error('保存设置失败')
  }
}

// 加载基础数据
const loadOffers = async () => {
  try {
    const response = await getOffers({ page: 1, page_size: 100 })
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      offerList.value = (response.data || []).slice().sort((a, b) => a.id - b.id)
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error)
  }
}

const loadAdvertisers = async () => {
  try {
    const response = await getAdvertisers({ page: 1, page_size: 100 })
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      advertiserList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载广告主列表失败:', error)
  }
}

const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      publisherList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载渠道列表失败:', error)
  }
}

const setDefaultMonthRange = () => {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), 1)
  const end = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  dateRange.value = [
    start.toISOString().split('T')[0],
    end.toISOString().split('T')[0]
  ]
}

// 从统计数据中提取可用的选项
const extractOptionsFromStats = (statsList) => {
  // 提取广告主列表（去重）
  const advertiserMap = new Map()
  const offerMap = new Map()
  const publisherMap = new Map()
  const offerPubMap = new Map() // 存储每个Offer对应的渠道ID集合
  
  statsList.forEach(stat => {
    // 提取广告主
    if (stat.advertiser_id && stat.advertiser_name) {
      if (!advertiserMap.has(stat.advertiser_id)) {
        advertiserMap.set(stat.advertiser_id, {
          id: stat.advertiser_id,
          advertiser_name: stat.advertiser_name
        })
      }
    }
    
    // 提取Offer
    if (stat.offer_id && stat.offer_name) {
      if (!offerMap.has(stat.offer_id)) {
        offerMap.set(stat.offer_id, {
          id: stat.offer_id,
          offer_name: stat.offer_name,
          advertiser_id: stat.advertiser_id
        })
      }
      // 记录该Offer对应的渠道
      if (stat.publisher_id) {
        if (!offerPubMap.has(stat.offer_id)) {
          offerPubMap.set(stat.offer_id, new Set())
        }
        offerPubMap.get(stat.offer_id).add(stat.publisher_id)
      }
    }
    
    // 提取渠道
    if (stat.publisher_id && stat.publisher_name) {
      if (!publisherMap.has(stat.publisher_id)) {
        publisherMap.set(stat.publisher_id, {
          id: stat.publisher_id,
          publisher_name: stat.publisher_name
        })
      }
    }
  })
  
  allAdvertisersFromStats.value = Array.from(advertiserMap.values())
  allOffersFromStats.value = Array.from(offerMap.values())
  allPublishersFromStats.value = Array.from(publisherMap.values())
  offerPublisherMap.value = offerPubMap
  
  // 更新筛选列表（根据当前筛选条件过滤）
  updateFilterLists()
}

// 根据当前筛选条件更新筛选列表
const updateFilterLists = () => {
  // 如果选择了日期范围，使用从统计数据中提取的列表
  if (dateRange.value && dateRange.value.length === 2) {
    // 更新广告主列表
    if (isAdmin.value) {
      advertiserList.value = allAdvertisersFromStats.value
        .slice()
        .sort((a, b) => a.id - b.id)
      
      // 如果当前选择的广告主不在新列表中，清空选择
      if (filterAdvertiser.value && !advertiserList.value.find(a => a.id === filterAdvertiser.value)) {
        filterAdvertiser.value = null
      }
    }
    
    // 更新Offer列表（如果选择了广告主，只显示该广告主的Offer）
    let filteredOffers = allOffersFromStats.value
    if (filterAdvertiser.value) {
      filteredOffers = filteredOffers.filter(offer => offer.advertiser_id === filterAdvertiser.value)
    }
    offerList.value = filteredOffers
      .slice()
      .sort((a, b) => a.id - b.id)
    
    // 如果当前选择的Offer不在新列表中，清空选择
    if (filterOffer.value && !offerList.value.find(o => o.id === filterOffer.value)) {
      filterOffer.value = null
    }
    
    // 更新渠道列表（如果选择了Offer，只显示该Offer的渠道）
    let filteredPublishers = allPublishersFromStats.value
    if (filterOffer.value) {
      // 从offerPublisherMap中获取该Offer对应的渠道ID集合
      const publisherIds = offerPublisherMap.value.get(filterOffer.value)
      if (publisherIds && publisherIds.size > 0) {
        filteredPublishers = allPublishersFromStats.value.filter(pub => publisherIds.has(pub.id))
      } else {
        // 如果没有找到对应的渠道，显示空列表
        filteredPublishers = []
      }
    }
    publisherList.value = filteredPublishers
      .slice()
      .sort((a, b) => a.id - b.id)
    
    // 如果当前选择的渠道不在新列表中，清空选择
    if (filterPublisher.value && !publisherList.value.find(p => p.id === filterPublisher.value)) {
      filterPublisher.value = null
    }
  } else {
    // 如果没有选择日期范围，加载全部列表（保持原有逻辑）
    if (isAdmin.value) {
      loadAdvertisers()
    }
    loadOffers()
    loadPublishers()
  }
}

// 加载统计数据
const loadData = async (shouldExtractOptions = false) => {
  loading.value = true
  try {
    const params = {
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
      offer_id: filterOffer.value || undefined,
      advertiser_id: filterAdvertiser.value || undefined,
      publisher_id: filterPublisher.value || undefined
    }
    
    // 如果选择了日期范围且需要提取选项，先获取完整数据（不带筛选条件）
    if (shouldExtractOptions && dateRange.value && dateRange.value.length === 2) {
      const fullParams = {
        start_date: dateRange.value[0],
        end_date: dateRange.value[1]
      }
      const fullResponse = await getConversionSummary(fullParams)
      if (fullResponse && fullResponse.data && fullResponse.data.stats_list) {
        extractOptionsFromStats(fullResponse.data.stats_list)
      }
    }
    
    // 获取带筛选条件的数据
    const response = await getConversionSummary(params)
    // response已经是标准格式，直接使用data字段
    if (response && response.data) {
      Object.assign(summaryData, response.data)
      // 计算总利润（如果API没有返回）
      if (summaryData.total_profit === 0 && summaryData.total_po > 0 && summaryData.total_po_after_discount > 0) {
        summaryData.total_profit = summaryData.total_po - summaryData.total_po_after_discount
      }
      statsList.value = response.data.stats_list || []
    }
  } catch (error) {
    logger.error('获取统计数据失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 日期改变
const handleDateChange = () => {
  // 日期改变时，清空下级筛选
  filterAdvertiser.value = null
  filterOffer.value = null
  filterPublisher.value = null
  // 如果选择了日期范围，需要提取选项；否则加载全部列表
  if (dateRange.value && dateRange.value.length === 2) {
    loadData(true)
  } else {
    // 如果没有选择日期范围，加载全部列表
    updateFilterLists()
    loadData(false)
  }
}

// 广告主改变
const handleAdvertiserChange = () => {
  // 清空下级筛选
  filterOffer.value = null
  filterPublisher.value = null
  // 更新Offer和渠道列表
  updateFilterLists()
  // 重新加载数据（不需要重新提取选项，因为日期范围没变）
  loadData(false)
}

// Offer改变
const handleOfferChange = () => {
  // 清空下级筛选
  filterPublisher.value = null
  // 更新渠道列表
  updateFilterLists()
  // 重新加载数据（不需要重新提取选项，因为日期范围没变）
  loadData(false)
}

// 渠道改变
const handlePublisherChange = () => {
  // 重新加载数据（不需要重新提取选项，因为日期范围没变）
  loadData(false)
}

// 搜索
const handleSearch = () => {
  loadData(false)
}

// 重置
const handleReset = () => {
  setDefaultMonthRange()
  filterOffer.value = null
  filterAdvertiser.value = null
  filterPublisher.value = null
  // 重置时需要提取选项
  loadData(true)
}

// 点击Offer ID或Offer Name跳转到Offer管理详情
const handleOfferClick = (offerId) => {
  if (offerId) {
    const route = router.resolve({
      name: 'OfferManagement',
      query: { offer_id: offerId }
    })
    window.open(route.href, '_blank')
  }
}

// 获取显示的转化数（客户显示的不能超出转化上限）
const getDisplayConversion = (conversions, cap) => {
  if (!isAdmin.value && cap > 0) {
    return Math.min(conversions, cap)
  }
  return conversions
}

// 计算表格汇总
const getSummaries = (param) => {
  const { columns, data } = param
  const sums = []
  
  // 计算总点击数和总转化数（用于计算总转化率）
  const totalClicks = data.reduce((sum, item) => sum + (Number(item.click_count) || 0), 0)
  const totalConversions = data.reduce((sum, item) => sum + (Number(item.conversion_count) || 0), 0)
  const totalCr = totalClicks > 0 ? ((totalConversions / totalClicks) * 100).toFixed(2) : '0.00'
  
  // 计算总Revenue和总Pub Revenue
  const totalPo = data.reduce((sum, item) => sum + (Number(item.po) || 0), 0)
  const totalPoAfterDiscount = data.reduce((sum, item) => sum + (Number(item.po_after_discount) || 0), 0)
  const totalProfit = totalPo - totalPoAfterDiscount
  
  columns.forEach((column, index) => {
    const prop = column.property
    
    if (!prop) {
      // 第一列或其他没有property的列，显示"汇总"
      if (index === 0) {
        sums[index] = '汇总'
      } else {
        sums[index] = ''
      }
      return
    }
    
    // 根据列属性计算汇总值
    if (prop === 'click_count') {
      sums[index] = totalClicks
    } else if (prop === 'conversion_count') {
      sums[index] = totalConversions
    } else if (prop === 'cr') {
      sums[index] = totalCr + '%'
    } else if (prop === 'po' && isAdmin.value) {
      sums[index] = totalPo.toFixed(2)
    } else if (prop === 'po_after_discount') {
      sums[index] = totalPoAfterDiscount.toFixed(2)
    } else if (prop === 'profit' && isAdmin.value) {
      sums[index] = totalProfit.toFixed(2)
    } else {
      sums[index] = ''
    }
  })
  
  return sums
}

onMounted(() => {
  // 加载列显示设置
  loadColumnVisibility()
  // 默认查询当月
  setDefaultMonthRange()
  // 初始加载时需要提取选项
  loadData(true)
})
</script>

<style scoped>
.conversion-summary {
  padding: 20px;
}

.page-card {
  min-height: calc(100vh - 100px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  font-size: 20px;
  color: #409eff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}

/* 日期选择器宽度 */
.filter-date-picker {
  width: 100px !important;
}

/* 筛选下拉框统一宽度 */
.filter-select {
  width: 250px !important;
}

/* 按钮样式 */
.filter-button {
  margin-left: 0 !important;
}

/* 确保输入框和下拉框文字不被遮盖 */
.filter-bar :deep(.el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮留出空间 */
}

.filter-bar :deep(.el-select .el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮和下拉箭头留出空间 */
}

.filter-bar :deep(.el-input__inner),
.filter-bar :deep(.el-select__input) {
  padding-right: 8px; /* 文字与清除按钮之间的间距 */
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}

/* 确保清除按钮不遮挡文字 */
.filter-bar :deep(.el-input__suffix) {
  right: 8px;
}

.filter-bar :deep(.el-select .el-input__suffix) {
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 日期选择器特殊处理 */
.filter-date-picker :deep(.el-input__wrapper) {
  padding-right: 30px;
}

.filter-date-picker :deep(.el-input__inner) {
  padding-right: 8px;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.conversion-cap {
  font-size: 14px;
  color: #606266;
  margin-left: 4px;
}

.table-card {
  margin-top: 20px;
}

.table-card :deep(.el-card__body) {
  padding: 20px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.table-wrapper {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.table-wrapper :deep(.el-table) {
  min-width: 1000px;
}

.table-wrapper :deep(.el-table__header-wrapper),
.table-wrapper :deep(.el-table__body-wrapper) {
  overflow-x: visible;
}

.table-header {
  font-weight: 600;
  font-size: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .conversion-summary {
    padding: 10px;
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-bar > * {
    width: 100% !important;
    margin-left: 0 !important;
  }

  .stats-cards {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .table-card :deep(.el-card__body) {
    padding: 10px;
  }

  .table-wrapper :deep(.el-table) {
    min-width: 900px;
    font-size: 12px;
  }

.table-wrapper :deep(.el-table__cell) {
  padding: 8px 4px;
}

/* 汇总行样式 */
.table-wrapper :deep(.el-table__footer-wrapper) {
  font-weight: 600;
}

.table-wrapper :deep(.el-table__footer) {
  background-color: #f5f7fa;
}

.table-wrapper :deep(.el-table__footer .el-table__cell) {
  background-color: #f5f7fa;
  font-weight: 600;
  color: #303133;
}
}
</style>
