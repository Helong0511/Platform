<!--
  产品表单对话框
  @file components/admin/ProductFormDialog.vue
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="formTitle"
    :width="isMobile ? '95%' : '800px'"
    :close-on-click-modal="false"
    class="product-form-dialog"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="130px"
      class="product-form"
    >
      <el-form-item label="产品名称" prop="name" class="product-name-item">
        <div class="product-name-wrapper">
          <el-autocomplete
            v-model="formData.name"
            :fetch-suggestions="queryProductNames"
            placeholder="请选择或输入产品名称"
            clearable
            size="large"
            :loading="productNamesLoading"
            @select="emit('product-name-select', $event)"
            @blur="emit('product-name-blur')"
            @focus="emit('load-product-names')"
            class="product-name-select"
            ref="productNameSelectRef"
            value-key="value"
            :trigger-on-focus="true"
          >
            <template #prefix>
              <el-icon :size="20"><Box /></el-icon>
            </template>
            <template #default="{ item }">
              <div class="product-name-option">
                <el-icon :size="16"><Box /></el-icon>
                <span class="product-name-option-label">{{ item.label || item.value }}</span>
              </div>
            </template>
          </el-autocomplete>
          <div class="form-hint-container">
            <div class="form-hint" v-if="productNames.length > 0">
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>已找到 {{ productNames.length }} 个产品（包括关联管理员的客户和其他客户的产品），可选择或手动输入新名称。选择其他客户的产品时，将直接将该产品的客户归属改为当前客户。</span>
            </div>
            <div class="form-hint" v-else-if="productNamesLoading">
              <el-icon :size="16"><Loading /></el-icon>
              <span>正在加载产品名称...</span>
            </div>
            <div class="form-hint" v-else>
              <el-icon :size="16"><InfoFilled /></el-icon>
              <span>当前客户已有所有产品名称，或数据库中没有产品，请手动输入新名称</span>
            </div>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="eCPM减扣比例" prop="ecpm_deduct_ratio">
        <div>
          <el-input-number
            v-model="formData.ecpm_deduct_ratio"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="4"
            style="width: 100%;"
            placeholder="0.00-1.00"
            size="large"
            controls-position="right"
          ></el-input-number>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>范围：0.00 - 1.00（例如：0.10 表示 10%）</span>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="收益减扣比例" prop="revenue_deduct_ratio">
        <div>
          <el-input-number
            v-model="formData.revenue_deduct_ratio"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="4"
            style="width: 100%;"
            placeholder="0.00-1.00"
            size="large"
            controls-position="right"
          ></el-input-number>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>范围：0.00 - 1.00（例如：0.10 表示 10%）</span>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="状态" prop="is_active">
        <div class="status-wrapper">
          <el-switch
            v-model="formData.is_active"
            active-text="活跃"
            inactive-text="禁用"
            size="large"
            aria-label="切换产品状态"
          ></el-switch>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>状态不活跃的产品在广告数据中将不会显示</span>
          </div>
        </div>
      </el-form-item>

      <el-divider content-position="left">
        <el-icon :size="16"><Connection /></el-icon>
        <span style="margin-left: 8px;">下游 Postback 配置（可选）</span>
      </el-divider>

      <el-form-item label="下游 Postback URL" prop="downstream_postback_url">
        <div>
          <el-input
            v-model="formData.downstream_postback_url"
            placeholder="https://example.com/api/postback"
            clearable
            size="large"
          >
            <template #prefix>
              <el-icon :size="16"><Link /></el-icon>
            </template>
          </el-input>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>配置后，该产品的 postback 转化数据将自动转发到此 URL</span>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="请求方式" prop="downstream_postback_method">
        <div>
          <el-radio-group v-model="formData.downstream_postback_method" size="large">
            <el-radio label="GET">GET</el-radio>
            <el-radio label="POST">POST</el-radio>
          </el-radio-group>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>GET：数据作为 URL 参数传递；POST：数据作为 JSON body 传递</span>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="成功检查配置" prop="downstream_postback_success_check">
        <div>
          <el-input
            v-model="formData.downstream_postback_success_check"
            type="textarea"
            :rows="6"
            placeholder='JSON 格式配置，例如：{"type": "keyword", "success_keywords": ["OK"], "exact_match": true}'
            size="large"
          />
          <div class="form-hint">
            <el-link type="primary" @click="showSuccessCheckHelp = !showSuccessCheckHelp" style="font-size: 12px;">
              <el-icon><InfoFilled /></el-icon>
              {{ showSuccessCheckHelp ? '隐藏' : '查看' }}配置说明
            </el-link>
          </div>
          <el-collapse-transition>
            <div v-show="showSuccessCheckHelp" class="success-check-help">
              <div class="help-title">下游转发成功检查配置说明：</div>
              <div class="help-content">
                <div class="help-section">
                  <div class="help-section-title">1. HTTP 状态码检查（默认）</div>
                  <div class="help-example">
                    <div class="example-label">不填写配置：</div>
                    <div class="example-code">（留空）</div>
                    <div class="example-desc">默认 200-299 状态码为成功</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">只接受 200：</div>
                    <div class="example-code">{"type": "status_code", "success_status_codes": [200]}</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">接受多个状态码：</div>
                    <div class="example-code">{"type": "status_code", "success_status_codes": [200, 201, 202]}</div>
                  </div>
                </div>
                <div class="help-section">
                  <div class="help-section-title">2. 关键词检查</div>
                  <div class="help-example">
                    <div class="example-label">精确匹配 "OK"：</div>
                    <div class="example-code">{"type": "keyword", "success_keywords": ["OK"], "exact_match": true}</div>
                    <div class="example-desc">响应必须完全等于 "OK"（不区分大小写）</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">包含 "success"：</div>
                    <div class="example-code">{"type": "keyword", "success_keywords": ["success"]}</div>
                    <div class="example-desc">响应包含 "success" 即可（不区分大小写）</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">多个关键词：</div>
                    <div class="example-code">{"type": "keyword", "success_keywords": ["OK", "success", "200"]}</div>
                    <div class="example-desc">包含任意一个关键词即可</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">检查失败关键词：</div>
                    <div class="example-code">{"type": "keyword", "success_keywords": ["OK"], "failure_keywords": ["error", "fail"]}</div>
                    <div class="example-desc">包含失败关键词则失败（优先级更高）</div>
                  </div>
                </div>
                <div class="help-section">
                  <div class="help-section-title">3. JSON 检查</div>
                  <div class="help-example">
                    <div class="example-label">检查 status 字段：</div>
                    <div class="example-code">{"type": "json", "json_path": "status", "json_value": "ok"}</div>
                    <div class="example-desc">检查 JSON 响应中 status 字段的值是否为 "ok"</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">检查嵌套字段：</div>
                    <div class="example-code">{"type": "json", "json_path": "data.status", "json_value": "success"}</div>
                    <div class="example-desc">检查 data.status 字段的值</div>
                  </div>
                  <div class="help-example">
                    <div class="example-label">只检查字段存在：</div>
                    <div class="example-code">{"type": "json", "json_path": "status"}</div>
                    <div class="example-desc">只要 status 字段存在且不为空即可</div>
                  </div>
                </div>
                <div class="help-note">
                  <el-icon><Warning /></el-icon>
                  <strong>注意：</strong>配置必须是有效的 JSON 格式。如果不填写，默认使用 HTTP 状态码判断（200-299 为成功）。
                  <br>
                  详细配置示例请参考：<el-link type="primary" href="/docs/postback_success_check_examples.md" target="_blank">配置示例文档</el-link>
                </div>
              </div>
            </div>
          </el-collapse-transition>
        </div>
      </el-form-item>

      <el-divider content-position="left">
        <el-icon :size="16"><Bell /></el-icon>
        <span style="margin-left: 8px;">通知配置（可选）</span>
      </el-divider>

      <el-form-item label="通知地址" prop="notification_address">
        <div>
          <el-input
            v-model="formData.notification_address"
            placeholder="Telegram Chat ID、邮箱地址或 Webhook URL"
            clearable
            size="large"
          >
            <template #prefix>
              <el-icon :size="16"><Message /></el-icon>
            </template>
          </el-input>
          <div class="form-hint">
            <el-icon :size="16"><InfoFilled /></el-icon>
            <span>配置后，该产品的转化通知将发送到此地址。支持：Telegram Chat ID（纯数字）、邮箱地址（包含@）、Webhook URL（http://或https://开头）</span>
          </div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer-buttons">
        <el-button size="large" @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" size="large" @click="emit('save')" :loading="saving" :icon="saving ? undefined : Check">
          <span>保存</span>
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue';
import {
  ElDialog, ElButton, ElForm, ElFormItem, ElInput, ElInputNumber, ElSwitch,
  ElIcon, ElAutocomplete, ElDivider, ElRadioGroup, ElRadio, ElLink, ElCollapseTransition,
} from 'element-plus';
import {
  Box, InfoFilled, Check, Loading, Connection, Link, Bell, Message, Warning,
} from '@element-plus/icons-vue';

defineProps({
  modelValue: { type: Boolean, default: false },
  formTitle: { type: String, default: '添加产品' },
  isMobile: { type: Boolean, default: false },
  formData: { type: Object, required: true },
  formRules: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  productNames: { type: Array, default: () => [] },
  productNamesLoading: { type: Boolean, default: false },
  queryProductNames: { type: Function, required: true },
});

const emit = defineEmits([
  'update:modelValue',
  'save',
  'product-name-select',
  'product-name-blur',
  'load-product-names',
]);

const formRef = ref(null);
const productNameSelectRef = ref(null);
const showSuccessCheckHelp = ref(false);

defineExpose({ formRef, productNameSelectRef });
</script>
