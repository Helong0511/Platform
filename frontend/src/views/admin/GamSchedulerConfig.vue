<!--
  GAM 多账号配置页面

  管理「Google API获取数据」定时任务的账号、密钥路径与产品白名单。
  配置保存到服务端 config/gam_scheduler.json。
-->
<template>
  <div class="gam-scheduler-page">
    <div class="page-header">
      <div class="header-left">
        <h1>GAM 多账号配置</h1>
        <p class="header-description">
          配置 Google Ad Manager 拉数账号、报表类型与产品白名单，供定时任务「Google API获取数据」使用。
          每个账号可单独选择报表类型；白名单为空表示该账号全量拉取。
        </p>
        <div class="config-meta">
          <el-tag :type="configExists ? 'success' : 'warning'" size="small">
            {{ configExists ? '配置文件已存在' : '配置文件尚未创建' }}
          </el-tag>
          <span v-if="configPath" class="config-path">路径：{{ configPath }}</span>
        </div>
      </div>
      <div class="header-right">
        <el-button :icon="Plus" @click="addAccount">添加账号</el-button>
        <el-button type="primary" :loading="saving" :icon="Check" @click="handleSave">
          保存配置
        </el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="tips-alert">
      <template #title>
        <div>支持本地上传 Google 服务账号 JSON，将保存到服务端 <code>secrets/gam-网络ID.json</code>；也可手动填写已有路径。</div>
        <div>保存后立即写回 JSON 文件，无需重启后端；若配置文件不存在，保存时会自动创建。</div>
      </template>
    </el-alert>

    <el-card v-if="accounts.length" shadow="never" class="batch-card">
      <template #header>
        <div class="batch-header">
          <span>批量白名单操作</span>
          <el-switch
            v-if="hasMultipleAccounts()"
            :model-value="unifiedMode"
            active-text="统一白名单"
            inactive-text="分账号配置"
            @change="toggleUnifiedMode"
          />
        </div>
      </template>

      <div v-if="unifiedMode && hasMultipleAccounts()" class="unified-panel">
        <GamProductWhitelistEditor v-model="unifiedWhitelist" />
        <div class="batch-actions">
          <el-button type="primary" plain size="small" @click="applyUnifiedWhitelist">
            同步到全部账号
          </el-button>
        </div>
      </div>

      <template v-else>
        <div class="global-bulk">
          <div class="section-title">批量添加到全部账号</div>
          <el-input
            v-model="globalBulkText"
            type="textarea"
            :rows="3"
            placeholder="每行一个产品名称，将同时添加到所有 GAM 账号"
          />
          <el-button
            type="primary"
            plain
            size="small"
            :disabled="!globalBulkText.trim()"
            @click="globalBulkAddToAll"
          >
            添加到全部账号
          </el-button>
        </div>

        <div v-if="hasMultipleAccounts()" class="copy-row">
          <span class="copy-label">复制白名单：</span>
          <el-select v-model="copySourceKey" size="small" style="width: 180px;">
            <el-option
              v-for="account in accounts"
              :key="account.key"
              :label="account.key"
              :value="account.key"
            />
          </el-select>
          <el-button size="small" plain @click="copyWhitelistToAll">
            复制到全部账号
          </el-button>
        </div>
      </template>

      <div class="batch-actions">
        <el-button size="small" @click="clearAllWhitelists">全部清空（全量）</el-button>
      </div>
    </el-card>

    <div v-loading="loading" class="accounts-panel">
      <el-empty v-if="!accounts.length" description="暂无 GAM 账号，请点击右上角「添加账号」">
        <el-button type="primary" :icon="Plus" @click="addAccount">添加账号</el-button>
      </el-empty>

      <el-card
        v-for="(account, index) in accounts"
        :key="`${account.key}-${index}`"
        shadow="never"
        class="account-card"
      >
        <template #header>
          <div class="account-header">
            <div class="account-title-row">
              <span class="account-title">{{ account.key || `账号 ${index + 1}` }}</span>
              <el-tag v-if="account.network_code" type="info" size="small">
                网络 {{ account.network_code }}
              </el-tag>
              <el-tag v-if="account.fetch_all || !account.product_whitelist?.length" type="warning" size="small">
                全量拉取
              </el-tag>
              <el-tag
                v-if="account.credentials_json"
                :type="account.credentials_exists ? 'success' : 'danger'"
                size="small"
              >
                {{ account.credentials_exists ? '密钥文件存在' : '密钥文件缺失' }}
              </el-tag>
            </div>
            <el-button type="danger" plain size="small" @click="removeAccount(account)">
              删除账号
            </el-button>
          </div>
        </template>

        <el-form label-width="120px" class="account-form">
          <el-form-item label="账号标识 key" required>
            <el-input v-model="account.key" placeholder="如 x_browser、leadwin" maxlength="100" />
          </el-form-item>
          <el-form-item label="密钥文件" required>
            <div class="credentials-row">
              <el-input
                v-model="account.credentials_json"
                placeholder="secrets/gam-23347342743.json"
                maxlength="500"
                class="credentials-input"
              />
              <el-upload
                :show-file-list="false"
                accept=".json,application/json"
                :auto-upload="false"
                :disabled="account.credentialsUploading"
                @change="(file) => uploadCredentialsForAccount(account, file)"
              >
                <el-button :loading="account.credentialsUploading">本地上传</el-button>
              </el-upload>
            </div>
            <div class="field-hint">
              从 Windows 选择下载的 JSON 密钥即可；文件名建议为 <code>gam-网络ID.json</code>，否则上传时会提示填写网络 ID。
            </div>
          </el-form-item>
          <el-form-item label="应用名称">
            <el-input
              v-model="account.application_name"
              placeholder="Google API application_name"
              maxlength="200"
            />
          </el-form-item>
        </el-form>

        <GamReportTypesEditor
          v-model="account.report_keys"
          :options="account.report_type_options"
          :network-label="account.reportTypesNetworkLabel"
          :refreshing="account.reportTypesRefreshing"
          :can-refresh="Boolean(account.credentials_json?.trim())"
          class="report-types-section"
          @refresh="refreshReportTypesForAccount(account)"
        />

        <div v-if="!unifiedMode || !hasMultipleAccounts()" class="whitelist-section">
          <div class="section-title">产品白名单</div>
          <GamProductWhitelistEditor v-model="account.product_whitelist" />
          <div class="account-actions">
            <el-button size="small" @click="clearAccountWhitelist(account)">
              清空白名单（全量）
            </el-button>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { Plus, Check } from '@element-plus/icons-vue';
