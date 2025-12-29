<template>
  <div class="offer-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Box /></el-icon>
            <span class="header-title">Offer管理</span>
          </div>
          <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="handleAdd">添加Offer</el-button>
        </div>
      </template>

      <!-- 搜索栏 -->
      <div class="search-bar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索Offer名称或ID"
          clearable
          style="width: 300px;"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="filterAdvertiser"
          placeholder="请选择广告主"
          clearable
          filterable
          style="width: 180px; margin-left: 10px; min-width: 180px;"
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
          v-model="filterStatus"
          placeholder="请选择状态"
          clearable
          style="width: 140px; margin-left: 10px; min-width: 140px;"
          @change="handleStatusChange"
        >
          <el-option label="全部" :value="null" />
          <el-option label="Active" value="Active" />
          <el-option label="Inactive" value="Inactive" />
        </el-select>
        <el-select
          v-model="filterActive"
          placeholder="请选择激活状态"
          clearable
          style="width: 160px; margin-left: 10px; min-width: 160px;"
          @change="handleActiveChange"
        >
          <el-option label="全部" :value="null" />
          <el-option label="激活" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="handleSearch" style="margin-left: 10px;">搜索</el-button>
        <el-button :icon="Refresh" @click="handleReset">重置</el-button>
      </div>

      <!-- 表格 -->
      <div class="table-wrapper">
        <el-table
          v-loading="loading"
          :data="tableData"
          stripe
          style="width: 100%; margin-top: 20px;"
        >
        <el-table-column prop="id" label="Offer ID" width="100" align="center" />
        <el-table-column prop="offer_name" label="Offer名称" width="180" show-overflow-tooltip />
        <el-table-column v-if="isAdmin" prop="advertiser_name" label="广告主" width="150" />
        <el-table-column v-if="isAdmin" prop="advertiser_offer_id" label="上游Offer ID" width="150" />
        <el-table-column v-if="isAdmin" prop="payout" label="上游PO" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.payout">{{ scope.row.payout.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="affiliate_payout" :label="isAdmin ? '下游PO' : 'PO'" width="100" align="right">
          <template #default="scope">
            <span v-if="scope.row.affiliate_payout">{{ scope.row.affiliate_payout.toFixed(2) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="country" label="国家" width="100" />
        <el-table-column v-if="isAdmin" prop="category" label="分类" width="120" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.category">{{ scope.row.category }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="type" label="类型" width="100" show-overflow-tooltip>
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
        <el-table-column v-if="isAdmin" prop="downstream_cap" label="下游Cap" width="100" align="center">
          <template #default="scope">
            <span v-if="scope.row.downstream_cap">{{ scope.row.downstream_cap }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="preview_link" label="预览链接" width="200" show-overflow-tooltip>
          <template #default="scope">
            <el-link v-if="scope.row.preview_link" :href="scope.row.preview_link" target="_blank" type="primary" :underline="false">
              预览
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="postback_method" label="Postback方法" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.postback_method === 'POST' ? 'success' : 'info'" size="small">
              {{ scope.row.postback_method || 'GET' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="click_validity_hours" label="点击有效期(小时)" width="140" align="center">
          <template #default="scope">
            <span v-if="scope.row.click_validity_hours">{{ scope.row.click_validity_hours }}</span>
            <span v-else>720</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="assigned_publishers" label="分配渠道" width="200" show-overflow-tooltip>
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
        <el-table-column v-if="isAdmin" prop="status" label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'Active' ? 'success' : 'info'">
              {{ scope.row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="is_active" label="激活" width="80" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
              {{ scope.row.is_active ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="isAdmin" prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
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
            <el-button
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
          <div v-if="isEdit && formData.downstream_tracklink" class="form-hint">
            您可以生成短链接，短链接将在保存时创建。
          </div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Postback URL" prop="postback_url">
              <el-input v-model="formData.postback_url" placeholder="Postback URL（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Postback方法" prop="postback_method">
              <el-select v-model="formData.postback_method" style="width: 100%;">
                <el-option label="GET" value="GET" />
                <el-option label="POST" value="POST" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

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
                        placeholder="扣价后给渠道的金额"
                        style="width: 100%;"
                      />
                      <div class="field-hint">
                        该渠道的扣价后支付金额
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
                        placeholder="下游转化上限"
                        style="width: 100%;"
                      />
                      <div class="field-hint">
                        该渠道的转化上限
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
                <span v-if="currentOffer?.affiliate_payout">{{ currentOffer.affiliate_payout.toFixed(2) }}</span>
                <span v-else>-</span>
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
              <el-descriptions-item :label="isAdmin ? '下游Cap' : 'Cap'">{{ currentOffer?.downstream_cap || '-' }}</el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="点击有效期(小时)">{{ currentOffer?.click_validity_hours || 720 }}</el-descriptions-item>
              <el-descriptions-item v-if="isAdmin" label="Postback方法">
                <el-tag :type="currentOffer?.postback_method === 'POST' ? 'success' : 'info'" size="small">
                  {{ currentOffer?.postback_method || 'GET' }}
                </el-tag>
              </el-descriptions-item>
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
              <el-descriptions-item v-if="isAdmin" label="Postback URL" :span="2">
                <span v-if="currentOffer?.postback_url" style="word-break: break-all;">
                  {{ currentOffer.postback_url }}
                </span>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDate(currentOffer?.created_at) }}</el-descriptions-item>
              <el-descriptions-item label="更新时间">{{ formatDate(currentOffer?.updated_at) }}</el-descriptions-item>
            </el-descriptions>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh, Edit, Delete, Box, View, DocumentCopy, Loading, InfoFilled, User } from '@element-plus/icons-vue'
import { getOffers, createOffer, updateOffer, deleteOffer, getOffer } from '@/api/offer'
import { getAdvertisers } from '@/api/advertiser'
import { getPublishers } from '@/api/publisher'
import { getCaps } from '@/api/cap'
import { getDiscounts } from '@/api/discount'
import { createShortLink, getShortLinks } from '@/api/shortLink'
import { logger } from '@/utils/logger'
import { formatDate } from '@/utils/date'
import { useAuthStore } from '@/store'
import { computed } from 'vue'

const authStore = useAuthStore()
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

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const searchKeyword = ref('')
const filterAdvertiser = ref(null)
const filterStatus = ref(null)
const filterActive = ref(null)
const formRef = ref(null)

// 详情对话框相关
const detailDialogVisible = ref(false)
const detailLoading = ref(false)
const activeTab = ref('basic')
const currentOffer = ref(null)
const relatedCaps = ref([])
const relatedDiscounts = ref([])
const capsLoading = ref(false)
const discountsLoading = ref(false)
const publisherShortLinks = ref({}) // 存储渠道ID对应的短链接
const creatingShortLinks = ref({}) // 正在创建短链接的渠道ID
const clientPublisherTracklink = ref(null) // 客户渠道的Tracklink（短链接+参数）
const loadingClientTracklink = ref(false) // 是否正在加载客户Tracklink

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])
const advertiserList = ref([])
const publisherList = ref([])

const formData = reactive({
  offer_name: '',
  advertiser_id: null,
  advertiser_offer_id: '',
  preview_link: '',
  payout: null,
  affiliate_payout: null,
  country: '',
  category: '',
  type: '',
  status: 'Active',
  upstream_cap: null,
  downstream_cap: null,
  advertiser_tracklink: '',
  downstream_tracklink: '',
  downstream_tracklink_short: '',
  postback_url: '',
  postback_method: 'GET',
  click_validity_hours: 720,
  publisher_configs: [{ publisher_id: null, affiliate_payout: null, downstream_cap: null }],
  is_active: true
})

const formRules = {
  offer_name: [
    { required: true, message: '请输入Offer名称', trigger: 'blur' }
  ],
  advertiser_id: [
    { required: true, message: '请选择广告主', trigger: 'change' }
  ]
}

// 加载广告主列表
const loadAdvertisers = async () => {
  try {
    const response = await getAdvertisers({ page: 1, page_size: 100 })
    if (response.code === 200) {
      advertiserList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载广告主列表失败:', error)
  }
}

// 加载渠道列表
const loadPublishers = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 })
    if (response.code === 200) {
      publisherList.value = response.data || []
    }
  } catch (error) {
    logger.error('加载渠道列表失败:', error)
  }
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: Math.min(pagination.pageSize, 100),
      search: searchKeyword.value || undefined,
      advertiser_id: filterAdvertiser.value || undefined,
      status: filterStatus.value || undefined,
      is_active: filterActive.value !== null ? filterActive.value : undefined
    }
    const response = await getOffers(params)
    if (response.code === 200) {
      tableData.value = response.data || []
      pagination.total = response.total || 0
    } else {
      ElMessage.error(response.message || '获取数据失败')
    }
  } catch (error) {
    logger.error('获取Offer列表失败:', error)
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

// 广告主选择变化
const handleAdvertiserChange = () => {
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
  handleSearch();
}

// 状态选择变化
const handleStatusChange = () => {
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
  handleSearch();
}

// 激活状态选择变化
const handleActiveChange = () => {
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
  handleSearch();
}

// 搜索
const handleSearch = () => {
  pagination.page = 1
  loadData()
}

// 重置
const handleReset = () => {
  searchKeyword.value = ''
  filterAdvertiser.value = null
  filterStatus.value = null
  filterActive.value = null
  pagination.page = 1
  loadData()
  
  // 修复选中值显示
  nextTick(() => {
    setTimeout(() => {
      if (typeof window.fixSelectDisplay === 'function') {
        window.fixSelectDisplay();
      }
    }, 100);
  });
}

// 添加渠道配置
const addPublisherConfig = () => {
  formData.publisher_configs.push({
    publisher_id: null,
    affiliate_payout: null,
    downstream_cap: null
  })
}

// 删除渠道配置
const removePublisherConfig = (index) => {
  formData.publisher_configs.splice(index, 1)
}

// 检查渠道是否已被选择
const isPublisherSelected = (publisherId, currentIndex) => {
  if (!publisherId) return false
  return formData.publisher_configs.some((config, index) => 
    index !== currentIndex && config.publisher_id === publisherId
  )
}

// 获取渠道名称
const getPublisherName = (publisherId) => {
  if (!publisherId) return ''
  const publisher = publisherList.value.find(p => p.id === publisherId)
  return publisher ? publisher.publisher_name : ''
}

// 修复函数：确保选中值后 placeholder 隐藏，选中值显示


// 添加
const handleAdd = () => {
  isEdit.value = false
  Object.assign(formData, {
    offer_name: '',
    advertiser_id: null,
    advertiser_offer_id: '',
    preview_link: '',
    payout: null,
    affiliate_payout: null,
    country: '',
    category: '',
    type: '',
    status: 'Active',
    upstream_cap: null,
    downstream_cap: null,
    advertiser_tracklink: '',
    downstream_tracklink: '',
    downstream_tracklink_short: '',
    postback_url: '',
    postback_method: 'GET',
    click_validity_hours: 720,
    publisher_configs: [{ publisher_id: null, affiliate_payout: null, downstream_cap: null }],
    is_active: true
  })
  dialogVisible.value = true
}

// 编辑
const handleEdit = async (row) => {
  isEdit.value = true
  
  // 获取完整的Offer详情（包含渠道配置信息）
  try {
    const response = await getOffer(row.id)
    if (response.code === 200 && response.data) {
      const offerData = response.data
      
      // 构建渠道配置
      let publisherConfigs = []
      if (offerData.assigned_publishers && offerData.assigned_publishers.length > 0) {
        publisherConfigs = offerData.assigned_publishers.map(p => ({
          publisher_id: p.id,
          affiliate_payout: p.affiliate_payout || null,
          downstream_cap: p.downstream_cap || null
        }))
      } else {
        publisherConfigs = [{ publisher_id: null, affiliate_payout: null, downstream_cap: null }]
      }
      
      Object.assign(formData, {
        id: offerData.id,
        offer_name: offerData.offer_name,
        advertiser_id: offerData.advertiser_id,
        advertiser_offer_id: offerData.advertiser_offer_id || '',
        preview_link: offerData.preview_link || '',
        payout: offerData.payout,
        affiliate_payout: offerData.affiliate_payout,
        country: offerData.country || '',
        category: offerData.category || '',
        type: offerData.type || '',
        status: offerData.status,
        upstream_cap: offerData.upstream_cap,
        downstream_cap: offerData.downstream_cap,
        advertiser_tracklink: offerData.advertiser_tracklink || '',
        downstream_tracklink: offerData.downstream_tracklink || '',
        downstream_tracklink_short: '',
        postback_url: offerData.postback_url || '',
        postback_method: offerData.postback_method || 'GET',
        click_validity_hours: offerData.click_validity_hours || 720,
        publisher_configs: publisherConfigs,
        is_active: offerData.is_active
      })
      
      // 检查是否已有短链接
      if (offerData.downstream_tracklink) {
        checkExistingShortLink(offerData.downstream_tracklink)
      }
    } else {
      // 如果获取详情失败，使用列表中的数据（向后兼容）
      Object.assign(formData, {
        id: row.id,
        offer_name: row.offer_name,
        advertiser_id: row.advertiser_id,
        advertiser_offer_id: row.advertiser_offer_id || '',
        preview_link: row.preview_link || '',
        payout: row.payout,
        affiliate_payout: row.affiliate_payout,
        country: row.country || '',
        category: row.category || '',
        type: row.type || '',
        status: row.status,
        upstream_cap: row.upstream_cap,
        downstream_cap: row.downstream_cap,
        advertiser_tracklink: row.advertiser_tracklink || '',
        downstream_tracklink: row.downstream_tracklink || '',
        downstream_tracklink_short: '',
        postback_url: row.postback_url || '',
        postback_method: row.postback_method || 'GET',
        click_validity_hours: row.click_validity_hours || 720,
        publisher_configs: row.assigned_publishers && row.assigned_publishers.length > 0
          ? row.assigned_publishers.map(p => ({
              publisher_id: p.id,
              affiliate_payout: p.affiliate_payout || null,
              downstream_cap: p.downstream_cap || null
            }))
          : [{ publisher_id: null, affiliate_payout: null, downstream_cap: null }],
        is_active: row.is_active
      })
      
      if (row.downstream_tracklink) {
        checkExistingShortLink(row.downstream_tracklink)
      }
    }
  } catch (error) {
    logger.error('获取Offer详情失败:', error)
    ElMessage.error('获取Offer详情失败')
    return
  }
  
  dialogVisible.value = true
}

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除Offer "${row.offer_name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await deleteOffer(row.id)
    if (response.code === 200) {
      ElMessage.success('删除成功')
      loadData()
    } else {
      ElMessage.error(response.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除Offer失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

// 提交
const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    // 验证渠道配置
    const validConfigs = formData.publisher_configs.filter(config => config.publisher_id !== null)
    if (validConfigs.length === 0) {
      ElMessage.warning('请至少添加一个渠道配置')
      return
    }
    
    // 验证是否有重复的渠道ID
    const publisherIds = validConfigs.map(config => config.publisher_id)
    const uniquePublisherIds = new Set(publisherIds)
    if (publisherIds.length !== uniquePublisherIds.size) {
      ElMessage.warning('渠道配置中存在重复的渠道，请检查')
      return
    }
    
    submitting.value = true
    try {
      // 构建提交数据
      const submitData = { ...formData }
      
      // 过滤掉publisher_id为null的配置
      submitData.publisher_configs = validConfigs
      
      // 移除publisher_ids（使用publisher_configs）
      delete submitData.publisher_ids
      
      let response
      let offerData = null
      
      if (isEdit.value) {
        // 编辑：先更新Offer
        response = await updateOffer(formData.id, submitData)
        if (response.code === 200) {
          offerData = response.data
        }
      } else {
        // 新建：先创建Offer获取id
        response = await createOffer(submitData)
        if (response.code === 200) {
          offerData = response.data
        }
      }
      
      if (response.code === 200 && offerData) {
        // 后端已自动创建短链接，使用后端返回的消息
        // downstream_tracklink 已经是短链接URL（如果创建成功）
        if (response.message) {
          // 显示后端返回的详细消息（包含短链接信息）
          ElMessage.success(response.message)
        } else {
          ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
        }
        
        // 更新表单中的downstream_tracklink（可能是短链接URL）
        if (offerData.downstream_tracklink) {
          formData.downstream_tracklink = offerData.downstream_tracklink
          formData.downstream_tracklink_short = offerData.downstream_tracklink
        }
        
        dialogVisible.value = false
        loadData()
      } else {
        ElMessage.error(response.message || '操作失败')
      }
    } catch (error) {
      logger.error('提交失败:', error)
      ElMessage.error('操作失败')
    } finally {
      submitting.value = false
    }
  })
}

