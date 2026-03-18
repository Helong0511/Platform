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
  // API缓存
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
  },
  {
    key: 'api:products:all',
    size: 6144,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 95,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"products": [{"id": 1, "name": "Test Product", "status": "active"}]}',
    canView: true
  },
  {
    key: 'api:users:list',
    size: 4608,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 67,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"users": [{"id": 1, "username": "admin", "role": "admin"}]}',
    canView: true
  },
  // 短链接缓存
  {
    key: 'shortlink:all',
    size: 8192,
    expireTime: Date.now() + 3600000,
    type: 'ShortLink',
    hits: 200,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"shortlinks": [{"id": 1, "code": "abc123", "target_url": "https://example.com", "clicks": 150}]}',
    canView: true
  },
  {
    key: 'shortlink:stats:abc123',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'ShortLink',
    hits: 150,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"clicks": 150, "last_click": "2026-03-18 10:00:00"}',
    canView: true
  },
  // 斗篷缓存
  {
    key: 'cloak:all',
    size: 12288,
    expireTime: Date.now() + 3600000,
    type: 'Cloak',
    hits: 180,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"cloaks": [{"id": 1, "name": "Test Cloak", "status": "active"}]}',
    canView: true
  },
  {
    key: 'cloak:stats:1',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'Cloak',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"views": 120, "conversions": 15}',
    canView: true
  },
  // 系统缓存
  {
    key: 'system:config',
    size: 2048,
    expireTime: null,
    type: 'System',
    hits: 500,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"system": {"version": "1.0.0", "maintenance": false}}',
    canView: true
  },
  {
    key: 'system:stats',
    size: 3072,
    expireTime: Date.now() + 300000,
    type: 'System',
    hits: 250,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"stats": {"active_users": 15, "requests_per_minute": 45}}',
    canView: true
  },
  // 用户缓存
  {
    key: 'user:1:session',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'User',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"user_id": 1, "last_activity": "2026-03-18 09:00:00"}',
    canView: true
  },
  {
    key: 'user:preferences',
    size: 1024,
    expireTime: null,
    type: 'User',
    hits: 85,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"theme": "dark", "language": "zh-CN"}',
    canView: true
  },
  // 产品缓存
  {
    key: 'product:all',
    size: 7168,
    expireTime: Date.now() + 3600000,
    type: 'Product',
    hits: 130,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"products": [{"id": 1, "name": "Test Product", "price": 99.99}]}',
    canView: true
  },
  // 会话缓存
  {
    key: 'session:all',
    size: 5120,
    expireTime: Date.now() + 1800000,
    type: 'Session',
    hits: 90,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"sessions": [{"id": 1, "user_id": 1, "status": "active"}]}',
    canView: true
  },
  // 审计日志缓存
  {
    key: 'audit:logs:recent',
    size: 9216,
    expireTime: Date.now() + 3600000,
    type: 'AuditLog',
    hits: 45,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"logs": [{"id": 1, "user_id": 1, "action": "login", "timestamp": "2026-03-18 08:00:00"}]}',
    canView: true
  },
  // 任务缓存
  {
    key: 'task:scheduled',
    size: 4096,
    expireTime: Date.now() + 3600000,
    type: 'Task',
    hits: 60,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"tasks": [{"id": 1, "name": "Cleanup", "status": "scheduled"}]}',
    canView: true
  },
  // 其他缓存
  {
    key: 'other:temp:data',
    size: 2048,
    expireTime: Date.now() + 600000,
    type: 'Other',
    hits: 30,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"temp": "some temporary data"}',
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
    'Other': 'info',
    'ShortLink': 'success',
    'Cloak': 'warning',
    'Product': 'info',
    'Session': 'primary',
    'AuditLog': 'danger',
    'Task': 'warning'
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