import GamProductWhitelistEditor from '../../components/admin/GamProductWhitelistEditor.vue';
import GamReportTypesEditor from '../../components/admin/GamReportTypesEditor.vue';
import { useGamSchedulerConfig } from '../../composables/useGamSchedulerConfig';

const {
  loading,
  saving,
  configPath,
  configExists,
  accounts,
  unifiedMode,
  unifiedWhitelist,
  globalBulkText,
  copySourceKey,
  hasMultipleAccounts,
  loadConfig,
  saveConfig,
  addAccount,
  removeAccount,
  clearAccountWhitelist,
  toggleUnifiedMode,
  applyUnifiedWhitelist,
  copyWhitelistToAll,
  globalBulkAddToAll,
  clearAllWhitelists,
  uploadCredentialsForAccount,
  refreshReportTypesForAccount,
} = useGamSchedulerConfig();

const handleSave = async () => {
  await saveConfig();
};

onMounted(() => {
  loadConfig();
});
</script>

<style scoped>
.gam-scheduler-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.header-left h1 {
  margin: 0 0 8px;
  font-size: 22px;
}

.header-description {
  margin: 0 0 8px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.config-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.config-path {
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}

.header-right {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tips-alert {
  margin-bottom: 0;
}

.batch-card,
.account-card {
  border: 1px solid var(--border-lighter);
}

.report-types-section {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px dashed var(--border-lighter);
}

.batch-header,
.account-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.account-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.account-title {
  font-weight: 600;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.batch-actions,
.account-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.global-bulk,
.unified-panel,
.copy-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.copy-row {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
}

.copy-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.accounts-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 120px;
}

.account-form {
  margin-bottom: 8px;
}

.credentials-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  width: 100%;
}

.credentials-input {
  flex: 1;
  min-width: 0;
}

.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.whitelist-section {
  border-top: 1px dashed var(--border-lighter);
  padding-top: 12px;
}

@media (max-width: 767px) {
  .header-right {
    width: 100%;
  }

  .header-right .el-button {
    flex: 1;
  }

  .credentials-row {
    flex-direction: column;
  }

  .credentials-row .el-button {
    width: 100%;
  }
}
</style>
