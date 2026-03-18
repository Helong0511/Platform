<template>
  <div class="cache-management">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <h1 class="page-title">缓存管理</h1>
          <el-button type="primary" @click="refreshCacheList" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新缓存列表
          </el-button>
        </div>
      </template>

      <div class="cache-content">
        <el-table
          v-loading="loading"
          :data="cacheList"
          style="width: 100%"
          border
          stripe
        >
          <el-table-column prop="key" label="缓存键" width="300">
            <template #default="scope">
              <el-tag size="small" effect="plain">{{ scope.row.key }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="size" label="缓存大小" width="120">
            <template #default="scope">
              {{ formatSize(scope.row.size) }}
            </template>
          </el-table-column>
          <el-table-column prop="expireTime" label="过期时间" width="180">
            <template #default="scope">
              {{ formatExpireTime(scope.row.expireTime) }}
            </template>
          </el-table-column>
          <el-table-column prop="type" label="缓存类型" width="120">
            <template #default="scope">
              <el-tag :type="getTypeColor(scope.row.type)">
                {{ scope.row.type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="hits" label="访问次数" width="100" />
          <el-table-column prop="createdAt" label="创建时间" width="180" />
          <el-table-column prop="updatedAt" label="更新时间" width="180" />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="scope">
              <el-button
                size="small"
                type="primary"
                @click="viewCache(scope.row)"
                :disabled="!scope.row.canView"
              >
                查看
              </el-button>
              <el-button
                size="small"
                type="warning"
                @click="refreshCache(scope.row)"
              >
                刷新
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="clearCache(scope.row)"
              >
                清除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="cache-actions">
          <el-button
            type="danger"
            @click="clearAllCache"
            :loading="clearingAll"
          >
            <el-icon><Delete /></el-icon>
            清除所有缓存
          </el-button>
          <el-button
            type="info"
            @click="exportCacheStats"
          >
            <el-icon><Download /></el-icon>
            导出缓存统计
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 缓存详情对话框 -->
    <el-dialog
      v-model="cacheDetailVisible"
      title="缓存详情"
      width="80%"
    >
      <div class="cache-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="缓存键">{{ currentCache.key }}</el-descriptions-item>
          <el-descriptions-item label="缓存类型">{{ currentCache.type }}</el-descriptions-item>
          <el-descriptions-item label="缓存大小">{{ formatSize(currentCache.size) }}</el-descriptions-item>
          <el-descriptions-item label="过期时间">{{ formatExpireTime(currentCache.expireTime) }}</el-descriptions-item>
          <el-descriptions-item label="访问次数">{{ currentCache.hits }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ currentCache.createdAt }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ currentCache.updatedAt }}</el-descriptions-item>
          <el-descriptions-item label="缓存内容">
            <pre class="cache-content-pre">{{ formatCacheContent(currentCache.content) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { ElCard, ElTable, ElTableColumn, ElButton, ElTag, ElDialog, ElDescriptions, ElDescriptionsItem, ElMessage, ElLoading } from 'element-plus';
import { Refresh, Delete, Download } from '@element-plus/icons-vue';

// 模拟缓存数据
const cacheList = ref([
  {
    key: 'api:offers:all',
    size: 10240,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 150,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"offers": [{"id": 1, "name": "Test Offer", "status": "active"}]}',
    canView: true
  },
  {
    key: 'api:advertisers:list',
    size: 5120,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 89,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"advertisers": [{"id": 1, "name": "Test Advertiser"}]}',
    canView: true
  },
  {
    key: 'api:publishers:list',
    size: 7680,
    expireTime: Date.now() + 2700000,
    type: 'API',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"publishers": [{"id": 1, "name": "Test Publisher"}]}',
    canView: true
  },
  {
    key: 'api:caps:all',
    size: 3072,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 56,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"caps": [{"id": 1, "offerId": 1, "value": 100}]}',
    canView: true
  },
  {
    key: 'api:discounts:all',
    size: 4096,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 78,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"discounts": [{"id": 1, "offerId": 1, "value": 10}]}',
    canView: true
  }
]);

const loading = ref(false);
const clearingAll = ref(false);
const cacheDetailVisible = ref(false);
const currentCache = ref({});

// 格式化缓存大小
const formatSize = (bytes) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// 格式化过期时间
const formatExpireTime = (expireTime) => {
  if (!expireTime) return '永不过期';
  const now = Date.now();
  const diff = expireTime - now;
  if (diff < 0) return '已过期';
  if (diff < 60000) return '不到1分钟';
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟';
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时';
  return Math.floor(diff / 86400000) + '天';
};

// 获取缓存类型颜色
const getTypeColor = (type) => {
  const colorMap = {
    'API': 'primary',
    'System': 'success',
    'User': 'warning',
    'Other': 'info'
  };
  return colorMap[type] || 'info';
};

// 格式化缓存内容
const formatCacheContent = (content) => {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
};

// 刷新缓存列表
const refreshCacheList = () => {
  loading.value = true;
  // 模拟API请求
  setTimeout(() => {
    // 这里可以调用后端API获取真实的缓存列表
    ElMessage.success('缓存列表已刷新');
    loading.value = false;
  }, 1000);
};

// 查看缓存详情
const viewCache = (cache) => {
  currentCache.value = { ...cache };
  cacheDetailVisible.value = true;
};

// 刷新缓存
const refreshCache = (cache) => {
  ElButton().$confirm('确定要刷新此缓存吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    // 模拟API请求
    setTimeout(() => {
      ElMessage.success(`缓存 ${cache.key} 已刷新`);
    }, 500);
  }).catch(() => {
    // 取消操作
  });
};

// 清除缓存
const clearCache = (cache) => {
  ElButton().$confirm('确定要清除此缓存吗？', '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'danger'
  }).then(() => {
    // 模拟API请求
    setTimeout(() => {
      // 从列表中移除
      const index = cacheList.value.findIndex(item => item.key === cache.key);
      if (index > -1) {
        cacheList.value.splice(index, 1);
      }
      ElMessage.success(`缓存 ${cache.key} 已清除`);
    }, 500);
  }).catch(() => {
    // 取消操作
  });
};

// 清除所有缓存
const clearAllCache = () => {
  ElButton().$confirm('确定要清除所有缓存吗？此操作不可恢复！', '危险', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'danger'
  }).then(() => {
    clearingAll.value = true;
    // 模拟API请求
    setTimeout(() => {
      cacheList.value = [];
      ElMessage.success('所有缓存已清除');
      clearingAll.value = false;
    }, 1500);
  }).catch(() => {
    // 取消操作
  });
};

// 导出缓存统计
const exportCacheStats = () => {
  // 模拟导出操作
  setTimeout(() => {
    ElMessage.success('缓存统计已导出');
  }, 1000);
};

// 组件挂载时刷新缓存列表
onMounted(() => {
  refreshCacheList();
});
</script>

<style scoped>
.cache-management {
  padding: var(--spacing-lg);
  min-height: 100vh;
  background-color: var(--bg-light);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-dark);
  margin: 0;
}

.cache-content {
  margin-top: var(--spacing-lg);
}

.cache-actions {
  margin-top: var(--spacing-lg);
  display: flex;
  gap: var(--spacing-md);
  justify-content: flex-end;
}

.cache-detail {
  max-height: 60vh;
  overflow-y: auto;
}

.cache-content-pre {
  background-color: var(--bg-dark);
  color: var(--text-white);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  overflow-x: auto;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-tight);
}

/* 响应式设计 */
@media (max-width: 767px) {
  .cache-management {
    padding: var(--spacing-md);
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-md);
  }

  .cache-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>