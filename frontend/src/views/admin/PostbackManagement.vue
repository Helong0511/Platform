<!--
Postback 转化管理页面
功能说明：
- 查询和管理所有转化记录（已融合转化日志功能）
- 支持多维度筛选：平台、产品、客户、Click ID、Offer、渠道、广告主、转化状态等
- 提供转化统计、通知记录、状态更新等功能
- 支持查看转化详情、补发通知、更新转化状态等操作

注意：
- 转化日志功能已融合到此页面，原转化日志页面已重定向到此页面
-->
<template>
  <!-- 页面主模板 -->
  <div class="postback-management-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1>Postback 转化管理</h1>
        <div class="stats-info" v-if="stats && stats.length > 0">
          <span class="stat-item" v-for="stat in stats" :key="stat.platform">
            <span class="stat-label">{{ stat.platform }}：</span>
            <span class="stat-value">{{ stat.total_conversions || 0 }}</span>
            <span class="stat-unit">条转化</span>
            <span class="stat-separator">|</span>
            <span class="stat-label">{{ isAdmin ? '总金额 (PayOut(扣))' : '总金额 (PayOut)' }}：</span>
            <span class="stat-value">{{ formatCurrency(stat.total_payout || 0) }}</span>
          </span>
        </div>
      </div>
      <div class="header-right">
        <el-button type="info" :icon="Bell" @click="showNotificationRecords">
          查看通知记录
        </el-button>
      </div>
    </div>

    <!-- 筛选控件 -->
    <!-- 筛选区 -->
    <el-card class="filter-card" shadow="never">
      <!-- 表单区域 -->
      <el-form :inline="true" :model="searchForm" class="filter-form">
        <el-form-item label="平台">
          <el-select v-model="searchForm.platform" placeholder="全部" clearable style="width: 150px;" name="platform" popper-class="select-dropdown" :teleported="true">
            <el-option label="全部" value=""></el-option>
            <el-option label="BFT" value="bft"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="转化ID/点击ID">
          <el-input 
            v-model="searchForm.conversion_or_click_id" 
            placeholder="输入转化ID或点击ID" 
            clearable
            @keyup.enter="fetchConversions"
            style="width: 200px;"
            name="conversion_or_click_id"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="产品ID">
          <el-input-number 
            v-model="searchForm.product_id" 
            placeholder="产品ID" 
            clearable
            :min="1"
            style="width: 150px;"
            name="product_id"
          />
        </el-form-item>
        <el-form-item label="客户ID">
          <el-input-number 
            v-model="searchForm.client_id" 
            placeholder="客户ID" 
            clearable
            :min="1"
            style="width: 150px;"
            name="client_id"
          />
        </el-form-item>
        <!-- 转化日志筛选条件（融合功能） -->
        <el-form-item label="Click ID">
          <el-input 
            v-model="searchForm.click_id" 
            placeholder="Click ID" 
            clearable
            @keyup.enter="fetchConversions"
            style="width: 200px;"
            name="click_id"
          >
            <template #prefix>
              <el-icon :size="16"><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="Offer">
          <el-select 
            v-model="searchForm.offer_id" 
            placeholder="请选择Offer" 
            clearable
            filterable
            style="width: 200px;"
            name="offer_id"
          >
            <el-option
              v-for="offer in offerList"
              :key="offer.id"
              :label="`${offer.id} - ${offer.offer_name}`"
              :value="offer.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="渠道">
          <el-select 
            v-model="searchForm.publisher_id" 
            placeholder="请选择渠道" 
            clearable
            filterable
            style="width: 200px;"
            name="publisher_id"
          >
            <el-option
              v-for="pub in publisherList"
              :key="pub.id"
              :label="pub.publisher_name"
              :value="pub.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="广告主">
          <el-select 
            v-model="searchForm.advertiser_id" 
            placeholder="请选择广告主" 
            clearable
            filterable
            style="width: 200px;"
            name="advertiser_id"
          >
            <el-option
              v-for="adv in advertiserList"
              :key="adv.id"
              :label="adv.advertiser_name"
              :value="adv.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="转化状态">
          <el-select 
            v-model="searchForm.conversion_status" 
            placeholder="全部" 
            clearable
            style="width: 150px;"
            name="conversion_status"
          >
            <el-option label="Approved" value="Approved" />
            <el-option label="Pending" value="Pending" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" class="date-range-item">
          <el-date-picker
            v-model="dateRange"
            name="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 300px;"
            class="date-picker-full"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchConversions" :loading="loading" :icon="Search">
            查询
          </el-button>
          <el-button @click="resetFilter" :icon="Refresh">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 统计数据卡片 -->
    <el-card class="stats-card" shadow="never" v-if="stats && stats.length > 0">
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="stats-header">
          <span>平台统计</span>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :md="8" :lg="6" :xl="4" v-for="stat in stats" :key="stat.platform">
          <div class="stat-card">
            <div class="stat-card-header">
              <span class="platform-name">{{ stat.platform }}</span>
            </div>
            <div class="stat-card-body">
              <div class="stat-row">
                <span class="stat-label">总转化数：</span>
                <span class="stat-value">{{ stat.total_conversions || 0 }}</span>
              </div>
              <div class="stat-row" v-if="isAdmin && stat.total_original_payout">
                <span class="stat-label">PayOut：</span>
                <span class="stat-value">{{ formatCurrency(stat.total_original_payout || 0) }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">{{ isAdmin ? 'PayOut(扣)' : 'PayOut' }}：</span>
                <span class="stat-value highlight">{{ formatCurrency(stat.total_payout || 0) }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">总事件价值：</span>
                <span class="stat-value">{{ formatCurrency(stat.total_event_value || 0) }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">唯一事件数：</span>
                <span class="stat-value">{{ stat.unique_events || 0 }}</span>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 转化数据表格 -->
    <el-card class="data-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span>转化记录列表</span>
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
      <div v-if="selectedConversions.length > 0" class="batch-operations" style="margin-bottom: 10px;">
        <el-button 
          type="warning" 
          size="small"
          :loading="batchResending"
          @click="handleBatchResendNotification"
        >
          <i class="el-icon-refresh"></i> 批量补发通知 ({{ selectedConversions.length }})
        </el-button>
        <el-button 
          type="default" 
          size="small"
          @click="selectedConversions = []"
        >
          取消选择
        </el-button>
      </div>
      
      <el-table
        v-loading="loading"
        :data="conversions"
        border
        stripe
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column
          type="selection"
          width="55"
        />
        <el-table-column v-if="columnVisibility.id" prop="id" label="ID" width="80" align="center" />
        <el-table-column v-if="columnVisibility.platform" prop="platform" label="平台" width="100" align="center">
          <template #default="scope">
            <el-tag type="primary" size="small">
              {{ scope.row.platform }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.conversion_id" prop="conversion_id" label="转化ID/点击ID" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            <el-link 
              v-if="scope.row.conversion_id" 
              type="primary" 
              :underline="false"
              @click="handleViewClickDetail(scope.row.conversion_id)"
            >
              {{ scope.row.conversion_id }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.click_advertiser_name" prop="click_advertiser_name" label="关联广告主" min-width="120" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.click_advertiser_id">
              <div style="font-weight: 500;">{{ scope.row.click_advertiser_name || `广告主_${scope.row.click_advertiser_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ scope.row.click_advertiser_id }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.click_offer_name" prop="click_offer_name" label="关联Offer" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.click_offer_id">
              <div style="font-weight: 500;">{{ scope.row.click_offer_name || `Offer_${scope.row.click_offer_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ scope.row.click_offer_id }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.click_publisher_name" prop="click_publisher_name" label="关联渠道" min-width="100" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.click_publisher_id">
              <div style="font-weight: 500;">{{ scope.row.click_publisher_name || `渠道_${scope.row.click_publisher_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ scope.row.click_publisher_id }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.click_time" prop="click_time" label="点击时间" width="150">
          <template #default="scope">
            {{ scope.row.click_time ? formatDateTime(scope.row.click_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.conversion_status" prop="conversion_status" label="转化状态" width="120" align="center">
          <template #default="scope">
            <el-tag 
              v-if="scope.row.conversion_status" 
              :type="scope.row.conversion_status === 'Approved' ? 'success' : 'warning'" 
              size="small"
            >
              {{ scope.row.conversion_status }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.event_name" prop="event_name" label="事件名称" width="120" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.event_name" type="success" size="small">
              {{ scope.row.event_name }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.event_value" prop="event_value" label="事件价值" width="120" align="right">
          <template #default="scope">
            {{ scope.row.event_value ? formatCurrency(scope.row.event_value) : '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.original_payout" prop="original_payout" label="PayOut" width="150" align="right">
          <template #default="scope">
            <span v-if="scope.row.original_payout">
              {{ formatCurrency(scope.row.original_payout) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.payout" prop="payout" :label="isAdmin ? 'PayOut(扣)' : 'PayOut'" width="150" align="right">
          <template #default="scope">
            <span class="highlight" v-if="scope.row.payout">
              {{ formatCurrency(scope.row.payout) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.devad_id" prop="devad_id" label="设备ID" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.devad_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.os" prop="os" label="操作系统" width="120" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.os" size="small" :type="getOsTagType(scope.row.os)">
              {{ formatOs(scope.row.os) }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.carrier" prop="carrier" label="运营商" width="120" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.carrier" size="small" type="info">
              {{ scope.row.carrier }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.gid" prop="gid" label="渠道(GID)" min-width="100" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.gid">
              <div v-if="scope.row.gid_publisher_name" style="font-weight: 500;">
                {{ scope.row.gid_publisher_name }}
              </div>
              <div style="font-size: 12px; color: #909399;">ID: {{ scope.row.gid }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.product_id" prop="product_id" label="产品" min-width="100" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.product_id">
              <div style="font-weight: 500;">{{ scope.row.product_name || `产品_${scope.row.product_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ scope.row.product_id }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.client_id" prop="client_id" label="客户" min-width="100" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.client_id">
              <div style="font-weight: 500;">{{ scope.row.client_name || `客户_${scope.row.client_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ scope.row.client_id }}</div>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.has_notification" label="通知状态" width="120" align="center">
          <template #default="scope">
            <el-tag 
              v-if="scope.row.has_notification" 
              type="success" 
              size="small"
            >
              已通知
            </el-tag>
            <el-tag 
              v-else 
              type="warning" 
              size="small"
            >
              未通知
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="scope">
            <el-button 
              type="primary" 
              link 
              size="small" 
              @click="handleViewDetail(scope.row)"
            >
              详情
            </el-button>
            <el-button 
              type="info" 
              link 
              size="small" 
              @click="handleViewNotifications(scope.row)"
            >
              通知记录
            </el-button>
            <el-button 
              v-if="!scope.row.has_notification"
              type="warning" 
              link 
              size="small" 
              :loading="resendingNotifications[scope.row.id]"
              @click="handleResendNotification(scope.row)"
            >
              补发通知
            </el-button>
            <!-- 更新转化状态（融合转化日志功能） -->
            <el-dropdown 
              v-if="scope.row.conversion_status !== undefined"
              @command="(cmd) => handleStatusChange(scope.row, cmd)" 
              trigger="click"
            >
              <el-button type="primary" link size="small">
                状态 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="Approved" :disabled="scope.row.conversion_status === 'Approved'">
                    批准
                  </el-dropdown-item>
                  <el-dropdown-item command="Pending" :disabled="scope.row.conversion_status === 'Pending'">
                    待处理
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          :layout="isMobile ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="转化记录详情"
      :width="isMobile ? '95%' : '900px'"
      class="conversion-detail-dialog"
      :close-on-click-modal="false"
      :append-to-body="true"
    >
      <div v-if="currentConversion" class="conversion-detail-content">
        <el-descriptions :column="isMobile ? 1 : 2" border>
          <el-descriptions-item label="记录ID">{{ currentConversion.id }}</el-descriptions-item>
          <el-descriptions-item label="平台">
            <el-tag type="primary">{{ currentConversion.platform }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="转化ID">{{ currentConversion.conversion_id }}</el-descriptions-item>
          <el-descriptions-item label="事件名称">
            <el-tag v-if="currentConversion.event_name" type="success">
              {{ currentConversion.event_name }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="事件价值">
            {{ currentConversion.event_value ? formatCurrency(currentConversion.event_value) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="isAdmin" label="PayOut">
            <span v-if="currentConversion.original_payout">
              {{ formatCurrency(currentConversion.original_payout) }}
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="isAdmin ? 'PayOut(扣)' : 'PayOut'">
            <span class="highlight" v-if="currentConversion.payout">
              {{ formatCurrency(currentConversion.payout) }}
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备ID">{{ currentConversion.devad_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="操作系统">
            <el-tag v-if="currentConversion.os" size="small">
              {{ currentConversion.os }}
            </el-tag>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="运营商">{{ currentConversion.carrier || '-' }}</el-descriptions-item>
          <el-descriptions-item label="IP地址">{{ currentConversion.ip || '-' }}</el-descriptions-item>
          <el-descriptions-item label="渠道ID（gid）">
            <div v-if="currentConversion.gid">
              <div v-if="currentConversion.gid_publisher_name" style="font-weight: 500;">
                {{ currentConversion.gid_publisher_name }}
              </div>
              <div style="font-size: 12px; color: #909399;">ID: {{ currentConversion.gid }}</div>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="产品">
            <div v-if="currentConversion.product_id">
              <div style="font-weight: 500;">{{ currentConversion.product_name || `产品_${currentConversion.product_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ currentConversion.product_id }}</div>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="客户">
            <div v-if="currentConversion.client_id">
              <div style="font-weight: 500;">{{ currentConversion.client_name || `客户_${currentConversion.client_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ currentConversion.client_id }}</div>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(currentConversion.created_at) }}</el-descriptions-item>
          
          <!-- 点击记录关联信息（conversion_id = click_id） -->
          <el-descriptions-item label="点击ID" :span="2" v-if="currentConversion.conversion_id">
            <el-link 
              type="primary" 
              :underline="false"
              @click="handleViewClickDetail(currentConversion.conversion_id)"
            >
              {{ currentConversion.conversion_id }}
            </el-link>
            <div style="font-size: 12px; color: #909399; margin-top: 4px;">
              （转化ID = 点击ID）
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="关联Offer" v-if="currentConversion.click_offer_id">
            <div>
              <div style="font-weight: 500;">{{ currentConversion.click_offer_name || `Offer_${currentConversion.click_offer_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ currentConversion.click_offer_id }}</div>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="关联渠道" v-if="currentConversion.click_publisher_id">
            <div>
              <div style="font-weight: 500;">{{ currentConversion.click_publisher_name || `渠道_${currentConversion.click_publisher_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ currentConversion.click_publisher_id }}</div>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="关联广告主" v-if="currentConversion.click_advertiser_id">
            <div>
              <div style="font-weight: 500;">{{ currentConversion.click_advertiser_name || `广告主_${currentConversion.click_advertiser_id}` }}</div>
              <div style="font-size: 12px; color: #909399;">ID: {{ currentConversion.click_advertiser_id }}</div>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="点击时间" v-if="currentConversion.click_time">
            {{ formatDateTime(currentConversion.click_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="原始数据" :span="2" v-if="currentConversion.raw_data">
            <pre class="json-content">{{ formatJson(currentConversion.raw_data) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-else class="loading-placeholder">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <template #footer>
        <el-button type="primary" @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 通知记录对话框 -->
    <NotificationRecordsDialog
      v-model="notificationRecordsVisible"
      :conversion-id="selectedConversionId"
      :client-id="selectedClientId"
      :product-id="selectedProductId"
      :publisher-id="selectedPublisherId"
      @update:modelValue="handleNotificationDialogClose"
    />

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="500px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">ID（固定显示）</el-checkbox>
        <el-checkbox label="platform">平台</el-checkbox>
        <el-checkbox label="conversion_id" :disabled="true">转化ID/点击ID（固定显示）</el-checkbox>
        <el-checkbox label="click_offer_name">关联Offer</el-checkbox>
        <el-checkbox label="click_publisher_name">关联渠道</el-checkbox>
        <el-checkbox label="click_advertiser_name">关联广告主</el-checkbox>
        <el-checkbox label="click_time">点击时间</el-checkbox>
        <el-checkbox label="conversion_status">转化状态</el-checkbox>
        <el-checkbox label="event_name">事件名称</el-checkbox>
        <el-checkbox label="event_value">事件价值</el-checkbox>
        <el-checkbox v-if="isAdmin" label="original_payout">PayOut</el-checkbox>
        <el-checkbox label="payout">PayOut(扣)</el-checkbox>
        <el-checkbox label="devad_id">设备ID</el-checkbox>
        <el-checkbox label="os">操作系统</el-checkbox>
        <el-checkbox label="carrier">运营商</el-checkbox>
        <el-checkbox label="gid">渠道（gid）</el-checkbox>
        <el-checkbox label="product_id">产品</el-checkbox>
        <el-checkbox label="client_id">客户</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
        <el-checkbox label="has_notification">通知状态</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * Postback 转化管理页面
 * 已融合转化日志功能，提供统一的转化记录查询和管理
 */
import { ref, onMounted, computed } from 'vue';
import { 
  ElButton, ElCard, ElTable, ElTableColumn, ElPagination, ElForm, ElFormItem, 
  ElInput, ElSelect, ElOption, ElTag, ElDialog, ElIcon, ElMessage, ElMessageBox,
  ElDescriptions, ElDescriptionsItem, ElDatePicker, ElInputNumber, ElRow, ElCol, ElLink,
  ElDropdown, ElDropdownMenu, ElDropdownItem, ElCheckboxGroup, ElCheckbox
} from 'element-plus';
import { Search, Refresh, Loading, Bell, ArrowDown, Setting } from '@element-plus/icons-vue';
import { updateConversionStatus } from '../../api/postback';
import { formatDateTime } from '../../utils/dateFormat';
import { formatCurrency, formatOs, getOsTagType, formatJson } from '../../utils/postbackFormat';
import { useDevice } from '../../composables/useDevice';
import { usePostbackConversions } from '../../composables/usePostbackConversions';
import { usePostbackColumnVisibility } from '../../composables/usePostbackColumnVisibility';
import NotificationRecordsDialog from '../../components/admin/NotificationRecordsDialog.vue';
import { resendConversionNotification, batchResendConversionNotification } from '../../api/notification';
import { useAuthStore } from '../../store';
import { logger } from '../../utils/logger';

const { isMobile } = useDevice();
const authStore = useAuthStore();
const isAdmin = computed(() => authStore.isAdmin);

const {
  conversions,
  loading,
  stats,
  pagination,
  searchForm,
  offerList,
  publisherList,
  advertiserList,
  dateRange,
  fetchConversions,
  fetchStats,
  resetFilter,
  loadAll,
  initFilters,
} = usePostbackConversions();

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = usePostbackColumnVisibility(isAdmin);

initFilters();

const selectedConversions = ref([]);
const batchResending = ref(false);
const resendingNotifications = ref({});

// 详情对话框
const detailDialogVisible = ref(false);
const currentConversion = ref(null);

// 通知记录对话框
const notificationRecordsVisible = ref(false);
const selectedConversionId = ref(null);
const selectedClientId = ref(null);
const selectedProductId = ref(null);
const selectedPublisherId = ref(null);

// 查看详情
const handleViewDetail = (row) => {
  currentConversion.value = row;
  detailDialogVisible.value = true;
};

// 查看通知记录（全部）
const showNotificationRecords = () => {
  selectedConversionId.value = null;
  selectedClientId.value = null;
  selectedProductId.value = null;
  selectedPublisherId.value = null;
  notificationRecordsVisible.value = true;
};

// 查看指定转化的通知记录（对应当前行数据）
const handleViewNotifications = (row) => {
  // 优先使用转化记录ID（最精确）
  selectedConversionId.value = row.id || null;
  selectedClientId.value = row.client_id || null;
  selectedProductId.value = row.product_id || null;
  selectedPublisherId.value = null; // 可以从 row 中获取 publisher_id 如果有的话
  notificationRecordsVisible.value = true;
};

// 处理通知记录对话框关闭
const handleNotificationDialogClose = (val) => {
  notificationRecordsVisible.value = val;
  // 对话框关闭时，重置过滤条件
  if (!val) {
    selectedConversionId.value = null;
    selectedClientId.value = null;
    selectedProductId.value = null;
    selectedPublisherId.value = null;
  }
};

// 查看点击详情
const handleViewClickDetail = (clickId) => {
  if (!clickId) return;
  // 打开新窗口或跳转到点击记录详情页
  // 这里可以根据实际需求实现，比如打开对话框或跳转页面
  window.open(`/app/admin/click-log?click_id=${clickId}`, '_blank');
};

// 补发通知
const handleResendNotification = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要补发转化记录 ID ${row.id} 的通知吗？`,
      '补发通知',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    resendingNotifications.value[row.id] = true;
    try {
      await resendConversionNotification(row.id);
      ElMessage.success('通知补发成功');
      
      // 刷新列表数据以获取最新的通知状态（而不是直接修改本地状态）
      await fetchConversions();
      
      // 刷新通知记录对话框（如果已打开）
      if (notificationRecordsVisible.value && 
          selectedConversionId.value === row.id) {
        // 触发通知记录对话框重新加载
        notificationRecordsVisible.value = false;
        setTimeout(() => {
          selectedConversionId.value = row.id;
          notificationRecordsVisible.value = true;
        }, 100);
      }
    } catch (error) {
      ElMessage.error('补发通知失败，请稍后重试');
    } finally {
      resendingNotifications.value[row.id] = false;
    }
  } catch (error) {
    // 用户取消操作或 ElMessageBox 的其他错误，不需要处理
    if (error !== 'cancel') {
      // 如果不是取消操作，记录错误但不显示给用户
      logger.debug('补发通知对话框错误:', error);
    }
  }
};

// 处理表格选择变化
const handleSelectionChange = (selection) => {
  selectedConversions.value = selection;
};

// 批量补发通知
const handleBatchResendNotification = async () => {
  if (selectedConversions.value.length === 0) {
    ElMessage.warning('请先选择要补发的转化记录');
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要批量补发 ${selectedConversions.value.length} 条转化记录的通知吗？`,
      '批量补发通知',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    batchResending.value = true;
    try {
      const conversionIds = selectedConversions.value.map(item => item.id);
      const result = await batchResendConversionNotification(conversionIds);
      
      ElMessage.success(result.message);
      
      // 刷新列表数据以获取最新的通知状态
      await fetchConversions();
      
      // 清空选择
      selectedConversions.value = [];
      
      // 如果有失败的记录，显示详细信息
      if (result.failed_count > 0) {
        await ElMessageBox.alert(
          `失败详情：\n${result.failed_items.map(item => 
            `转化ID ${item.conversion_id}：${item.error}`
          ).join('\n')}`,
          '批量补发结果',
          {
            confirmButtonText: '确定',
            type: 'info'
          }
        );
      }
    } catch (error) {
      ElMessage.error('批量补发通知失败，请稍后重试');
    } finally {
      batchResending.value = false;
    }
  } catch (error) {
    // 用户取消操作或 ElMessageBox 的其他错误，不需要处理
    if (error !== 'cancel') {
      // 如果不是取消操作，记录错误但不显示给用户
      logger.debug('批量补发通知对话框错误:', error);
    }
  }
};

// 更新转化状态（融合转化日志功能）
const handleStatusChange = async (row, status) => {
  try {
    await ElMessageBox.confirm(
      `确定要将转化状态改为 "${status}" 吗？`,
      '确认操作',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    await updateConversionStatus(row.id, status);
    ElMessage.success('状态更新成功');
    row.conversion_status = status;
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('更新状态失败:', error);
      ElMessage.error('更新失败');
    }
  }
};

onMounted(() => {
  loadColumnVisibility();
  loadAll();
});
</script>

<style scoped>
.postback-management-container {
  padding: var(--spacing-lg);
}

.page-header {
  margin-bottom: var(--spacing-lg);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-right {
  display: flex;
  gap: var(--spacing-md);
}

.page-header h1 {
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.stats-info {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.stat-label {
  color: var(--text-secondary);
}

.stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--primary-color);
}

.stat-unit {
  color: var(--text-secondary);
}

.stat-separator {
  margin: 0 var(--spacing-xs);
  color: var(--text-tertiary);
}

.filter-card {
  margin-bottom: var(--spacing-lg);
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}

.stats-card {
  margin-bottom: var(--spacing-lg);
}

.stats-header {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

.stat-card {
  background: var(--bg-light);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.stat-card-header {
  margin-bottom: var(--spacing-xs);
  padding-bottom: var(--spacing-xs);
  border-bottom: 1px solid var(--border-color);
}

.platform-name {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-base);
  color: var(--primary-color);
}

.stat-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-row .stat-label {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.stat-row .stat-value {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
}

.stat-row .stat-value.highlight {
  color: var(--success-color);
  font-size: var(--font-size-base);
}

.data-table-card {
  margin-bottom: var(--spacing-lg);
}

.data-table-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.data-table-card :deep(.el-table) {
  min-width: 1400px;
}

.table-header {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-lg);
}

.pagination-container {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: flex-end;
}

.conversion-detail-content {
  max-height: 70vh;
  overflow-y: auto;
}

.json-content {
  background: var(--bg-light);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  gap: var(--spacing-md);
}

.highlight {
  color: var(--success-color);
  font-weight: var(--font-weight-semibold);
}

/* 移动端优化 */
@media (max-width: 767px) {
  .postback-management-container {
    padding: var(--spacing-md);
  }

  .filter-form {
    flex-direction: column;
  }

  .date-range-item {
    width: 100%;
  }

  .date-picker-full {
    width: 100% !important;
  }

  .data-table-card :deep(.el-card__body) {
    padding: var(--spacing-sm);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .data-table-card :deep(.el-table) {
    min-width: 1300px;
    font-size: 12px;
  }

  .data-table-card :deep(.el-table__cell) {
    padding: 8px 4px;
  }
}
</style>