// 对话框关闭
const handleDialogClose = () => {
  formRef.value?.resetFields()
  formData.downstream_tracklink_short = ''
}

// 生成短链接状态
const generatingShortLink = ref(false)

// 检查是否已有短链接（用于编辑时显示）
const checkExistingShortLink = async (tracklink) => {
  if (!tracklink) return
  
  // downstream_tracklink现在可能是短链接URL，直接使用
  // 如果是短链接格式（包含/s/），直接使用
  if (tracklink.includes('/s/')) {
    formData.downstream_tracklink_short = tracklink
    return
  }
  
  // 否则尝试查找对应的短链接
  try {
    const existingLinks = await getShortLinks({
      page: 1,
      page_size: 1,
      search: tracklink
    })
    
    if (existingLinks.data && existingLinks.data.length > 0) {
      const matchedLink = existingLinks.data.find(link => link.original_url === tracklink)
      if (matchedLink && matchedLink.short_url) {
        formData.downstream_tracklink_short = matchedLink.short_url
      }
    }
  } catch (error) {
    logger.error('查找短链接失败:', error)
  }
}

// 为Offer生成短链接（预览，不立即创建）
// 注意：后端已自动创建短链接，此函数主要用于检查现有短链接
const generateShortLinkForOffer = async () => {
  if (!formData.advertiser_tracklink) {
    ElMessage.warning('请先配置上游Tracklink')
    return
  }

  // 如果是新建，提示需要先保存
  if (!isEdit.value) {
    ElMessage.info('新建Offer需要先保存才能生成短链接（保存时会根据分配的渠道自动生成）')
    return
  }

  generatingShortLink.value = true
  try {
    // 使用advertiser_tracklink查找短链接
    const existingLinks = await getShortLinks({
      page: 1,
      page_size: 10,
      search: formData.advertiser_tracklink
    })
    
    if (existingLinks.data && existingLinks.data.length > 0) {
      // 查找该Offer的短链接（如果有多个渠道，使用第一个）
      const matchedLink = existingLinks.data.find(link => 
        link.original_url === formData.advertiser_tracklink &&
        link.offer_id === formData.id
      )
      if (matchedLink && matchedLink.short_url) {
        formData.downstream_tracklink_short = matchedLink.short_url
        ElMessage.success('已找到现有短链接')
        return
      }
    }
    
    ElMessage.info('保存Offer时会根据分配的渠道自动创建短链接')
  } catch (error) {
    logger.error('查找短链接失败:', error)
    ElMessage.error('操作失败')
  } finally {
    generatingShortLink.value = false
  }
}

