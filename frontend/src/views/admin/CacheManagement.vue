<!--
  管理端 - 系统缓存管理
  @file views/admin/CacheManagement.vue
-->
<template>
  <!-- 页面主模板 -->
<div class="cache-management">
    <el-card class="page-card">
      <!-- 卡片标题栏 -->
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
        <!-- 卡片视图展示所有缓存 -->
        <div class="cache-cards">
          <div 
            v-for="(cache, index) in flatCacheList" 
            :key="cache.key" 
            class="cache-card"
          >
            <div class="cache-card-header">
              <div class="cache-card-title">
                <span class="cache-key">{{ cache.key }}</span>
                <span v-if="cache.comment" class="cache-comment">({{ cache.comment }})</span>
              </div>
              <el-tag :type="getTypeColor(cache.type)">{{ cache.type }}</el-tag>
            </div>
            <div class="cache-card-body">
              <div class="cache-card-meta">
                <div class="cache-meta-item">
                  <span class="meta-label">大小:</span>
                  <span class="meta-value">{{ formatSize(cache.size) }}</span>
                </div>
                <div class="cache-meta-item">
                  <span class="meta-label">访问:</span>
                  <span class="meta-value">{{ cache.hits }}</span>
                </div>
                <div class="cache-meta-item">
                  <span class="meta-label">过期:</span>
                  <span class="meta-value">{{ formatExpireTime(cache.expireTime) }}</span>
                </div>
                <div class="cache-meta-item">
                  <span class="meta-label">创建:</span>
                  <span class="meta-value">{{ cache.createdAt }}</span>
                </div>
              </div>
            </div>
            <div class="cache-card-footer">
              <el-button
                size="small"
                type="primary"
                @click="viewCache(cache)"
                :disabled="!cache.canView"
              >
                查看
              </el-button>
              <el-button
                size="small"
                type="warning"
                @click="refreshCache(cache)"
              >
                刷新
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="clearCache(cache)"
              >
                清除
              </el-button>
            </div>
          </div>
        </div>

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
import { onMounted } from 'vue';
import { Refresh, Delete, Download } from '@element-plus/icons-vue';
import { useCacheList } from '@/composables/useCacheList';
import { useCacheActions } from '@/composables/useCacheActions';
import {
  formatCacheSize as formatSize,
  formatCacheExpireTime as formatExpireTime,
  getCacheTypeColor as getTypeColor,
  formatCacheContent,
} from '@/utils/cacheFormat';

const { loading, flatCacheList, refreshCacheList, removeByKey, clearAll } = useCacheList();

const {
  clearingAll,
  cacheDetailVisible,
  currentCache,
  viewCache,
  refreshCache,
  clearCache,
  clearAllCache,
  exportCacheStats,
} = useCacheActions({ removeByKey, clearAll, refreshCacheList });

onMounted(() => {
  refreshCacheList();
});
</script>
<style scoped>
.cache-management {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.cache-content {
  margin-top: 20px;
  width: 100%;
  overflow-x: auto;
}

/* 卡片视图样式 */
.cache-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.cache-card {
  background-color: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 16px;
  transition: all 0.3s ease;
}

.cache-card:hover {
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.cache-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

.cache-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  margin-right: 12px;
}

.cache-key {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 200px;
}

.cache-comment {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 100px;
}

.cache-card-body {
  margin-bottom: 16px;
}

.cache-card-meta {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.cache-meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.meta-label {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.meta-value {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cache-card-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* 调整操作按钮大小 */
.cache-card-footer .el-button {
  font-size: 12px;
  padding: 4px 8px;
  min-width: 50px;
  height: 28px;
  line-height: 20px;
}

/* 确保标签不会被压缩 */
.cache-card-header .el-tag {
  flex-shrink: 0;
  font-size: 12px;
  padding: 0 8px;
  height: 20px;
  line-height: 18px;
}

/* 响应式设计 */
@media (max-width: 767px) {
  .cache-cards {
    grid-template-columns: 1fr;
  }
  
  .cache-card-meta {
    grid-template-columns: 1fr;
  }
  
  .cache-card-footer {
    flex-direction: column;
  }
  
  .cache-card-footer .el-button {
    width: 100%;
  }
}

.cache-actions {
  margin-top: 20px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.cache-detail {
  max-height: 60vh;
  overflow-y: auto;
}

.cache-content-pre {
  background-color: #1f2329;
  color: #e6e6e6;
  padding: 16px;
  border-radius: 4px;
  overflow-x: auto;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

/* 响应式设计 */
@media (max-width: 767px) {
  .cache-management {
    padding: 16px;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .cache-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .tree-node-meta {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .tree-node-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>