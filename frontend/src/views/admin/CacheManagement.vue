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
        <!-- 树状结构展示 -->
        <el-tree
          v-loading="loading"
          :data="treeData"
          :props="treeProps"
          node-key="key"
          default-expand-all
          @node-click="handleNodeClick"
          class="cache-tree"
        >
          <template #default="{ node, data }">
            <div class="tree-node-content">
              <div class="node-header">
                <span class="node-key">{{ data.key }}</span>
                <span v-if="data.comment" class="node-comment">({{ data.comment }})</span>
              </div>
              <div v-if="data.size" class="node-meta">
                <el-tag size="small" :type="getTypeColor(data.type)">{{ data.type }}</el-tag>
                <span class="node-size">{{ formatSize(data.size) }}</span>
                <span class="node-hits">访问: {{ data.hits }}</span>
                <div class="node-actions">
                  <el-button
                    size="small"
                    type="primary"
                    @click.stop="viewCache(data)"
                    :disabled="!data.canView"
                  >
                    查看
                  </el-button>
                  <el-button
                    size="small"
                    type="warning"
                    @click.stop="refreshCache(data)"
                  >
                    刷新
                  </el-button>
                  <el-button
                    size="small"
                    type="danger"
                    @click.stop="clearCache(data)"
                  >
                    清除
                  </el-button>
                </div>
              </div>
            </div>
          </template>
        </el-tree>

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
import { ref, onMounted, computed } from 'vue';
import { ElCard, ElButton, ElTag, ElDialog, ElDescriptions, ElDescriptionsItem, ElMessage, ElLoading, ElTree } from 'element-plus';
import { Refresh, Delete, Download } from '@element-plus/icons-vue';