// 查看详情
const handleViewDetails = async (row) => {
  detailDialogVisible.value = true
  activeTab.value = 'basic'
  detailLoading.value = true
  publisherShortLinks.value = {} // 清空短链接缓存
  creatingShortLinks.value = {} // 清空创建状态
  
  try {
    // 加载Offer详情
    const response = await getOffer(row.id)
    if (response.code === 200) {
      currentOffer.value = response.data
      
      // 主短链接已保存在downstream_tracklink中，不需要查找
      // 每个渠道的短链接通过getPublisherShortLink函数动态生成（主短链接 + 参数）
      
      // 如果是客户登录，加载客户渠道的Tracklink（短链接+参数）
      // 如果 currentClientId 为 null，尝试从 userInfo 中获取
      let clientId = currentClientId.value
      if (!clientId && !isAdmin.value && authStore.userInfo) {
        // 尝试从 userInfo.client.id 获取
        if (authStore.userInfo.client?.id) {
          clientId = authStore.userInfo.client.id
        }
        // 如果还是没有，尝试刷新用户信息
        else if (authStore.userInfo.role === 'client') {
          try {
            await authStore.fetchUserInfo()
            if (authStore.userInfo?.client?.id) {
              clientId = authStore.userInfo.client.id
            }
          } catch (error) {
            logger.error('刷新用户信息失败:', error)
          }
        }
      }
      
      if (!isAdmin.value && clientId) {
        loadingClientTracklink.value = true
        clientPublisherTracklink.value = null // 先清空
        try {
          const tracklink = await getClientPublisherTracklinkWithId(clientId)
          clientPublisherTracklink.value = tracklink
        } catch (error) {
          logger.error('获取客户Tracklink失败:', error)
        } finally {
          loadingClientTracklink.value = false
        }
      } else {
        // 如果不是客户登录，清空clientPublisherTracklink
        clientPublisherTracklink.value = null
      }
    } else {
      ElMessage.error(response.message || '获取详情失败')
      detailDialogVisible.value = false
      return
    }
    
    // 加载关联数据
    const loadPromises = [loadRelatedCaps(row.id)]
    // 仅管理员加载扣量配置
    if (isAdmin.value) {
      loadPromises.push(loadRelatedDiscounts(row.id))
    }
    await Promise.all(loadPromises)
  } catch (error) {
    logger.error('获取Offer详情失败:', error)
    ElMessage.error('获取详情失败')
    detailDialogVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// 加载关联的Cap配置
const loadRelatedCaps = async (offerId) => {
  capsLoading.value = true
  try {
    const response = await getCaps({
      page: 1,
      page_size: 100,
      offer_id: offerId
    })
    if (response.code === 200) {
      relatedCaps.value = response.data || []
    }
  } catch (error) {
    logger.error('加载Cap配置失败:', error)
  } finally {
    capsLoading.value = false
  }
}

// 加载关联的扣量配置
const loadRelatedDiscounts = async (offerId) => {
  discountsLoading.value = true
  try {
    const response = await getDiscounts({
      page: 1,
      page_size: 100,
      offer_id: offerId
    })
    if (response.code === 200) {
      relatedDiscounts.value = response.data || []
    }
  } catch (error) {
    logger.error('加载扣量配置失败:', error)
  } finally {
    discountsLoading.value = false
  }
}

// 详情对话框关闭
const handleDetailDialogClose = () => {
  currentOffer.value = null
  relatedCaps.value = []
  relatedDiscounts.value = []
  publisherShortLinks.value = {}
  creatingShortLinks.value = {}
  clientPublisherTracklink.value = null
  loadingClientTracklink.value = false
  activeTab.value = 'basic'
}

// 生成渠道的Tracklink（原始URL）
const getPublisherTracklink = (publisherId) => {
  if (!currentOffer.value?.downstream_tracklink || !publisherId) {
    return null
  }
  // downstream_tracklink格式：{base_url}/api/v1/track/click/{offer_id}?publisher_id={publisher_id}
  // 替换{publisher_id}为实际的publisher_id
  return currentOffer.value.downstream_tracklink.replace('{publisher_id}', publisherId)
}

// 获取渠道的短链接（主短链接 + 参数）
const getPublisherShortLink = (publisherId) => {
  // 如果downstream_tracklink是主短链接URL，则添加参数
  if (!currentOffer.value?.downstream_tracklink || !currentOffer.value.id || !publisherId) {
    logger.warn('getPublisherShortLink: 缺少必要参数')
    return null
  }
  
  let mainShortLink = currentOffer.value.downstream_tracklink.trim()
  
  // 检查是否是短链接格式（包含/s/）
  if (!mainShortLink.includes('/s/')) {
    logger.warn('getPublisherShortLink: downstream_tracklink不是短链接格式')
    return null
  }
  
  // 如果是相对路径（以/s/开头），需要添加域名
  if (mainShortLink.startsWith('/s/')) {
    const baseUrl = window.location.origin
    mainShortLink = `${baseUrl}${mainShortLink}`
  }
  
  // 移除可能已存在的参数，重新添加
  // 先分离URL和参数
  const urlParts = mainShortLink.split('?')
  const baseUrl = urlParts[0]
  
  // 添加参数：?offer_id=X&channel_id=Y
  const result = `${baseUrl}?offer_id=${currentOffer.value.id}&channel_id=${publisherId}`
  return result
}

// 获取客户自己的渠道Tracklink（用于客户登录时显示）
const getClientPublisherTracklink = async () => {
  return getClientPublisherTracklinkWithId(currentClientId.value)
}

// 获取客户自己的渠道Tracklink（带clientId参数版本）
const getClientPublisherTracklinkWithId = async (clientId) => {
  if (!currentOffer.value || !clientId) {
    logger.warn('getClientPublisherTracklinkWithId: 缺少currentOffer或clientId')
    return null
  }
  
  // 查找属于该客户的渠道
  const clientPublisher = currentOffer.value.assigned_publishers?.find(
    pub => pub.client_id === clientId
  )
  
  if (!clientPublisher) {
    logger.warn('getClientPublisherTracklink: 未找到客户关联的渠道')
    return null
  }
  
  // 优先使用短链接（如果downstream_tracklink是短链接格式）
  let shortLink = getPublisherShortLink(clientPublisher.id)
  
  if (shortLink) {
    return shortLink
  }
  
  // 如果getPublisherShortLink返回null，但downstream_tracklink是短链接格式，手动添加参数
  if (currentOffer.value.downstream_tracklink && currentOffer.value.downstream_tracklink.includes('/s/')) {
    let mainShortLink = currentOffer.value.downstream_tracklink.trim()
    
    // 如果是相对路径（以/s/开头），需要添加域名
    if (mainShortLink.startsWith('/s/')) {
      const baseUrl = window.location.origin
      mainShortLink = `${baseUrl}${mainShortLink}`
    }
    
    // 移除可能已存在的参数，重新添加
    const urlParts = mainShortLink.split('?')
    const baseUrl = urlParts[0]
    
    // 添加参数：?offer_id=X&channel_id=Y
    const result = `${baseUrl}?offer_id=${currentOffer.value.id}&channel_id=${clientPublisher.id}`
    return result
  }
  
  // 如果downstream_tracklink不是短链接格式，尝试通过offer_id查找主短链接
  try {
    // 通过offer_id查找该Offer的主短链接（channel_id为NULL）
    const existingLinks = await getShortLinks({
      page: 1,
      page_size: 100,
      offer_id: currentOffer.value.id
    })
    
    if (existingLinks.code === 200 && existingLinks.data && existingLinks.data.length > 0) {
      // 查找主短链接（channel_id为null或undefined）
      const mainShortLink = existingLinks.data.find(link => 
        link.offer_id === currentOffer.value.id && 
        (link.channel_id === null || link.channel_id === undefined)
      )
      
      if (mainShortLink && mainShortLink.short_code) {
        // 使用找到的主短链接，添加参数
        // 优先使用short_url（如果存在），否则构建URL
        let shortLinkUrl
        if (mainShortLink.short_url) {
          shortLinkUrl = mainShortLink.short_url
        } else {
          const baseUrl = window.location.origin
          shortLinkUrl = `${baseUrl}/s/${mainShortLink.short_code}`
        }
        
        // 移除可能已存在的参数，重新添加
        const urlParts = shortLinkUrl.split('?')
        const baseUrl = urlParts[0]
        
        // 添加参数：?offer_id=X&channel_id=Y
        const result = `${baseUrl}?offer_id=${currentOffer.value.id}&channel_id=${clientPublisher.id}`
        logger.info('getClientPublisherTracklink: 通过API查找短链接结果:', result)
        return result
      }
    }
  } catch (error) {
    logger.error('查找短链接失败:', error)
  }
  
  // 如果都没有，返回null（不显示原始Tracklink）
  logger.warn('getClientPublisherTracklink: 未找到短链接')
  return null
}

// 为渠道创建短链接（不再需要，因为使用主短链接 + 参数）
// 此函数保留用于兼容，但实际不需要创建，因为使用主短链接 + 参数
const createPublisherShortLink = async (publisherId) => {
  // 检查是否有主短链接
  if (!currentOffer.value?.downstream_tracklink) {
    ElMessage.warning('Offer还没有主短链接，请先保存Offer以生成主短链接')
    return
  }
  
  // 主短链接已存在，每个渠道使用主短链接 + 参数
  // 通过getPublisherShortLink函数动态生成
  const channelShortLink = getPublisherShortLink(publisherId)
  if (channelShortLink) {
    publisherShortLinks.value[publisherId] = channelShortLink
    ElMessage.success('渠道短链接已生成（主短链接 + 参数）')
  } else {
    ElMessage.warning('无法生成渠道短链接')
  }
}

// 复制到剪贴板
const copyToClipboard = async (text) => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    // 如果clipboard API失败，使用备用方法
    try {
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-999999px'
      textArea.style.top = '-999999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      const successful = document.execCommand('copy')
      document.body.removeChild(textArea)
      
      if (successful) {
        ElMessage.success('已复制到剪贴板')
      } else {
        ElMessage.error('复制失败')
      }
    } catch (fallbackError) {
      logger.error('复制失败:', fallbackError)
      ElMessage.error('复制失败')
    }
  }
}

// 分页
const handleSizeChange = () => {
  loadData()
}

const handlePageChange = () => {
  loadData()
}

onMounted(() => {
  loadAdvertisers()
  loadPublishers()
  loadData()
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
}

.table-wrapper :deep(.el-table) {
  min-width: 2000px;
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

