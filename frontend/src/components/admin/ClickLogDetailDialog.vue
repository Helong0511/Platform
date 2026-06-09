<!--
  点击日志详情弹窗
  @file components/admin/ClickLogDetailDialog.vue
-->
<template>
  <!-- 页面主模板 -->
<!-- 弹窗区域 -->
<!-- 弹窗 -->
    <el-dialog
    v-model="visible"
    title="点击记录详情"
    width="80%"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div v-if="detail" class="detail-content">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="Click ID" :span="2">
          <el-button 
            type="primary" 
            link 
            size="small"
            @click="copyToClipboard(detail.click_id)"
          >
            {{ detail.click_id }}
          </el-button>
        </el-descriptions-item>
        <el-descriptions-item label="访问时间">
          {{ detail.click_time ? formatDate(detail.click_time) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="IP地址">
          {{ detail.ip || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="国家">
          <el-tag v-if="detail.country" size="small" type="info">
            {{ detail.country }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="设备类型">
          <el-tag 
            v-if="detail.device_type" 
            :type="detail.device_type === 'mobile' ? 'success' : detail.device_type === 'tablet' ? 'warning' : 'info'"
            size="small"
          >
            {{ detail.device_type === 'mobile' ? '手机' : detail.device_type === 'tablet' ? '平板' : '桌面' }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="设备品牌">
          {{ detail.device_brand || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="设备型号">
          {{ detail.device_model || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="操作系统">
          {{ detail.os ? (detail.os + (detail.os_version ? ' ' + detail.os_version : '')) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="浏览器">
          {{ detail.browser ? (detail.browser + (detail.browser_version ? ' ' + detail.browser_version : '')) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="接受语言">
          {{ detail.accept_language || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="接受编码">
          {{ detail.accept_encoding || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="是否为机器人">
          <el-tag v-if="detail.is_bot" type="danger" size="small">是</el-tag>
          <el-tag v-else type="success" size="small">否</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Offer ID">
          <span v-if="detail.offer_id" class="text-primary">
            {{ detail.offer_id }}
          </span>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="Offer名称">
          {{ detail.offer_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="渠道ID">
          <span v-if="detail.publisher_id" class="text-primary">
            {{ detail.publisher_id }}
          </span>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="渠道名称">
          {{ detail.publisher_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="广告主ID">
          <span v-if="detail.advertiser_id" class="text-primary">
            {{ detail.advertiser_id }}
          </span>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="广告主名称">
          {{ detail.advertiser_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="短链接ID">
          <span v-if="detail.short_link_id" class="text-primary">
            {{ detail.short_link_id }}
          </span>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="短链接代码">
          <el-button 
            v-if="detail.short_code" 
            type="primary" 
            link 
            size="small"
            @click="copyToClipboard(detail.short_code)"
          >
            {{ detail.short_code }}
          </el-button>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="短链接标题">
          {{ detail.short_link_title || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="短链接URL" :span="2">
          <el-link 
            v-if="detail.short_link_url" 
            :href="detail.short_link_url" 
            target="_blank" 
            type="primary"
          >
            {{ detail.short_link_url }}
          </el-link>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="来源页面" :span="2">
          <el-link 
            v-if="detail.referer" 
            :href="detail.referer" 
            target="_blank" 
            type="primary"
          >
            {{ detail.referer }}
          </el-link>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="原始请求URL" :span="2">
          <el-link 
            v-if="detail.original_request_url" 
            :href="detail.original_request_url" 
            target="_blank" 
            type="primary"
          >
            {{ detail.original_request_url }}
          </el-link>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="最终跳转URL" :span="2">
          <el-link 
            v-if="detail.final_redirect_url" 
            :href="detail.final_redirect_url" 
            target="_blank" 
            type="primary"
          >
            {{ detail.final_redirect_url }}
          </el-link>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="User Agent" :span="2">
          <div class="text-wrap">{{ detail.user_agent || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="URL参数" :span="2" v-if="detail.url_params">
          <pre class="json-preview">{{ formatJSON(detail.url_params) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="请求头" :span="2" v-if="detail.all_headers">
          <pre class="json-preview">{{ formatJSON(detail.all_headers) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="转化ID">
          <el-tag v-if="detail.conversion_id" type="success" size="small">
            {{ detail.conversion_id }}
          </el-tag>
          <span v-else class="text-muted">-</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue';
import { formatDate } from '@/utils/dateFormat';
import { copyToClipboard } from '@/utils/clipboard';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  detail: {
    type: Object,
    default: null
  }
});

const emit = defineEmits(['update:modelValue']);

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const formatJSON = (value) => {
  if (!value) return '-';
  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2);
  }
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch (e) {
    return String(value);
  }
};

const handleClose = () => {
  visible.value = false;
};
</script>

<style scoped>
.detail-content {
  max-height: 70vh;
  overflow-y: auto;
}

.text-primary {
  color: var(--el-color-primary);
  font-weight: 500;
}

.text-muted {
  color: var(--el-text-color-secondary);
}

.text-wrap {
  word-break: break-all;
  white-space: pre-wrap;
}

.json-preview {
  background-color: var(--el-fill-color-lighter);
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 200px;
  overflow-y: auto;
  word-break: break-all;
  white-space: pre-wrap;
}
</style>