// 模拟缓存数据
const cacheList = ref([
  // API缓存
  {
    key: 'api:offers:all',
    comment: '所有Offer列表',
    size: 10240,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 150,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"offers": [{"id": 1, "name": "Test Offer", "status": "active"}, {"id": 2, "name": "Second Offer", "status": "active"}, {"id": 3, "name": "Third Offer", "status": "inactive"}]}',
    canView: true
  },
  // 单个Offer缓存
  {
    key: 'api:offer:1',
    comment: 'Offer 1详情',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Test Offer", "status": "active", "payout": 10.0, "created_at": "2026-03-01 08:00:00", "updated_at": "2026-03-15 10:00:00"}',
    canView: true
  },
  {
    key: 'api:offer:2',
    comment: 'Offer 2详情',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 90,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 2, "name": "Second Offer", "status": "active", "payout": 15.0, "created_at": "2026-03-05 09:00:00", "updated_at": "2026-03-16 11:00:00"}',
    canView: true
  },
  {
    key: 'api:offer:3',
    comment: 'Offer 3详情',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 60,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 3, "name": "Third Offer", "status": "inactive", "payout": 8.0, "created_at": "2026-03-10 10:00:00", "updated_at": "2026-03-17 12:00:00"}',
    canView: true
  },
  // 广告主缓存
  {
    key: 'api:advertisers:list',
    comment: '所有广告主列表',
    size: 5120,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 89,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"advertisers": [{"id": 1, "name": "Test Advertiser"}, {"id": 2, "name": "Second Advertiser"}, {"id": 3, "name": "Third Advertiser"}]}',
    canView: true
  },
  {
    key: 'api:advertiser:1',
    comment: '广告主 1详情',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 70,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Test Advertiser", "contact": "test@example.com", "status": "active", "created_at": "2026-02-01 08:00:00"}',
    canView: true
  },
  // 渠道缓存
  {
    key: 'api:publishers:list',
    comment: '所有渠道列表',
    size: 7680,
    expireTime: Date.now() + 2700000,
    type: 'API',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"publishers": [{"id": 1, "name": "Test Publisher"}, {"id": 2, "name": "Second Publisher"}, {"id": 3, "name": "Third Publisher"}]}',
    canView: true
  },
  {
    key: 'api:publisher:1',
    comment: '渠道 1详情',
    size: 1536,
    expireTime: Date.now() + 2700000,
    type: 'API',
    hits: 95,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Test Publisher", "contact": "publisher@example.com", "status": "active", "created_at": "2026-02-15 09:00:00"}',
    canView: true
  },
  // Cap缓存
  {
    key: 'api:caps:all',
    comment: '所有Cap列表',
    size: 3072,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 56,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"caps": [{"id": 1, "offerId": 1, "value": 100}, {"id": 2, "offerId": 2, "value": 200}, {"id": 3, "offerId": 3, "value": 150}]}',
    canView: true
  },
  {
    key: 'api:cap:1',
    comment: 'Cap 1详情',
    size: 1024,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 45,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "offerId": 1, "value": 100, "current": 85, "status": "active", "created_at": "2026-03-01 10:00:00"}',
    canView: true
  },
  // 扣量缓存
  {
    key: 'api:discounts:all',
    comment: '所有扣量列表',
    size: 4096,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 78,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"discounts": [{"id": 1, "offerId": 1, "value": 10}, {"id": 2, "offerId": 2, "value": 15}, {"id": 3, "offerId": 3, "value": 5}]}',
    canView: true
  },
  {
    key: 'api:discount:1',
    comment: '扣量 1详情',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 65,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "offerId": 1, "value": 10, "status": "active", "created_at": "2026-03-05 11:00:00", "updated_at": "2026-03-10 14:00:00"}',
    canView: true
  },
  // 产品缓存
  {
    key: 'api:products:all',
    comment: '所有产品列表',
    size: 6144,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 95,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"products": [{"id": 1, "name": "Test Product", "status": "active"}, {"id": 2, "name": "Second Product", "status": "active"}, {"id": 3, "name": "Third Product", "status": "inactive"}]}',
    canView: true
  },
  {
    key: 'api:product:1',
    comment: '产品 1详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'API',
    hits: 80,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Test Product", "price": 99.99, "status": "active", "created_at": "2026-03-01 12:00:00", "updated_at": "2026-03-15 16:00:00"}',
    canView: true
  },
  // 用户缓存
  {
    key: 'api:users:list',
    comment: '所有用户列表',
    size: 4608,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 67,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"users": [{"id": 1, "username": "admin", "role": "admin"}, {"id": 2, "username": "user1", "role": "user"}, {"id": 3, "username": "user2", "role": "user"}]}',
    canView: true
  },
  {
    key: 'api:user:1',
    comment: '用户 1详情',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'API',
    hits: 55,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "username": "admin", "role": "admin", "email": "admin@example.com", "status": "active", "last_login": "2026-03-18 08:00:00"}',
    canView: true
  },
  // 短链接缓存
  {
    key: 'shortlink:all',
    comment: '所有短链接列表',
    size: 8192,
    expireTime: Date.now() + 3600000,
    type: 'ShortLink',
    hits: 200,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"shortlinks": [{"id": 1, "code": "abc123", "target_url": "https://example.com", "clicks": 150}, {"id": 2, "code": "def456", "target_url": "https://test.com", "clicks": 80}, {"id": 3, "code": "ghi789", "target_url": "https://demo.com", "clicks": 200}]}',
    canView: true
  },
  // 单个短链接详细信息缓存
  {
    key: 'shortlink:detail:abc123',
    comment: '短链接 abc123 详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'ShortLink',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "code": "abc123", "target_url": "https://example.com", "created_at": "2026-03-10 08:00:00", "updated_at": "2026-03-15 10:00:00", "status": "active", "clicks": 150, "creator_id": 1}',
    canView: true
  },
  {
    key: 'shortlink:detail:def456',
    comment: '短链接 def456 详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'ShortLink',
    hits: 90,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 2, "code": "def456", "target_url": "https://test.com", "created_at": "2026-03-12 09:00:00", "updated_at": "2026-03-16 11:00:00", "status": "active", "clicks": 80, "creator_id": 1}',
    canView: true
  },
  {
    key: 'shortlink:detail:ghi789',
    comment: '短链接 ghi789 详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'ShortLink',
    hits: 150,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 3, "code": "ghi789", "target_url": "https://demo.com", "created_at": "2026-03-08 10:00:00", "updated_at": "2026-03-17 12:00:00", "status": "active", "clicks": 200, "creator_id": 1}',
    canView: true
  },
  // 短链接统计数据缓存
  {
    key: 'shortlink:stats:abc123',
    comment: '短链接 abc123 统计',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'ShortLink',
    hits: 150,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"clicks": 150, "last_click": "2026-03-18 10:00:00", "today_clicks": 25, "yesterday_clicks": 30, "week_clicks": 100}',
    canView: true
  },
  {
    key: 'shortlink:stats:def456',
    comment: '短链接 def456 统计',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'ShortLink',
    hits: 80,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"clicks": 80, "last_click": "2026-03-18 09:30:00", "today_clicks": 15, "yesterday_clicks": 20, "week_clicks": 60}',
    canView: true
  },
  {
    key: 'shortlink:stats:ghi789',
    comment: '短链接 ghi789 统计',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'ShortLink',
    hits: 200,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"clicks": 200, "last_click": "2026-03-18 10:30:00", "today_clicks": 40, "yesterday_clicks": 35, "week_clicks": 150}',
    canView: true
  },
  // 短链接点击历史缓存
  {
    key: 'shortlink:history:abc123',
    comment: '短链接 abc123 点击历史',
    size: 3072,
    expireTime: Date.now() + 86400000,
    type: 'ShortLink',
    hits: 50,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"history": [{"timestamp": "2026-03-18 10:00:00", "ip": "192.168.1.1", "user_agent": "Mozilla/5.0...", "referrer": "https://google.com"}, {"timestamp": "2026-03-18 09:55:00", "ip": "192.168.1.2", "user_agent": "Mozilla/5.0...", "referrer": "https://bing.com"}]}',
    canView: true
  },
  // 短链接性能统计缓存
  {
    key: 'shortlink:performance:all',
    comment: '短链接性能统计',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'ShortLink',
    hits: 30,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"performance": {"avg_response_time": 150, "max_response_time": 500, "min_response_time": 50, "total_requests": 1000}}',
    canView: true
  },
  // 斗篷缓存
  {
    key: 'cloak:all',
    comment: '所有斗篷列表',
    size: 12288,
    expireTime: Date.now() + 3600000,
    type: 'Cloak',
    hits: 180,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"cloaks": [{"id": 1, "name": "Test Cloak", "status": "active"}, {"id": 2, "name": "Product Cloak", "status": "active"}, {"id": 3, "name": "Marketing Cloak", "status": "active"}]}',
    canView: true
  },
  // 单个斗篷详细信息缓存
  {
    key: 'cloak:detail:1',
    comment: '斗篷 1详情',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'Cloak',
    hits: 100,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Test Cloak", "url": "https://cloak.example.com/test", "created_at": "2026-03-05 08:00:00", "updated_at": "2026-03-10 10:00:00", "status": "active", "views": 120, "conversions": 15, "creator_id": 1}',
    canView: true
  },
  {
    key: 'cloak:detail:2',
    comment: '斗篷 2详情',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'Cloak',
    hits: 85,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 2, "name": "Product Cloak", "url": "https://cloak.example.com/product", "created_at": "2026-03-08 09:00:00", "updated_at": "2026-03-12 11:00:00", "status": "active", "views": 95, "conversions": 12, "creator_id": 1}',
    canView: true
  },
  {
    key: 'cloak:detail:3',
    comment: '斗篷 3详情',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'Cloak',
    hits: 110,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 3, "name": "Marketing Cloak", "url": "https://cloak.example.com/marketing", "created_at": "2026-03-10 10:00:00", "updated_at": "2026-03-15 12:00:00", "status": "active", "views": 150, "conversions": 20, "creator_id": 1}',
    canView: true
  },
  // 斗篷统计数据缓存
  {
    key: 'cloak:stats:1',
    comment: '斗篷 1统计',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'Cloak',
    hits: 120,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"views": 120, "conversions": 15, "conversion_rate": 12.5, "today_views": 20, "yesterday_views": 25, "week_views": 80}',
    canView: true
  },
  {
    key: 'cloak:stats:2',
    comment: '斗篷 2统计',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'Cloak',
    hits: 95,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"views": 95, "conversions": 12, "conversion_rate": 12.6, "today_views": 15, "yesterday_views": 20, "week_views": 65}',
    canView: true
  },
  {
    key: 'cloak:stats:3',
    comment: '斗篷 3统计',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'Cloak',
    hits: 150,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"views": 150, "conversions": 20, "conversion_rate": 13.3, "today_views": 25, "yesterday_views": 30, "week_views": 100}',
    canView: true
  },
  // 斗篷访问历史缓存
  {
    key: 'cloak:history:1',
    comment: '斗篷 1访问历史',
    size: 3072,
    expireTime: Date.now() + 86400000,
    type: 'Cloak',
    hits: 45,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"history": [{"timestamp": "2026-03-18 09:00:00", "ip": "192.168.1.1", "user_agent": "Mozilla/5.0...", "referrer": "https://google.com", "converted": true}, {"timestamp": "2026-03-18 08:30:00", "ip": "192.168.1.2", "user_agent": "Mozilla/5.0...", "referrer": "https://bing.com", "converted": false}]}',
    canView: true
  },
  // 斗篷性能统计缓存
  {
    key: 'cloak:performance:all',
    comment: '斗篷性能统计',
    size: 2048,
    expireTime: Date.now() + 3600000,
    type: 'Cloak',
    hits: 25,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"performance": {"avg_response_time": 200, "max_response_time": 600, "min_response_time": 80, "total_requests": 800, "avg_conversion_rate": 12.8}}',
    canView: true
  },
  // 系统缓存
  {
    key: 'system:config',
    comment: '系统配置',
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
    comment: '系统统计',
    size: 3072,
    expireTime: Date.now() + 300000,
    type: 'System',
    hits: 250,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"stats": {"active_users": 15, "requests_per_minute": 45}}',
    canView: true
  },
  // 系统配置缓存
  {
    key: 'system:config:database',
    comment: '数据库配置',
    size: 1024,
    expireTime: null,
    type: 'System',
    hits: 300,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"host": "localhost", "port": 3306, "database": "platform", "max_connections": 100}',
    canView: true
  },
  {
    key: 'system:config:api',
    comment: 'API配置',
    size: 1024,
    expireTime: null,
    type: 'System',
    hits: 250,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"rate_limit": 1000, "timeout": 30, "max_payload": 1048576}',
    canView: true
  },
  // 用户缓存
  {
    key: 'user:1:session',
    comment: '用户 1 会话',
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
    key: 'user:2:session',
    comment: '用户 2 会话',
    size: 1536,
    expireTime: Date.now() + 1800000,
    type: 'User',
    hits: 80,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"user_id": 2, "last_activity": "2026-03-18 08:30:00"}',
    canView: true
  },
  {
    key: 'user:1:preferences',
    comment: '用户 1 偏好设置',
    size: 1024,
    expireTime: null,
    type: 'User',
    hits: 85,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"theme": "dark", "language": "zh-CN", "notifications": true}',
    canView: true
  },
  {
    key: 'user:2:preferences',
    comment: '用户 2 偏好设置',
    size: 1024,
    expireTime: null,
    type: 'User',
    hits: 65,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"theme": "light", "language": "en-US", "notifications": false}',
    canView: true
  },
  // 产品缓存
  {
    key: 'product:all',
    comment: '所有产品列表',
    size: 7168,
    expireTime: Date.now() + 3600000,
    type: 'Product',
    hits: 130,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"products": [{"id": 1, "name": "Test Product", "price": 99.99}, {"id": 2, "name": "Second Product", "price": 199.99}, {"id": 3, "name": "Third Product", "price": 299.99}]}',
    canView: true
  },
  {
    key: 'product:1',
    comment: '产品 1详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'Product',
    hits: 100,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Test Product", "price": 99.99, "stock": 100, "category": "electronics", "created_at": "2026-03-01 08:00:00"}',
    canView: true
  },
  {
    key: 'product:2',
    comment: '产品 2详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'Product',
    hits: 85,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 2, "name": "Second Product", "price": 199.99, "stock": 50, "category": "electronics", "created_at": "2026-03-05 09:00:00"}',
    canView: true
  },
  // 会话缓存
  {
    key: 'session:all',
    comment: '所有会话列表',
    size: 5120,
    expireTime: Date.now() + 1800000,
    type: 'Session',
    hits: 90,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"sessions": [{"id": 1, "user_id": 1, "status": "active"}, {"id": 2, "user_id": 2, "status": "active"}, {"id": 3, "user_id": 3, "status": "inactive"}]}',
    canView: true
  },
  {
    key: 'session:1',
    comment: '会话 1详情',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'Session',
    hits: 75,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "user_id": 1, "token": "abc123", "ip": "192.168.1.1", "user_agent": "Mozilla/5.0...", "created_at": "2026-03-18 08:00:00", "expires_at": "2026-03-18 14:00:00"}',
    canView: true
  },
  {
    key: 'session:2',
    comment: '会话 2详情',
    size: 1024,
    expireTime: Date.now() + 1800000,
    type: 'Session',
    hits: 60,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 2, "user_id": 2, "token": "def456", "ip": "192.168.1.2", "user_agent": "Mozilla/5.0...", "created_at": "2026-03-18 08:30:00", "expires_at": "2026-03-18 14:30:00"}',
    canView: true
  },
  // 审计日志缓存
  {
    key: 'audit:logs:recent',
    comment: '最近审计日志',
    size: 9216,
    expireTime: Date.now() + 3600000,
    type: 'AuditLog',
    hits: 45,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"logs": [{"id": 1, "user_id": 1, "action": "login", "timestamp": "2026-03-18 08:00:00"}, {"id": 2, "user_id": 1, "action": "update_user", "timestamp": "2026-03-18 09:00:00"}, {"id": 3, "user_id": 2, "action": "create_offer", "timestamp": "2026-03-18 10:00:00"}]}',
    canView: true
  },
  {
    key: 'audit:log:1',
    comment: '审计日志 1详情',
    size: 1024,
    expireTime: Date.now() + 86400000,
    type: 'AuditLog',
    hits: 30,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "user_id": 1, "action": "login", "ip": "192.168.1.1", "user_agent": "Mozilla/5.0...", "timestamp": "2026-03-18 08:00:00", "details": "User admin logged in successfully"}',
    canView: true
  },
  // 任务缓存
  {
    key: 'task:scheduled',
    comment: '计划任务列表',
    size: 4096,
    expireTime: Date.now() + 3600000,
    type: 'Task',
    hits: 60,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"tasks": [{"id": 1, "name": "Cleanup", "status": "scheduled"}, {"id": 2, "name": "Backup", "status": "scheduled"}, {"id": 3, "name": "Sync", "status": "scheduled"}]}',
    canView: true
  },
  {
    key: 'task:1',
    comment: '任务 1详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'Task',
    hits: 45,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 1, "name": "Cleanup", "status": "scheduled", "schedule": "0 0 * * *", "last_run": "2026-03-17 00:00:00", "next_run": "2026-03-18 00:00:00"}',
    canView: true
  },
  {
    key: 'task:2',
    comment: '任务 2详情',
    size: 1536,
    expireTime: Date.now() + 3600000,
    type: 'Task',
    hits: 40,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"id": 2, "name": "Backup", "status": "scheduled", "schedule": "0 1 * * *", "last_run": "2026-03-17 01:00:00", "next_run": "2026-03-18 01:00:00"}',
    canView: true
  },
  // 其他缓存
  {
    key: 'other:temp:data',
    comment: '临时数据',
    size: 2048,
    expireTime: Date.now() + 600000,
    type: 'Other',
    hits: 30,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"temp": "some temporary data"}',
    canView: true
  },
  {
    key: 'other:temp:import:1',
    comment: '导入任务 1临时数据',
    size: 3072,
    expireTime: Date.now() + 600000,
    type: 'Other',
    hits: 15,
    createdAt: new Date().toLocaleString(),
    updatedAt: new Date().toLocaleString(),
    content: '{"import_id": 1, "status": "processing", "progress": 50, "total": 100, "processed": 50}',
    canView: true
  }
]);

