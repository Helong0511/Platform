<template>
  <div class="short-link-management">
    <!-- 统计卡片 -->
    <div class="stats-cards">
      <el-card class="stat-card">
        <el-statistic title="总链接数" :value="stats.total_links" />
      </el-card>
      <el-card class="stat-card">
        <el-statistic title="总点击次数" :value="stats.total_clicks" />
      </el-card>
      <el-card class="stat-card">
        <el-statistic title="活跃链接" :value="stats.active_links" />
      </el-card>
      <el-card class="stat-card">
        <el-statistic title="过期链接" :value="stats.expired_links" />
      </el-card>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar">
      <el-button type="primary" @click="handleCreate" :icon="Plus">创建短链接</el-button>
      <div class="search-bar">
        <el-input
          v-model="filters.search"
          placeholder="搜索链接（标题、URL、代码）"
          clearable
          style="width: 300px;"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button @click="handleSearch" :icon="Search">搜索</el-button>
      </div>
    </div>

    <!-- 表格 -->
    <el-table
      v-loading="loading"
      :data="links"
      border
      stripe
      style="width: 100%"
    >
      <el-table-column prop="id" label="ID" width="100" align="center" />
      <el-table-column prop="short_code" label="短链接代码" width="150">
        <template #default="scope">
          <el-tag type="primary">{{ scope.row.short_code }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="short_url" label="短链接" width="350" show-overflow-tooltip>
        <template #default="scope">
          <el-link :href="scope.row.short_url" target="_blank" type="primary">
            {{ scope.row.short_url }}
          </el-link>
          <el-button
            text
            type="primary"
            :icon="DocumentCopy"
            @click="copyToClipboard(scope.row.short_url)"
            style="margin-left: 8px;"
          />
        </template>
      </el-table-column>
      <el-table-column prop="original_url" label="原始URL" min-width="300" show-overflow-tooltip />
      <el-table-column prop="title" label="标题" width="150" show-overflow-tooltip />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip>
        <template #default="scope">
          <span v-if="scope.row.description">{{ scope.row.description }}</span>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="offer_id" label="关联Offer" width="200" show-overflow-tooltip>
        <template #default="scope">
          <el-tag v-if="scope.row.offer_id" type="info">
            {{ getOfferName(scope.row.offer_id) || `ID: ${scope.row.offer_id}` }}
          </el-tag>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="channel_id" label="渠道" width="200" show-overflow-tooltip>
        <template #default="scope">
          <el-tag v-if="scope.row.channel_id" type="success">
            {{ getChannelName(scope.row.channel_id) || `ID: ${scope.row.channel_id}` }}
          </el-tag>
          <span v-else style="color: #909399;">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="creator_name" label="创建者" width="120" show-overflow-tooltip>
        <template #default="scope">
          <span v-if="scope.row.creator_name">{{ scope.row.creator_name }}</span>
          <el-tag v-else type="info" size="small">未知</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="click_count" label="点击次数" width="100" align="center">
        <template #default="scope">
          <el-tag type="success">{{ scope.row.click_count }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="expires_at" label="过期时间" width="180" align="center">
        <template #default="scope">
          <span v-if="scope.row.expires_at">{{ formatDate(scope.row.expires_at) }}</span>
          <el-tag v-else type="info" size="small">永不过期</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="激活" width="80" align="center">
        <template #default="scope">
          <el-switch
            v-model="scope.row.is_active"
            @change="handleToggleActive(scope.row)"
            :loading="scope.row._toggleLoading"
          />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="scope">
          {{ formatDate(scope.row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="scope">
          <el-button type="primary" size="small" @click="handleEdit(scope.row)">编辑</el-button>
          <el-button type="danger" size="small" @click="handleDelete(scope.row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
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

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      :width="isMobile ? '95%' : '600px'"
      :append-to-body="true"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="原始URL" prop="original_url">
          <el-input
            v-model="formData.original_url"
            type="textarea"
            :rows="5"
            placeholder="https://example.com/very/long/url"
            clearable
          />
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>必须包含协议（http://或https://）</span>
          </div>
        </el-form-item>

        <el-form-item label="自定义代码" prop="short_code">
          <div style="display: flex; gap: 8px;">
            <el-input
              v-model="formData.short_code"
              placeholder="留空则自动生成（3-20个字符，字母、数字、连字符、下划线）"
              clearable
              :disabled="isEdit"
              style="flex: 1;"
            />
            <el-button
              v-if="!isEdit"
              @click="handleGenerateCode"
              :loading="generatingCode"
              :icon="Refresh"
            >
              自动生成
            </el-button>
          </div>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span v-if="isEdit">编辑时不可修改代码</span>
            <span v-else>点击"自动生成"按钮生成唯一代码，或手动输入自定义代码</span>
          </div>
        </el-form-item>

        <el-form-item label="标题" prop="title">
          <el-input
            v-model="formData.title"
            placeholder="短链接标题（可选）"
            clearable
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="短链接描述（可选）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="关联Offer" prop="offer_id">
          <el-select
            v-model="formData.offer_id"
            placeholder="选择关联的Offer（可选）"
            filterable
            clearable
            popper-class="select-dropdown"
            :teleported="true"
            style="width: 100%;"
          >
            <el-option
              v-for="offer in offerList"
              :key="offer.id"
              :label="`${offer.offer_name} (ID: ${offer.id})`"
              :value="offer.id"
            />
          </el-select>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>选择关联的Offer，用于标识短链接所属的Offer</span>
          </div>
        </el-form-item>

        <el-form-item label="关联渠道" prop="channel_id">
          <el-select
            v-model="formData.channel_id"
            placeholder="选择关联的渠道（可选）"
            filterable
            clearable
            popper-class="select-dropdown"
            :teleported="true"
            style="width: 100%;"
          >
            <el-option
              v-for="channel in channelList"
              :key="channel.id"
              :label="`${channel.publisher_name} (ID: ${channel.id})`"
              :value="channel.id"
            />
          </el-select>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>选择关联的渠道，用于标识短链接所属的渠道</span>
          </div>
        </el-form-item>

        <el-form-item label="过期时间" prop="expires_at">
          <el-date-picker
            v-model="formData.expires_at"
            type="datetime"
            placeholder="选择过期时间（可选）"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%;"
          />
        </el-form-item>

        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="formData.is_active" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="handleDialogClose">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { ElMessage, ElMessageBox, ElStatistic } from 'element-plus';
import { Plus, Search, DocumentCopy, InfoFilled, Refresh } from '@element-plus/icons-vue';
import {
  createShortLink,
  getShortLinks,
  updateShortLink,
  deleteShortLink,
  getShortLinkStats,
  generateShortCode,
  checkShortCode
} from '../../api/shortLink';
import { getOffers } from '../../api/offer';
import { getPublishers } from '../../api/publisher';
import { useDevice } from '../../composables/useDevice';
import { logger } from '../../utils/logger';
import { formatDate as formatDateWithTimezone } from '../../utils/dateFormat';

const { isMobile } = useDevice();

const loading = ref(false);
const saving = ref(false);
const generatingCode = ref(false);
const dialogVisible = ref(false);
const isEdit = ref(false);
const currentLinkId = ref(null);

const links = ref([]);
const offerList = ref([]);
const channelList = ref([]);
const stats = reactive({
  total_links: 0,
  total_clicks: 0,
  active_links: 0,
  expired_links: 0
});

const filters = reactive({
  search: null,
  is_active: null
});

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
});

const formRef = ref(null);
const formData = reactive({
  original_url: '',
  short_code: '',
  title: '',
  description: '',
  offer_id: null,
  channel_id: null,
  expires_at: null,
  is_active: true
});

const dialogTitle = computed(() => {
  return isEdit.value ? '编辑短链接' : '创建短链接';
});

const formRules = {
  original_url: [
    { required: true, message: '请输入原始URL', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (!value) {
          callback();
          return;
        }
        try {
          const url = new URL(value);
          if (!url.protocol || !url.hostname) {
            callback(new Error('URL格式无效，必须包含协议和域名'));
          } else {
            callback();
          }
        } catch (e) {
          callback(new Error('URL格式无效'));
        }
      },
      trigger: 'blur'
    }
  ],
  short_code: [
    {
      validator: (rule, value, callback) => {
        if (!value) {
          callback();
          return;
        }
        if (!/^[a-zA-Z0-9_-]+$/.test(value)) {
          callback(new Error('短链接代码只能包含字母、数字、连字符和下划线'));
        } else if (value.length < 3) {
          callback(new Error('短链接代码至少需要3个字符'));
        } else if (value.length > 20) {
          callback(new Error('短链接代码最多20个字符'));
        } else {
          callback();
        }
      },
      trigger: 'blur'
    }
  ]
};

// 加载数据
const loadData = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...filters
    };
    const result = await getShortLinks(params);
    // 初始化每个链接的加载状态
    links.value = (result.data || []).map(link => ({
      ...link,
      _toggleLoading: false
    }));
    pagination.total = result.total || 0;
  } catch (error) {
    logger.error('加载短链接列表失败:', error);
  } finally {
    loading.value = false;
  }
};

