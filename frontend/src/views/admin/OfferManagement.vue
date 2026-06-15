<!--
  Offer 管理页面
  职责：Offer CRUD、Tracklink 配置、详情统计 Tab、列显隐与批量操作。
  @file views/admin/OfferManagement.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="offer-management">
    <el-card class="page-card">
      <!-- 卡片标题栏 -->
    <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Box /></el-icon>
            <span class="header-title">Offer管理</span>
          </div>
          <div class="header-right">
            <el-button 
              type="text" 
              :icon="Setting" 
              @click="columnSettingVisible = true"
              style="margin-right: 10px;"
            >
              列设置
            </el-button>
            <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="handleAdd">添加Offer</el-button>
          </div>
        </div>
      </template>

      <!-- 搜索栏 -->
      <OfferSearchBar
        v-model:search-keyword="searchKeyword"
        v-model:filter-advertiser="filterAdvertiser"
        v-model:filter-status="filterStatus"
        v-model:filter-active="filterActive"
        v-model:filter-publisher="filterPublisher"
        :is-admin="isAdmin"
        :advertiser-list="advertiserList"
        :publisher-list="publisherList"
        @search="handleSearch"
        @reset="handleReset"
        @advertiser-change="handleAdvertiserChange"
        @status-change="handleStatusChange"
        @active-change="handleActiveChange"
        @publisher-change="handlePublisherChange"
      />

      <!-- 表格 -->
      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="tableData"
          stripe
          style="width: 100%; margin-top: 20px;"
        >
        <el-table-column v-if="columnVisibility.id" prop="id" label="Offer ID" width="100" align="center" fixed="left" />
        <el-table-column v-if="columnVisibility.offer_name" prop="offer_name" label="Offer名称" width="250" show-overflow-tooltip fixed="left" />
        <el-table-column v-if="isAdmin && columnVisibility.advertiser_name" prop="advertiser_name" label="广告主" width="150" show-overflow-tooltip />
        <el-table-column v-if="isAdmin && columnVisibility.advertiser_offer_id" prop="advertiser_offer_id" label="上游Offer ID" width="150" show-overflow-tooltip />
        <el-table-column v-if="isAdmin && columnVisibility.payout" prop="payout" label="上游PO" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.payout">{{ scope.row.payout.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="affiliate_payout" :label="isAdmin ? '下游PO' : 'PO'" width="90" align="right">
          <template #default="scope">
            <template v-if="!isAdmin && currentClientId && scope.row.assigned_publishers">
              <!-- 客户登录：显示分配给该客户渠道的PO -->
              <span v-if="getRowClientPublisherPO(scope.row)">
                {{ getRowClientPublisherPO(scope.row).toFixed(2) }}
              </span>
              <span v-else>-</span>
            </template>
            <template v-else>
              <!-- 管理员：显示Offer级别的PO -->
              <span v-if="scope.row.affiliate_payout">{{ scope.row.affiliate_payout.toFixed(2) }}</span>
              <span v-else>-</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.country" prop="country" label="国家" width="80" align="center" />
        <el-table-column v-if="columnVisibility.category" prop="category" label="分类" width="120" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.category">{{ scope.row.category }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.type" prop="type" label="类型" width="80" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.type">{{ scope.row.type }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="upstream_cap" label="上游Cap" width="100" align="center">
          <template #default="scope">
            <span v-if="scope.row.upstream_cap">{{ scope.row.upstream_cap }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.downstream_cap" prop="downstream_cap" :label="isAdmin ? '下游Cap' : 'Cap'" width="90" align="center">
          <template #default="scope">
            <template v-if="!isAdmin && currentClientId && scope.row.assigned_publishers">
              <!-- 客户登录：显示分配给该客户渠道的Cap -->
              <span v-if="getRowClientPublisherCap(scope.row) !== null && getRowClientPublisherCap(scope.row) !== undefined">
                {{ getRowClientPublisherCap(scope.row) }}
              </span>
              <span v-else>-</span>
            </template>
            <template v-else>
              <!-- 管理员：显示Offer级别的Cap -->
              <span v-if="scope.row.downstream_cap">{{ scope.row.downstream_cap }}</span>
              <span v-else>-</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column prop="preview_link" label="预览链接" width="120" show-overflow-tooltip>
          <template #default="scope">
            <el-link v-if="scope.row.preview_link" :href="scope.row.preview_link" target="_blank" type="primary" :underline="false">
              预览
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.downstream_tracklink" :label="isAdmin ? '下游Tracklink' : 'Tracklink'" width="380" show-overflow-tooltip>
          <template #default="scope">
            <template v-if="!isAdmin && currentClientId && scope.row.assigned_publishers">
              <!-- 客户登录：显示该客户渠道的Tracklink -->
              <el-link 
                v-if="getRowClientPublisherTracklink(scope.row)"
                :href="getRowClientPublisherTracklink(scope.row)" 
                target="_blank" 
                type="primary"
                style="word-break: break-all;"
              >
                {{ getRowClientPublisherTracklink(scope.row) }}
              </el-link>
              <span v-else>-</span>
            </template>
            <template v-else>
              <!-- 管理员：显示原始Tracklink -->
              <el-link 
                v-if="scope.row.downstream_tracklink"
                :href="scope.row.downstream_tracklink" 
                target="_blank" 
                type="primary"
                style="word-break: break-all;"
              >
                {{ scope.row.downstream_tracklink }}
              </el-link>
              <span v-else>-</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.click_validity_hours" prop="click_validity_hours" label="点击有效期(小时)" width="120" align="center">
          <template #default="scope">
            <span v-if="scope.row.click_validity_hours">{{ scope.row.click_validity_hours }}</span>
            <span v-else>720</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="assigned_publishers" label="分配渠道" width="250" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.assigned_publishers && scope.row.assigned_publishers.length > 0">
              <el-tag
                v-for="pub in scope.row.assigned_publishers"
                :key="pub.id"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px;"
              >
                {{ pub.publisher_name }}
              </el-tag>
            </div>
            <el-tag v-else type="info" size="small">未分配</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.status" prop="status" label="状态" width="110" align="center">
          <template #default="scope">
            <el-switch
              :model-value="scope.row.status === 'Active'"
              @change="(value) => handleToggleStatus(scope.row, value)"
              :active-text="scope.row.status === 'Active' ? 'Active' : ''"
              :inactive-text="scope.row.status !== 'Active' ? 'Inactive' : ''"
              aria-label="切换状态"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin && columnVisibility.is_active" prop="is_active" label="激活" width="90" align="center">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              @change="handleToggleActive(scope.row)"
              :active-text="scope.row.is_active ? '激活' : ''"
              :inactive-text="!scope.row.is_active ? '禁用' : ''"
              aria-label="切换激活状态"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.created_at" prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="columnVisibility.updated_at" prop="updated_at" label="更新时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="scope">
            <el-button type="info" link :icon="View" @click="handleViewDetails(scope.row)">详情</el-button>
            <el-button v-if="isAdmin" type="primary" link :icon="Edit" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button v-if="isAdmin" type="danger" link :icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑Offer' : '添加Offer'"
      width="900px"
      :append-to-body="true"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Offer名称" prop="offer_name">
              <el-input v-model="formData.offer_name" placeholder="请输入Offer名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="广告主" prop="advertiser_id">
              <el-select
                v-model="formData.advertiser_id"
                placeholder="请选择广告主"
                filterable
                popper-class="select-dropdown"
                :teleported="true"
                style="width: 100%;"
              >
                <el-option
                  v-for="adv in advertiserList"
                  :key="adv.id"
                  :label="adv.advertiser_name"
                  :value="adv.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="上游Offer ID" prop="advertiser_offer_id">
              <el-input v-model="formData.advertiser_offer_id" placeholder="上游系统中的Offer ID（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="国家" prop="country">
              <el-input v-model="formData.country" placeholder="国家（可选）" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="分类" prop="category">
              <el-input v-model="formData.category" placeholder="分类（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类型" prop="type">
              <el-input v-model="formData.type" placeholder="类型（可选）" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="上游PO" prop="payout">
              <el-input-number
                v-model="formData.payout"
                :min="0"
                :precision="2"
                placeholder="上游支付金额"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="上游Cap" prop="upstream_cap">
              <el-input-number
                v-model="formData.upstream_cap"
                :min="0"
                placeholder="上游转化上限"
                style="width: 100%;"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin: 16px 0;"
        >
          <template #title>
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>重要提示</span>
            </div>
          </template>
          <div style="margin-top: 8px; line-height: 1.6;">
            下游PO和下游Cap现在需要在<strong>"分配渠道"</strong>部分为每个渠道单独配置。每个渠道可以设置不同的下游PO和下游Cap值。
          </div>
        </el-alert>

        <el-form-item label="预览链接" prop="preview_link">
          <el-input v-model="formData.preview_link" placeholder="预览链接（可选）" />
        </el-form-item>

        <el-form-item label="上游Tracklink" prop="advertiser_tracklink">
          <el-input
            v-model="formData.advertiser_tracklink"
            type="textarea"
            :rows="2"
            placeholder="上游的Tracklink（不显示给下游，建立单子时配置我们的参数）"
          />
          <div class="form-hint" style="margin-top: 4px; color: var(--el-text-color-secondary); font-size: 12px;">
            占位符支持 {click_id}、{{click_id}}、{clickId}、{channel_id}、{sub_affid} 等；无法解析的占位符将无法保存
          </div>
        </el-form-item>

        <el-form-item label="下游Tracklink" prop="downstream_tracklink">
          <div v-if="isEdit && formData.downstream_tracklink" style="display: flex; align-items: flex-start; gap: 8px;">
            <el-input
              v-model="formData.downstream_tracklink"
              type="textarea"
              :rows="2"
              placeholder="生成给下游的Tracklink（自动生成）"
              readonly
              style="flex: 1;"
            />
            <!-- 管理员登录且短链接不存在时显示生成按钮 -->
            <el-button
              v-if="isAdmin && !shortLinkExists"
              type="primary"
              :loading="generatingShortLink"
              @click="generateShortLinkForOffer"
            >
              生成短链接
            </el-button>
          </div>
          <div v-else-if="!isEdit" style="padding: 12px; background: #f5f7fa; border-radius: 4px;">
            <el-text type="info">
              下游Tracklink将在保存时自动生成，并自动创建短链接
            </el-text>
          </div>
          <!-- 短链接显示区域 -->
          <div v-if="formData.downstream_tracklink_short" style="margin-top: 8px;">
            <el-alert
              :title="`短链接: ${formData.downstream_tracklink_short}`"
              type="success"
              :closable="false"
              show-icon
            >
              <template #default>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-link
                    :href="formData.downstream_tracklink_short"
                    target="_blank"
                    type="primary"
                  >
                    {{ formData.downstream_tracklink_short }}
                  </el-link>
                  <el-button
                    text
                    type="primary"
                    :icon="DocumentCopy"
                    @click="copyToClipboard(formData.downstream_tracklink_short)"
                    title="复制短链接"
                  />
                </div>
              </template>
            </el-alert>
          </div>
          <!-- 管理员登录且短链接不存在时显示提示 -->
          <div v-if="isAdmin && isEdit && formData.downstream_tracklink && !shortLinkExists" class="form-hint">
            您可以生成短链接，短链接将在保存时创建。
          </div>
        </el-form-item>

        <el-divider content-position="left">
          <el-icon :size="16" style="vertical-align: middle; margin-right: 4px;"><User /></el-icon>
          <span style="font-weight: 600; font-size: 15px;">渠道配置</span>
        </el-divider>
        
        <el-form-item label="分配渠道" prop="publisher_configs" style="margin-top: 8px;">
          <div style="width: 100%;">
            <div 
              v-for="(config, index) in formData.publisher_configs" 
              :key="index" 
              class="publisher-config-card"
            >
              <div class="publisher-config-header">
                <div class="publisher-config-title">
                  <el-icon :size="18" style="margin-right: 6px; color: #409eff;"><User /></el-icon>
                  <span class="publisher-config-label">渠道配置 {{ index + 1 }}</span>
                  <el-tag 
                    v-if="config.publisher_id" 
                    type="success" 
                    size="small" 
                    style="margin-left: 8px;"
                  >
                    {{ getPublisherName(config.publisher_id) }}
                  </el-tag>
                  <el-tag 
                    v-else 
                    type="info" 
                    size="small" 
                    style="margin-left: 8px;"
                  >
                    未选择渠道
                  </el-tag>
                </div>
                <el-button
                  type="danger"
                  :icon="Delete"
                  circle
                  size="small"
                  @click="removePublisherConfig(index)"
                  :disabled="formData.publisher_configs.length <= 1"
                  title="删除此渠道配置"
                />
              </div>
              
              <div class="publisher-config-content">
                <el-form-item 
                  label="选择渠道" 
                  :prop="`publisher_configs.${index}.publisher_id`"
                  :rules="[{ required: true, message: '请选择渠道', trigger: 'change' }]"
                  style="margin-bottom: 16px;"
                >
                  <el-select
                    v-model="config.publisher_id"
                    placeholder="请选择渠道"
                    filterable
                    popper-class="select-dropdown"
                    :teleported="true"
                    style="width: 100%;"
                  >
                    <el-option
                      v-for="pub in publisherList"
                      :key="pub.id"
                      :label="pub.publisher_name"
                      :value="pub.id"
                      :disabled="isPublisherSelected(pub.id, index)"
                    />
                  </el-select>
                </el-form-item>
                
                <el-row :gutter="16" v-if="config.publisher_id">
                  <el-col :span="12">
                    <el-form-item 
                      label="下游PO" 
                      :prop="`publisher_configs.${index}.affiliate_payout`"
                    >
                      <el-input-number
                        v-model="config.affiliate_payout"
                        :min="0"
                        :precision="2"
                        placeholder="渠道的转化金额"
                        style="width: 100%;"
                      />
                      <div class="field-hint">
                        【下游PO】是渠道的转化金额（不是金额的扣减比例）。如果上游通知的金额大于这个金额，就按照【下游PO】的金额通知渠道
                      </div>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item 
                      label="下游Cap" 
                      :prop="`publisher_configs.${index}.downstream_cap`"
                    >
                      <el-input-number
                        v-model="config.downstream_cap"
                        :min="0"
                        placeholder="下游每天转化个数限制"
                        style="width: 100%;"
                      />
                      <div class="field-hint">
                        【下游Cap】里面的值是下游每天转化个数的限制。如果渠道转化超过了这个值就不通知渠道了。客户登录查看时，也只显示真实的（真实不超过【下游Cap】的）转化
                      </div>
                    </el-form-item>
                  </el-col>
                </el-row>
                <div v-else class="publisher-config-placeholder">
                  <el-empty 
                    description="请先选择渠道，然后配置该渠道的下游PO和下游Cap" 
                    :image-size="80"
                  />
                </div>
              </div>
            </div>
            
            <el-button
              type="primary"
              :icon="Plus"
              @click="addPublisherConfig"
              style="width: 100%; margin-top: 12px;"
              plain
            >
              添加渠道配置
            </el-button>
            
            <div class="form-hint" style="margin-top: 12px;">
              <el-icon :size="14" style="vertical-align: middle; margin-right: 4px;"><InfoFilled /></el-icon>
              每个渠道可以配置独立的下游PO和下游Cap。至少需要添加一个渠道配置。
            </div>
          </div>
        </el-form-item>

        <el-form-item label="点击有效期(小时)" prop="click_validity_hours">
          <el-input-number
            v-model="formData.click_validity_hours"
            :min="1"
            :max="8760"
            placeholder="默认720小时(30天)"
            style="width: 100%;"
          />
          <div class="form-hint">点击有效期，超过此时间的点击将无法关联转化。默认720小时（30天）</div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="状态" prop="status">
              <el-select v-model="formData.status" popper-class="select-dropdown" :teleported="true" style="width: 100%;">
                <el-option label="Active" value="Active" />
                <el-option label="Inactive" value="Inactive" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="激活" prop="is_active">
              <el-switch v-model="formData.is_active" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="Offer详情 - 相关联数据项"
      width="1200px"
      @close="handleDetailDialogClose"
    >
      <div v-loading="detailLoading">
        <el-tabs v-model="activeTab" type="border-card">
          <!-- 基本信息 -->
          <el-tab-pane label="基本信息" name="basic">
            <el-descriptions :column="2" border>
              <el-descriptions-item label="Offer ID">{{ currentOffer?.id }}</el-descriptions-item>
              <el-descriptions-item label="Offer名称">{{ currentOffer?.offer_name }}</el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="广告主">{{ currentOffer?.advertiser_name }}</el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="上游Offer ID">{{ currentOffer?.advertiser_offer_id || '-' }}</el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="上游PO">
                <span v-if="currentOffer?.payout">{{ currentOffer.payout.toFixed(2) }}</span>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item :label="isAdmin ? '下游PO' : 'PO'">
                <template v-if="!isAdmin && currentClientId && currentOffer?.assigned_publishers">
                  <!-- 客户登录：显示分配给该客户渠道的PO -->
                  <span v-if="getClientPublisherPO()">{{ getClientPublisherPO().toFixed(2) }}</span>
                  <span v-else>-</span>
                </template>
                <template v-else>
                  <!-- 管理员：显示Offer级别的PO -->
                  <span v-if="currentOffer?.affiliate_payout">{{ currentOffer.affiliate_payout.toFixed(2) }}</span>
                  <span v-else>-</span>
                </template>
              </el-descriptions-item>
              <el-descriptions-item label="国家">{{ currentOffer?.country || '-' }}</el-descriptions-item>
              <el-descriptions-item label="分类">{{ currentOffer?.category || '-' }}</el-descriptions-item>
              <el-descriptions-item label="类型">{{ currentOffer?.type || '-' }}</el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag :type="currentOffer?.status === 'Active' ? 'success' : 'info'">
                  {{ currentOffer?.status }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="激活状态">
                <el-tag :type="currentOffer?.is_active ? 'success' : 'danger'">
                  {{ currentOffer?.is_active ? '是' : '否' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="上游Cap">{{ currentOffer?.upstream_cap || '-' }}</el-descriptions-item>
              <el-descriptions-item :label="isAdmin ? '下游Cap' : 'Cap'">
                <template v-if="!isAdmin && currentClientId && currentOffer?.assigned_publishers">
                  <!-- 客户登录：显示分配给该客户渠道的Cap -->
                  <span v-if="getClientPublisherCap() !== null && getClientPublisherCap() !== undefined">
                    {{ getClientPublisherCap() }}
                  </span>
                  <span v-else>-</span>
                </template>
                <template v-else>
                  <!-- 管理员：显示Offer级别的Cap -->
                  <span>{{ currentOffer?.downstream_cap || '-' }}</span>
                </template>
              </el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="点击有效期(小时)">{{ currentOffer?.click_validity_hours || 720 }}</el-descriptions-item>
              <el-descriptions-item label="预览链接" :span="2">
                <el-link v-if="currentOffer?.preview_link" :href="currentOffer.preview_link" target="_blank" type="primary">
                  {{ currentOffer.preview_link }}
                </el-link>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="上游Tracklink" :span="2">
                <span v-if="currentOffer?.advertiser_tracklink" style="word-break: break-all;">
                  {{ currentOffer.advertiser_tracklink }}
                </span>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item :label="isAdmin ? '下游Tracklink' : 'Tracklink'" :span="2">
                <template v-if="!isAdmin && currentClientId">
                  <!-- 客户登录：显示该客户渠道的Tracklink（短链接+参数） -->
                  <template v-if="clientPublisherTracklink">
                    <el-link 
                      :href="clientPublisherTracklink" 
                      target="_blank" 
                      type="primary"
                      style="word-break: break-all;"
                    >
                      {{ clientPublisherTracklink }}
                    </el-link>
                    <el-button
                      text
                      type="primary"
                      :icon="DocumentCopy"
                      style="margin-left: 8px;"
                      @click="copyToClipboard(clientPublisherTracklink)"
                      title="复制Tracklink"
                    />
                  </template>
                  <span v-else-if="loadingClientTracklink" style="color: #909399;">加载中...</span>
                  <span v-else style="color: #909399;">该Offer未分配给您的渠道或未找到短链接</span>
                </template>
                <template v-else>
                  <!-- 管理员：显示原始模板Tracklink -->
                  <span v-if="currentOffer?.downstream_tracklink" style="word-break: break-all;">
                    {{ currentOffer.downstream_tracklink }}
                  </span>
                  <span v-else>-</span>
                </template>
              </el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDate(currentOffer?.created_at) }}</el-descriptions-item>
              <el-descriptions-item label="更新时间">{{ formatDate(currentOffer?.updated_at) }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>

          <el-tab-pane label="数据统计" name="stats">
            <OfferStatsPanel
              v-if="currentOffer?.id"
              :offer-id="currentOffer.id"
            />
          </el-tab-pane>

          <!-- 渠道分配（仅管理员可见） -->
          <el-tab-pane v-if="isAdmin" label="渠道分配" name="publishers">
            <div v-if="currentOffer?.assigned_publishers && currentOffer.assigned_publishers.length > 0">
              <el-table :data="currentOffer.assigned_publishers" stripe style="width: 100%">
                <el-table-column prop="id" label="渠道ID" width="100" align="center" />
                <el-table-column prop="publisher_name" label="渠道名称" />
                <el-table-column label="Tracklink" min-width="400" show-overflow-tooltip>
                  <template #default="scope">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <el-link
                        v-if="getPublisherShortLink(scope.row.id)"
                        :href="getPublisherShortLink(scope.row.id)"
                        target="_blank"
                        type="primary"
                        style="flex: 1; word-break: break-all;"
                      >
                        {{ getPublisherShortLink(scope.row.id) }}
                      </el-link>
                      <span v-else-if="creatingShortLinks[scope.row.id]" style="color: #909399;">
                        <el-icon class="is-loading"><Loading /></el-icon>
                        生成中...
                      </span>
                      <span v-else style="color: #909399;">-</span>
                      <el-button
                        v-if="getPublisherShortLink(scope.row.id)"
                        text
                        type="primary"
                        :icon="DocumentCopy"
                        @click="copyToClipboard(getPublisherShortLink(scope.row.id))"
                        title="复制Tracklink"
                      />
                      <el-button
                        v-else-if="!creatingShortLinks[scope.row.id] && getPublisherTracklink(scope.row.id)"
                        text
                        type="primary"
                        :icon="Plus"
                        @click="createPublisherShortLink(scope.row.id)"
                        title="生成短链接"
                      />
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <el-empty v-else description="暂无分配的渠道" />
          </el-tab-pane>

          <!-- Cap配置 -->
          <el-tab-pane label="Cap配置" name="caps">
            <el-table :data="relatedCaps" stripe style="width: 100%" v-loading="capsLoading">
              <el-table-column prop="id" label="ID" width="80" align="center" />
              <el-table-column prop="cap_type" label="Cap类型" width="150">
                <template #default="scope">
                  <el-tag :type="scope.row.cap_type === 'advertiser_offer' ? 'warning' : 'primary'" size="small">
                    {{ scope.row.cap_type }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="publisher_name" label="渠道" width="150">
                <template #default="scope">
                  {{ scope.row.publisher_name || '全部渠道' }}
                </template>
              </el-table-column>
              <el-table-column prop="daily_cap" label="每日Cap" width="100" align="center">
                <template #default="scope">
                  {{ scope.row.daily_cap || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="total_cap" label="总Cap" width="100" align="center">
                <template #default="scope">
                  {{ scope.row.total_cap || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="current_daily_count" label="当前每日计数" width="120" align="center" />
              <el-table-column prop="current_total_count" label="当前总计数" width="120" align="center" />
              <el-table-column prop="is_active" label="激活" width="80" align="center">
                <template #default="scope">
                  <el-tag :type="scope.row.is_active ? 'success' : 'danger'" size="small">
                    {{ scope.row.is_active ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="180">
                <template #default="scope">
                  {{ formatDate(scope.row.created_at) }}
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!capsLoading && relatedCaps.length === 0" description="暂无Cap配置" />
          </el-tab-pane>

          <!-- 扣量配置（仅管理员可见） -->
          <el-tab-pane v-if="isAdmin" label="扣量配置" name="discounts">
            <el-table :data="relatedDiscounts" stripe style="width: 100%" v-loading="discountsLoading">
              <el-table-column prop="id" label="ID" width="80" align="center" />
              <el-table-column prop="discount_type" label="扣量类型" width="120">
                <template #default="scope">
                  <el-tag :type="scope.row.discount_type === 'offer' ? 'primary' : 'warning'" size="small">
                    {{ scope.row.discount_type }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="publisher_name" label="渠道" width="200" />
              <el-table-column prop="discount_ratio" label="扣量比例(%)" width="120" align="center">
                <template #default="scope">
                  {{ scope.row.discount_ratio.toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column prop="is_active" label="激活" width="80" align="center">
                <template #default="scope">
                  <el-tag :type="scope.row.is_active ? 'success' : 'danger'" size="small">
                    {{ scope.row.is_active ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="180">
                <template #default="scope">
                  {{ formatDate(scope.row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column prop="updated_at" label="更新时间" width="180">
                <template #default="scope">
                  {{ formatDate(scope.row.updated_at) }}
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!discountsLoading && relatedDiscounts.length === 0" description="暂无扣量配置" />
          </el-tab-pane>

        </el-tabs>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 列设置对话框 -->
    <el-dialog
      v-model="columnSettingVisible"
      title="列显示设置"
      width="500px"
      @close="saveColumnVisibility"
    >
      <el-checkbox-group v-model="columnVisibilityArray">
        <el-checkbox label="id" :disabled="true">Offer ID（固定显示）</el-checkbox>
        <el-checkbox label="offer_name" :disabled="true">Offer名称（固定显示）</el-checkbox>
        <el-checkbox v-if="isAdmin" label="advertiser_name">广告主</el-checkbox>
        <el-checkbox v-if="isAdmin" label="advertiser_offer_id">上游Offer ID</el-checkbox>
        <el-checkbox v-if="isAdmin" label="payout">上游PO</el-checkbox>
        <el-checkbox label="affiliate_payout">{{ isAdmin ? '下游PO' : 'PO' }}</el-checkbox>
        <el-checkbox label="country">国家</el-checkbox>
        <el-checkbox label="category">分类</el-checkbox>
        <el-checkbox label="type">类型</el-checkbox>
        <el-checkbox v-if="isAdmin" label="upstream_cap">上游Cap</el-checkbox>
        <el-checkbox label="downstream_cap">{{ isAdmin ? '下游Cap' : 'Cap' }}</el-checkbox>
        <el-checkbox label="preview_link">预览链接</el-checkbox>
        <el-checkbox label="downstream_tracklink">{{ isAdmin ? '下游Tracklink' : 'Tracklink' }}</el-checkbox>
        <el-checkbox v-if="isAdmin" label="click_validity_hours">点击有效期(小时)</el-checkbox>
        <el-checkbox v-if="isAdmin" label="assigned_publishers">分配渠道</el-checkbox>
        <el-checkbox label="status">状态</el-checkbox>
        <el-checkbox v-if="isAdmin" label="is_active">激活</el-checkbox>
        <el-checkbox label="created_at">创建时间</el-checkbox>
        <el-checkbox label="updated_at">更新时间</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="columnSettingVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColumnVisibility">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { ElMessage, ElDialog, ElCheckboxGroup, ElCheckbox } from 'element-plus'
import { Plus, Search, Refresh, Edit, Delete, Box, View, DocumentCopy, Loading, InfoFilled, User, Setting } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { getOffers, getOffer } from '@/api/offer'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'
import { copyToClipboard } from '@/utils/clipboard'
import { useAuthStore } from '@/store'
import { useOfferColumnVisibility } from '@/composables/useOfferColumnVisibility'
import { useOfferList } from '@/composables/useOfferList'
import { useOfferForm } from '@/composables/useOfferForm'
import { useOfferDetail } from '@/composables/useOfferDetail'
import OfferStatsPanel from '@/components/admin/OfferStatsPanel.vue'
import OfferSearchBar from '@/components/admin/OfferSearchBar.vue'

const authStore = useAuthStore()
const route = useRoute()
const isAdmin = computed(() => authStore.isAdmin)
// 获取客户ID，支持多种方式
const currentClientId = computed(() => {
  // 方式1: 从 userInfo.client.id 获取
  if (authStore.userInfo?.client?.id) {
    return authStore.userInfo.client.id
  }
  // 方式2: 从 userInfo.client_id 获取（如果存在）
  if (authStore.userInfo?.client_id) {
    return authStore.userInfo.client_id
  }
  return null
})

const {
  loading,
  searchKeyword,
  filterAdvertiser,
  filterStatus,
  filterActive,
  filterPublisher,
  pagination,
  tableData,
  advertiserList,
  publisherList,
  loadAdvertisers,
  loadPublishers,
  loadData,
  handleSearch,
  handleReset,
  handleAdvertiserChange,
  handleStatusChange,
  handleActiveChange,
  handlePublisherChange,
} = useOfferList()

const {
  columnSettingVisible,
  columnVisibility,
  columnVisibilityArray,
  loadColumnVisibility,
  saveColumnVisibility,
} = useOfferColumnVisibility(isAdmin)

const {
  submitting,
  dialogVisible,
  isEdit,
  formRef,
  formData,
  formRules,
  generatingShortLink,
  shortLinkExists,
  addPublisherConfig,
  removePublisherConfig,
  isPublisherSelected,
  getPublisherName,
  handleAdd,
  handleEdit,
  handleDelete,
  handleToggleActive,
  handleToggleStatus,
  handleSubmit,
  handleDialogClose,
  generateShortLinkForOffer,
} = useOfferForm({ isAdmin, loadData, publisherList })

const {
  detailDialogVisible,
  detailLoading,
  activeTab,
  currentOffer,
  relatedCaps,
  relatedDiscounts,
  capsLoading,
  discountsLoading,
  publisherShortLinks,
  creatingShortLinks,
  clientPublisherTracklink,
  loadingClientTracklink,
  handleViewDetails,
  handleDetailDialogClose,
  getPublisherTracklink,
  getPublisherShortLink,
  createPublisherShortLink,
  getClientPublisherPO,
  getClientPublisherCap,
  getRowClientPublisherPO,
  getRowClientPublisherCap,
  getRowClientPublisherTracklink,
} = useOfferDetail({ authStore, isAdmin, currentClientId })

// 分页
const handleSizeChange = (size) => {
  pagination.pageSize = size;
  pagination.page = 1;  // 分页大小变化时重置到第一页
  loadData()
}

const handlePageChange = (page) => {
  pagination.page = page;
  loadData()
}

onMounted(async () => {
  // 加载列显示设置
  loadColumnVisibility()
  loadAdvertisers()
  loadPublishers()
  
  // 检查路由查询参数
  const offerId = route.query.offer_id
  const offerName = route.query.offer_name
  
  if (offerId) {
    // 如果有offer_id，直接打开详情对话框
    try {
      // 先加载数据列表
      await loadData()
      // 在表格数据中查找对应的offer
      let offer = tableData.value.find(item => item.id === Number(offerId))
      if (!offer) {
        // 如果第一页没找到，尝试搜索
        searchKeyword.value = String(offerId)
        await handleSearch()
        await nextTick()
        offer = tableData.value.find(item => item.id === Number(offerId))
      }
      
      if (offer) {
        // 找到对应的offer，打开详情对话框
        await handleViewDetails(offer)
      } else {
        // 如果还是没找到，尝试直接通过ID获取（可能不在当前筛选条件下）
        try {
          const offerData = await getOffer(Number(offerId))
          if (offerData) {
            // 创建一个临时对象用于显示详情
            const tempOffer = { id: Number(offerId), ...offerData }
            await handleViewDetails(tempOffer)
          } else {
            ElMessage.warning('未找到对应的Offer')
            loadData()
          }
        } catch (error) {
          logger.error('通过ID获取Offer失败:', error)
          ElMessage.warning('未找到对应的Offer')
          loadData()
        }
      }
    } catch (error) {
      logger.error('打开Offer详情失败:', error)
      ElMessage.error('打开详情失败')
      loadData()
    }
  } else if (offerName) {
    // 如果有offer_name，自动搜索
    searchKeyword.value = String(offerName)
    // 执行搜索
    nextTick(() => {
      handleSearch()
    })
  } else {
    loadData()
  }
})
</script>

<style scoped>
.offer-management {
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

.header-right {
  display: flex;
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

.search-bar {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 10px;
}

/* 确保输入框和下拉框文字不被遮盖 */
.search-bar :deep(.el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮留出空间 */
}

.search-bar :deep(.el-select .el-input__wrapper) {
  padding-right: 30px; /* 为清除按钮和下拉箭头留出空间 */
}

.search-bar :deep(.el-input__inner),
.search-bar :deep(.el-select__input) {
  padding-right: 8px; /* 文字与清除按钮之间的间距 */
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}

/* 确保清除按钮不遮挡文字 */
.search-bar :deep(.el-input__suffix) {
  right: 8px;
}

.search-bar :deep(.el-select .el-input__suffix) {
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.table-wrapper {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  position: relative;
}

.table-wrapper :deep(.el-table) {
  min-width: 2000px;
  width: 100%;
}

/* 确保固定列在滚动时正确显示 */
.table-wrapper :deep(.el-table__fixed-left) {
  left: 0 !important;
  z-index: 4 !important;
}

.table-wrapper :deep(.el-table__fixed-right) {
  right: 0 !important;
  z-index: 4 !important;
}

/* 解决固定列与内容列重叠的问题 */
.table-wrapper :deep(.el-table__fixed) {
  height: auto !important;
  bottom: 0 !important;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

/* 渠道配置卡片样式 */
.publisher-config-card {
  margin-bottom: 16px;
  padding: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
  position: relative;
  overflow: visible;
}

.publisher-config-card:hover {
  border-color: #409eff;
  box-shadow: 0 4px 8px rgba(64, 158, 255, 0.1);
}

.publisher-config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f2f5;
}

.publisher-config-title {
  display: flex;
  align-items: center;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.publisher-config-label {
  margin-right: 8px;
}

.publisher-config-content {
  padding-top: 8px;
}

.field-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

.publisher-config-placeholder {
  padding: 20px 0;
  text-align: center;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .offer-management {
    padding: 10px;
  }

  .search-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .search-bar > * {
    width: 100% !important;
    margin-left: 0 !important;
  }

  .table-wrapper :deep(.el-table) {
    min-width: 1100px;
    font-size: 12px;
  }

  .table-wrapper :deep(.el-table__cell) {
    padding: 8px 4px;
  }
}

/* 全局下拉选择框样式 */
.select-dropdown {
  z-index: 3000 !important;
}

:deep(.el-select__popper.select-dropdown) {
  z-index: 3000 !important;
  position: fixed !important;
}
</style>