const loading = ref(false);
const clearingAll = ref(false);
const cacheDetailVisible = ref(false);
const currentCache = ref({});

// 树状结构配置
const treeProps = {
  children: 'children',
  label: 'key'
};

// 生成树状数据
const treeData = computed(() => {
  const tree = [];
  const map = new Map();
  
  // 为每个缓存项创建节点
  cacheList.value.forEach(item => {
    const parts = item.key.split(':');
    let currentLevel = tree;
    let currentPath = '';
    
    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}:${part}` : part;
      
      let node = map.get(currentPath);
      if (!node) {
        node = {
          key: currentPath,
          comment: index === parts.length - 1 ? item.comment : '',
          size: index === parts.length - 1 ? item.size : undefined,
          type: index === parts.length - 1 ? item.type : undefined,
          hits: index === parts.length - 1 ? item.hits : undefined,
          expireTime: index === parts.length - 1 ? item.expireTime : undefined,
          createdAt: index === parts.length - 1 ? item.createdAt : undefined,
          updatedAt: index === parts.length - 1 ? item.updatedAt : undefined,
          content: index === parts.length - 1 ? item.content : undefined,
          canView: index === parts.length - 1 ? item.canView : undefined,
          children: []
        };
        map.set(currentPath, node);
        currentLevel.push(node);
      }
      
      currentLevel = node.children;
    });
  });
  
  return tree;
});

// 处理节点点击
const handleNodeClick = (data) => {
  // 只有叶子节点（有size属性的节点）才可以查看详情
  if (data.size) {
    viewCache(data);
  }
};

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

.cache-tree {
  margin-bottom: var(--spacing-lg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
  min-width: 900px;
  width: 100%;
}

.tree-node-content {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-sm);
  gap: var(--spacing-sm);
  width: 100%;
  min-height: 90px;
  box-sizing: border-box;
}

.node-header {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: var(--spacing-xs);
  width: 100%;
  margin-bottom: var(--spacing-xs);
  min-height: 24px;
}

.node-key {
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 200px;
}

.node-comment {
  color: var(--text-muted);
  font-size: var(--font-size-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 150px;
}

.node-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-xs);
  padding-top: var(--spacing-xs);
  border-top: 1px solid var(--border-color);
  flex-wrap: nowrap;
  width: 100%;
  min-height: 40px;
  align-content: center;
  box-sizing: border-box;
}

.node-size {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  min-width: 80px;
}

.node-hits {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  min-width: 80px;
}

.node-actions {
  margin-left: auto;
  display: flex;
  gap: var(--spacing-xs);
  flex-shrink: 0;
  min-width: 180px;
  justify-content: flex-end;
}

/* 确保树节点有足够的宽度 */
.el-tree {
  width: 100%;
  min-width: 900px;
  overflow-x: auto;
}

.el-tree-node {
  min-width: 100%;
}

.el-tree-node__content {
  width: 100%;
  min-height: 90px;
  padding: 0 !important;
}

/* 调整树节点的缩进，确保内容有足够空间 */
.el-tree-node.is-expanded > .el-tree-node__children {
  padding-left: 20px;
}

.el-tree-node__children {
  padding-left: 20px;
}

/* 调整操作按钮大小 */
.node-actions .el-button {
  font-size: 11px;
  padding: 3px 6px;
  min-width: 45px;
  height: 24px;
  line-height: 16px;
}

/* 确保标签不会被压缩 */
.node-meta .el-tag {
  flex-shrink: 0;
  font-size: 11px;
  padding: 0 8px;
  height: 20px;
  line-height: 18px;
}

/* 确保缓存内容区域有足够的宽度 */
.cache-content {
  margin-top: var(--spacing-lg);
  width: 100%;
  overflow-x: auto;
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

  .node-meta {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-xs);
  }

  .node-actions {
    margin-left: 0;
    width: 100%;
    justify-content: flex-start;
  }
}
</style>