// 加载统计
const loadStats = async () => {
  try {
    const statsData = await getShortLinkStats();
    Object.assign(stats, statsData);
  } catch (error) {
    logger.error('加载统计失败:', error);
  }
};

// 加载Offer列表
const loadOffers = async () => {
  try {
    const response = await getOffers({ page: 1, page_size: 100 });
    if (response.code === 200) {
      offerList.value = response.data || [];
    }
  } catch (error) {
    logger.error('加载Offer列表失败:', error);
  }
};

// 加载渠道列表
const loadChannels = async () => {
  try {
    const response = await getPublishers({ page: 1, page_size: 100 });
    if (response.code === 200) {
      channelList.value = response.data || [];
    }
  } catch (error) {
    logger.error('加载渠道列表失败:', error);
  }
};

// 获取Offer名称
const getOfferName = (offerId) => {
  if (!offerId) return null;
  const offer = offerList.value.find(o => o.id === offerId);
  return offer ? offer.offer_name : null;
};

// 获取渠道名称
const getChannelName = (channelId) => {
  if (!channelId) return null;
  const channel = channelList.value.find(c => c.id === channelId);
  return channel ? channel.publisher_name : null;
};

// 创建
const handleCreate = () => {
  isEdit.value = false;
  currentLinkId.value = null;
  Object.assign(formData, {
    original_url: '',
    short_code: '',
    title: '',
    description: '',
    offer_id: null,
    channel_id: null,
    expires_at: null,
    is_active: true
  });
  dialogVisible.value = true;
};

// 编辑
const handleEdit = async (link) => {
  isEdit.value = true;
  currentLinkId.value = link.id;
  Object.assign(formData, {
    original_url: link.original_url,
    short_code: link.short_code,
    title: link.title || '',
    description: link.description || '',
    offer_id: link.offer_id || null,
    channel_id: link.channel_id || null,
    expires_at: link.expires_at || null,
    is_active: link.is_active
  });
  dialogVisible.value = true;
};

// 保存
const handleSave = async () => {
  if (!formRef.value) return;
  
  try {
    await formRef.value.validate();
    saving.value = true;
    
    const submitData = { ...formData };
    if (!submitData.short_code) {
      delete submitData.short_code; // 空字符串时删除，让后端自动生成
    }
    
    if (isEdit.value) {
      await updateShortLink(currentLinkId.value, submitData);
      ElMessage.success('短链接更新成功');
    } else {
      await createShortLink(submitData);
      ElMessage.success('短链接创建成功');
    }
    
    dialogVisible.value = false;
    await loadData();
    await loadStats();
  } catch (error) {
    logger.error('保存短链接失败:', error);
  } finally {
    saving.value = false;
  }
};

// 删除
const handleDelete = async (linkId) => {
  try {
    await ElMessageBox.confirm('确定要删除这个短链接吗？', '确认删除', {
      type: 'warning'
    });
    
    await deleteShortLink(linkId);
    ElMessage.success('短链接已删除');
    await loadData();
    await loadStats();
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('删除短链接失败:', error);
    }
  }
};

// 切换激活状态
const handleToggleActive = async (link) => {
  // 防止重复点击
  if (link._toggleLoading) {
    return;
  }
  
  // 保存原始值（因为 switch 已经切换了，所以取反得到原值）
  const originalValue = !link.is_active;
  const newValue = link.is_active;
  
  // 设置加载状态
  link._toggleLoading = true;
  
  try {
    // 只更新 is_active 字段
    await updateShortLink(link.id, { is_active: newValue });
    ElMessage.success(newValue ? '短链接已激活' : '短链接已禁用');
    // 更新统计
    await loadStats();
  } catch (error) {
    // 如果失败，恢复原值
    link.is_active = originalValue;
    // 错误消息已经在 updateShortLink 中显示了，这里不需要再显示
    logger.error('切换激活状态失败:', error);
  } finally {
    link._toggleLoading = false;
  }
};

// 搜索
const handleSearch = () => {
  pagination.page = 1;
  loadData();
};

// 分页
const handleSizeChange = () => {
  loadData();
};

const handlePageChange = () => {
  loadData();
};

// 复制到剪贴板
const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success('已复制到剪贴板');
  } catch (error) {
    // 忽略浏览器扩展相关的错误（这些错误不影响复制功能）
    const errorMessage = error?.message || String(error || '').toLowerCase();
    const isExtensionError = typeof errorMessage === 'string' && (
      errorMessage.includes('message channel closed') ||
      errorMessage.includes('asynchronous response') ||
      errorMessage.includes('listener indicated') ||
      errorMessage.includes('channel closed')
    );
    
    // 如果是扩展错误，尝试使用备用方法复制
    if (isExtensionError) {
      try {
        // 使用传统的 execCommand 方法作为备用
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
          ElMessage.success('已复制到剪贴板');
          return;
        }
      } catch (fallbackError) {
        // 备用方法也失败，静默处理
      }
      // 扩展错误不影响功能，静默处理
      return;
    }
    
    // 其他错误才显示错误消息
    ElMessage.error('复制失败');
  }
};

// 格式化日期
const formatDate = (dateString) => {
  return formatDateWithTimezone(dateString);
};

// 自动生成代码
const handleGenerateCode = async () => {
  if (isEdit.value) {
    return; // 编辑模式下不允许生成
  }
  
  generatingCode.value = true;
  try {
    const result = await generateShortCode();
    if (result && result.short_code) {
      formData.short_code = result.short_code;
      ElMessage.success('代码已生成');
    }
  } catch (error) {
    logger.error('生成代码失败:', error);
  } finally {
    generatingCode.value = false;
  }
};

// 关闭对话框
const handleDialogClose = () => {
  dialogVisible.value = false;
  if (formRef.value) {
    formRef.value.clearValidate();
  }
};

// 初始化
onMounted(() => {
  loadData();
  loadStats();
  loadOffers();
  loadChannels();
});
</script>

<style scoped>
.short-link-management {
  padding: 20px;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.search-bar {
  display: flex;
  gap: 10px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.form-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>

