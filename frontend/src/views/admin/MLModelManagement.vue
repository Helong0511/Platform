<template>
  <div class="ml-model-management">

    <!-- 功能区域 -->
    <el-row :gutter="20" class="main-row">
      <!-- 列名映射训练和验证 -->
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>
            <div class="section-header">
              <el-icon :size="16"><Upload /></el-icon>
              <span>训练导入</span>
            </div>
          </template>

          <div class="train-section">
            <!-- Excel文件选择按钮 -->
            <div class="file-select-wrapper">
              <el-button 
                type="primary" 
                :icon="Upload"
                @click="handleSelectFile"
                :disabled="importing"
              >
                选择Excel文件
              </el-button>
              <input
                ref="fileInputRef"
                type="file"
                accept=".xlsx,.xls"
                style="display: none"
                @change="handleFileInputChange"
              />
              <span v-if="trainFileList.length > 0" class="file-name-hint">
                已选择：{{ trainFileList[0]?.name || '未知文件' }}
              </span>
            </div>

            <!-- 已选择文件提示 -->
            <div v-if="trainFileList.length > 0 && excelColumns.length === 0" class="file-info">
              <el-alert type="info" :closable="false" class="file-info-alert">
                <template #title>
                  <div>
                    <strong>已选择文件：</strong>{{ trainFileList[0]?.name || '未知文件' }}
                    <br />
                    <span class="parsing-hint">正在解析列名...</span>
                  </div>
                </template>
              </el-alert>
            </div>

            <!-- 列名映射选择 -->
            <div v-if="excelColumns.length > 0" class="mapping-section">
              <el-divider>选择列名映射</el-divider>
              <el-table :data="mappingTableData" border stripe style="width: 100%">
                <el-table-column prop="fieldName" label="必需字段" width="140" align="center">
                  <template #default="scope">
                    <el-tag type="warning" size="small">{{ scope.row.fieldName }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="fieldKey" label="字段标识" width="120" align="center">
                  <template #default="scope">
                    <span class="field-key-text">{{ scope.row.fieldKey }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="选择Excel列" min-width="200">
                  <template #default="scope">
                    <el-select
                      v-model="scope.row.selectedColumn"
                      placeholder="请选择Excel列"
                      popper-class="select-dropdown"
                      :teleported="true"
                      style="width: 100%"
                      @change="handleMappingChange"
                    >
                      <el-option
                        v-for="col in excelColumns"
                        :key="col"
                        :label="col"
                        :value="col"
                      />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="推荐" width="100" align="center">
                  <template #default="scope">
                    <el-tag
                      v-if="scope.row.recommended"
                      type="success"
                      size="small"
                    >
                      推荐
                    </el-tag>
                    <span v-else class="field-key-text">-</span>
                  </template>
                </el-table-column>
              </el-table>

              <el-row :gutter="10" class="button-row">
                <el-col :span="12">
                  <el-button
                    type="primary"
                    :loading="savingMapping"
                    :disabled="!isMappingComplete"
                    @click="handleSaveMapping"
                    style="width: 100%;"
                  >
                    <el-icon :size="16"><Check /></el-icon>
                    {{ savingMapping ? '保存中...' : '保存映射规则' }}
                  </el-button>
                </el-col>
                <el-col :span="12">
                  <el-button
                    type="success"
                    :loading="validating"
                    :disabled="!trainSelectedFile || excelColumns.length === 0"
                    @click="handleValidateCurrentMapping"
                    style="width: 100%;"
                  >
                    <el-icon :size="16"><Search /></el-icon>
                    {{ validating ? '验证中...' : '验证当前映射' }}
                  </el-button>
                </el-col>
              </el-row>

              <el-alert
                v-if="!isMappingComplete"
                type="warning"
                :closable="false"
                class="warning-alert"
              >
                <template #title>
                  请为所有必需字段选择对应的Excel列
                </template>
              </el-alert>

              <!-- 验证结果 -->
              <div v-if="validationResult" class="validation-result">
                <el-divider>验证结果</el-divider>
                
                <!-- 映射完成度 -->
                <el-card 
                  class="mapping-card" 
                  :class="validationResult.column_mapping.mapping_complete ? 'mapping-complete' : 'mapping-incomplete'"
                >
                  <div class="mapping-status">
                    <el-icon :size="40" :color="validationResult.column_mapping.mapping_complete ? '#67c23a' : '#e6a23c'">
                      <component :is="validationResult.column_mapping.mapping_complete ? CircleCheck : Warning" />
                    </el-icon>
                    <div class="status-text">
                      <div class="status-title">
                        {{ validationResult.column_mapping.mapping_complete ? '✅ 所有字段已映射' : '⚠️ 部分字段缺失' }}
                      </div>
                      <div class="status-detail">
                        已映射 {{ validationResult.column_mapping.mapped_count }}/{{ validationResult.column_mapping.required_count }} 个字段
                      </div>
                    </div>
                  </div>
                </el-card>

                <!-- 列名映射详情 -->
                <el-card class="result-card">
                  <template #header>
                    <span>列名映射详情</span>
                  </template>
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item
                      v-for="(dbCol, excelCol) in validationResult.column_mapping.mapping"
                      :key="excelCol"
                      :label="excelCol"
                    >
                      <el-tag type="success" size="small">
                        {{ getFieldName(dbCol) }}
                      </el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item
                      v-if="validationResult.column_mapping.missing_columns.length > 0"
                      label="缺失字段"
                    >
                      <el-tag 
                        type="warning" 
                        v-for="col in validationResult.column_mapping.missing_columns" 
                        :key="col" 
                        class="tag-margin"
                      >
                        {{ col }}
                      </el-tag>
                    </el-descriptions-item>
                  </el-descriptions>
                </el-card>

                <!-- Excel原始列名 -->
                <el-card class="result-card">
                  <template #header>
                    <span>Excel原始列名</span>
                  </template>
                  <div class="excel-columns">
                    <el-tag
                      v-for="col in validationResult.excel_columns"
                      :key="col"
                      class="column-tag"
                      :type="validationResult.column_mapping.mapping[col] ? 'success' : 'info'"
                    >
                      {{ col }}
                    </el-tag>
                  </div>
                </el-card>

                <!-- 建议 -->
                <el-card class="result-card">
                  <template #header>
                    <span>智能建议</span>
                  </template>
                  <ul class="recommendations">
                    <li v-for="(rec, index) in validationResult.recommendations" :key="index">
                      {{ rec }}
                    </li>
                  </ul>
                </el-card>
              </div>
            </div>

            <!-- 预览数据 -->
            <div v-if="previewData" class="preview-section" style="margin-top: 20px;">
              <el-divider>预览数据</el-divider>
              <el-card>
                <template #header>
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>数据预览（共 {{ previewData.total_rows }} 行，显示前 {{ previewData.preview_rows }} 行）</span>
                  </div>
                </template>
                <div v-if="!previewData.preview_data || previewData.preview_data.length === 0" class="empty-preview">
                  <el-icon :size="48" class="empty-icon"><Document /></el-icon>
                  <div>暂无预览数据</div>
                </div>
                <el-table 
                  v-else
                  :data="previewData.preview_data" 
                  border 
                  stripe 
                  style="width: 100%"
                  max-height="400"
                  empty-text="暂无数据"
                >
                  <el-table-column 
                    v-for="fieldKey in orderedPreviewFields" 
                    :key="fieldKey"
                    :prop="fieldKey"
                    :label="getPreviewFieldLabel(fieldKey)"
                    min-width="120"
                  >
                    <template #default="scope">
                      <span>{{ formatPreviewValue(scope.row[fieldKey]) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
            </div>

            <!-- 导入Excel按钮 -->
            <div v-if="previewData && previewData.mapping_complete" class="import-button-wrapper">
              <el-button
                type="success"
                size="large"
                :loading="importing"
                :icon="Upload"
                @click="handleImportExcel"
              >
                {{ importing ? '导入中...' : '导入Excel' }}
              </el-button>
            </div>

          </div>
        </el-card>
      </el-col>
    </el-row>

  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus';
import {
  Upload, Search, Refresh, Delete,
  CircleCheck, CircleClose, Document, Box, Warning, View, Check
} from '@element-plus/icons-vue';
import { validateExcelData, getModelStatus, parseExcelColumns, saveMapping, previewExcelData, importTrainingData } from '../../api/ml-model';
import { formatDateTime as formatDateTimeWithTimezone } from '../../utils/dateFormat';
import { extractErrorMessage, isErrorHandled } from '../../utils/api';
import { logger } from '../../utils/logger';

// 11个必需字段的中文名称（按显示顺序）
const requiredFields = {
  "date": "数据日期",
  "product_name": "产品名称",
  "request_count": "请求数",
  "match_count": "匹配数",
  "coverage_rate": "覆盖率",
  "display_count": "展示数",
  "display_rate": "展示率",
  "click_count": "点击数",
  "click_rate": "点击率",
  "ecpm_before_deduct": "eCPM",
  "revenue_before_deduct": "收益"
};

// 预览字段的显示顺序（固定顺序）
const previewFieldOrder = [
  "date",
  "product_name",
  "request_count",
  "match_count",
  "coverage_rate",
  "display_count",
  "display_rate",
  "click_count",
  "click_rate",
  "ecpm_before_deduct",
  "revenue_before_deduct"
];

// 状态管理
const modelStatus = ref({
  has_user_mapping: false,
  mapping_rules_exists: false,
  mapped_count: 0,
  total_fields: 11
});

const validating = ref(false);
const validationResult = ref(null);

// 映射相关
const trainFileList = ref([]);
const trainSelectedFile = ref(null);
const excelColumns = ref([]);
const recommendedMapping = ref({});
const mappingTableData = ref([]);
const savingMapping = ref(false);
const uploadKey = ref(0); // 用于强制重新渲染 el-upload 组件
const fileInputRef = ref(null);
const previewData = ref(null);
const previewLoading = ref(false);
const importing = ref(false);

// 计算属性：映射是否完整
const isMappingComplete = computed(() => {
  return mappingTableData.value.every(row => row.selectedColumn && row.selectedColumn.trim() !== '');
});

// 计算属性：按顺序排列的预览字段
const orderedPreviewFields = computed(() => {
  if (!previewData.value || !previewData.value.field_info) {
    return [];
  }
  // 按照固定顺序过滤出存在的字段
  return previewFieldOrder.filter(fieldKey => 
    previewData.value.field_info && previewData.value.field_info[fieldKey]
  );
});

// 获取预览字段的标签
const getPreviewFieldLabel = (fieldKey) => {
  if (previewData.value && previewData.value.field_info && previewData.value.field_info[fieldKey]) {
    return previewData.value.field_info[fieldKey].name;
  }
  return requiredFields[fieldKey] || fieldKey;
};

// 加载映射规则状态
const loadModelStatus = async () => {
  try {
    const status = await getModelStatus();
    modelStatus.value = {
      has_user_mapping: status.has_user_mapping || false,
      mapping_rules_exists: status.mapping_rules_exists || false,
      mapped_count: status.mapped_count || 0,
      total_fields: status.total_fields || 11
    };
  } catch (error) {
    // 错误已在ElMessage中显示，不需要额外日志
  }
};

// 清除文件相关状态
const clearFileState = () => {
  trainSelectedFile.value = null;
  trainFileList.value = [];
  excelColumns.value = [];
  mappingTableData.value = [];
  recommendedMapping.value = {};
  validationResult.value = null;
  previewData.value = null;
  // 增加 key 值以强制重新渲染 el-upload 组件
  uploadKey.value += 1;
  // 重置文件输入
  if (fileInputRef.value) {
    fileInputRef.value.value = '';
  }
};

// 选择文件按钮点击
const handleSelectFile = () => {
  if (fileInputRef.value) {
    fileInputRef.value.click();
  }
};

// 文件输入变化
const handleFileInputChange = (event) => {
  const file = event.target.files?.[0];
  if (file) {
    handleTrainFileChange({ raw: file, name: file.name }, [{ raw: file, name: file.name }]);
  }
};

// 文件选择超出限制（替换文件）
const handleTrainFileExceed = (files, fileList) => {
  // 当选择新文件时，el-upload会自动替换文件
  // fileList 已经包含了新文件，只需要处理新文件
  if (files.length > 0 && files[0]) {
    // 直接调用 handleTrainFileChange，fileList 已经是最新的（包含新文件）
    handleTrainFileChange(files[0], fileList);
  }
};

// 文件移除
const handleTrainFileRemove = (file, fileList) => {
  // 清除所有相关状态
  clearFileState();
};

// 加载预览数据
const loadPreviewData = async () => {
  if (!trainSelectedFile.value) {
    return;
  }

  try {
    previewLoading.value = true;
    const result = await previewExcelData(trainSelectedFile.value, 10);
    previewData.value = result;
    
    // 检查数据是否有效
    if (!result.preview_data || result.preview_data.length === 0) {
      ElMessage.warning('预览数据为空，请检查Excel文件内容');
    }
    if (!result.field_info || Object.keys(result.field_info).length === 0) {
      ElMessage.warning('字段信息为空，请检查映射规则');
    }
  } catch (error) {
    // 错误已在API层处理
    previewData.value = null;
    // 检查错误是否已被处理，避免重复提示
    if (!isErrorHandled(error)) {
      logger.error('加载预览数据失败:', error);
    }
  } finally {
    previewLoading.value = false;
  }
};

// 训练文件选择
const handleTrainFileChange = async (file, fileList) => {
  // 处理文件移除的情况（当fileList为空或file为null时）
  if (!file || !file.raw) {
    // 如果fileList还有文件，说明可能是正在替换文件，不立即清除
    if (!fileList || fileList.length === 0) {
      clearFileState();
    }
    return;
  }
  
  // 验证文件类型
  const fileName = file.name || '';
  const isValidType = fileName.endsWith('.xlsx') || fileName.endsWith('.xls');
  if (!isValidType) {
    ElMessage.error('请上传 .xlsx 或 .xls 格式的Excel文件');
    // 清除无效文件
    clearFileState();
    return;
  }
  
  // 如果已有文件且是新文件（替换文件的情况）
  const isReplacing = trainFileList.value.length > 0 && 
                       trainFileList.value[0]?.name !== file.name;
  
  if (isReplacing) {
    // 清除旧文件的状态（但保留fileList，让el-upload正常显示新文件）
    trainSelectedFile.value = null;
    excelColumns.value = [];
    mappingTableData.value = [];
    recommendedMapping.value = {};
    validationResult.value = null;
    // 注意：不清除 trainFileList 和 uploadKey，让 el-upload 正常处理文件替换
  }
  
  // 设置新文件
  trainSelectedFile.value = file.raw;
  // 确保使用最新的fileList（el-upload已经处理好了）
  trainFileList.value = Array.isArray(fileList) ? fileList : [file];
  
  try {
    // 先刷新映射规则状态，确保使用最新的训练数据
    await loadModelStatus();
    
    // 解析Excel列名（后端会自动使用最新的映射规则进行智能识别）
    const result = await parseExcelColumns(file.raw);
    excelColumns.value = result.excel_columns || [];
    recommendedMapping.value = result.recommended_mapping || {};
    
    // 构建映射表格数据，自动应用识别结果
    const requiredFieldsKeys = Object.keys(requiredFields);
    mappingTableData.value = requiredFieldsKeys.map(fieldKey => {
      const fieldName = requiredFields[fieldKey];
      // 查找推荐映射中是否有这个字段（推荐映射已使用最新的训练数据）
      const recommendedCol = Object.keys(recommendedMapping.value).find(
        col => recommendedMapping.value[col] === fieldKey
      );
      
      return {
        fieldKey,
        fieldName,
        selectedColumn: recommendedCol || '',
        recommended: !!recommendedCol
      };
    });
    
    // 统计自动识别的结果
    const autoMatchedCount = mappingTableData.value.filter(row => row.selectedColumn).length;
    const totalFields = requiredFieldsKeys.length;
    
    if (autoMatchedCount > 0) {
      ElMessage.success(
        `成功解析Excel，共 ${excelColumns.value.length} 列。已自动识别 ${autoMatchedCount}/${totalFields} 个字段映射${autoMatchedCount === totalFields ? '（全部匹配）' : '，请补充剩余字段'}`
      );
      
      // 如果映射完全成功，自动加载预览数据
      if (autoMatchedCount === totalFields) {
        await loadPreviewData();
      }
    } else {
      ElMessage.success(`成功解析Excel，共 ${excelColumns.value.length} 列，请手动选择字段映射`);
    }
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
    // 发生错误时，清除文件状态
    clearFileState();
  }
};

// 映射变化处理
const handleMappingChange = () => {
  // 可以在这里添加验证逻辑
};

// 保存映射规则
const handleSaveMapping = async () => {
  if (!isMappingComplete.value) {
    ElMessage.warning('请为所有必需字段选择对应的Excel列');
    return;
  }

  try {
    // 构建映射对象（规范化Excel列名，去除前后空格）
    const mapping = {};
    const excelColsSeen = new Set(); // 用于检测重复的Excel列名（去除空格后）
    
    mappingTableData.value.forEach(row => {
      if (row.selectedColumn && row.selectedColumn.trim()) {
        const normalizedCol = row.selectedColumn.trim();
        
        // 前端验证：检查重复的Excel列名（去除空格后）
        if (excelColsSeen.has(normalizedCol.toLowerCase())) {
          ElMessage.error(`Excel列名 "${row.selectedColumn}" 与其他列名重复（去除空格后）`);
          return;
        }
        excelColsSeen.add(normalizedCol.toLowerCase());
        
        mapping[normalizedCol] = row.fieldKey;
      }
    });

    // 验证映射完整性
    const requiredFieldsKeys = Object.keys(requiredFields);
    const mappedFields = new Set(Object.values(mapping));
    const missingFields = requiredFieldsKeys.filter(field => !mappedFields.has(field));
    
    if (missingFields.length > 0) {
      const missingNames = missingFields.map(field => requiredFields[field]);
      ElMessage.error(`缺少必需字段映射: ${missingNames.join(', ')}`);
      return;
    }
    
    // 前端验证：检查是否所有字段都被映射（防止一个字段被映射多次）
    if (mappedFields.size !== requiredFieldsKeys.length) {
      // 检查是否有重复映射的字段
      const fieldCounts = {};
      Object.values(mapping).forEach(field => {
        fieldCounts[field] = (fieldCounts[field] || 0) + 1;
      });
      const duplicateFields = Object.entries(fieldCounts)
        .filter(([field, count]) => count > 1)
        .map(([field]) => requiredFields[field] || field);
      
      if (duplicateFields.length > 0) {
        ElMessage.error(`字段重复映射: ${duplicateFields.join(', ')}。每个字段只能被映射一次。`);
        return;
      }
    }

    savingMapping.value = true;
    const result = await saveMapping(mapping);
    
    // 显示详细的保存结果
    const message = result.message || '映射规则保存成功！';
    if (result.new_mappings || result.updated_mappings) {
      ElMessage.success(
        `${message}（总映射: ${result.mapped_count}，新增: ${result.new_mappings || 0}，更新: ${result.updated_mappings || 0}）`
      );
    } else {
      ElMessage.success(message);
    }
    
    // 刷新状态
    await loadModelStatus();
    
    // 保存映射规则后，加载预览数据
    if (trainSelectedFile.value) {
      await loadPreviewData();
    }
  } catch (error) {
    // 错误信息已经在API层处理
    // 错误已在ElMessage中显示，不需要额外日志
  } finally {
    savingMapping.value = false;
  }
};

// 验证当前映射（使用训练文件）
const handleValidateCurrentMapping = async () => {
  if (!trainSelectedFile.value) {
    ElMessage.warning('请先选择Excel文件');
    return;
  }

  try {
    validating.value = true;
    validationResult.value = null; // 清除之前的验证结果
    const result = await validateExcelData(trainSelectedFile.value);
    validationResult.value = result;
    ElMessage.success('列名映射验证完成！');
  } catch (error) {
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    validating.value = false;
  }
};


// 刷新状态
const refreshModelStatus = async () => {
  await loadModelStatus();
  ElMessage.success('状态已刷新');
};

// 获取字段中文名称
const getFieldName = (field) => {
  return requiredFields[field] || field;
};

// 格式化值
const formatValue = (value) => {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') {
    return value.toFixed(2);
  }
  return String(value);
};

// 格式化预览值
const formatPreviewValue = (value) => {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') {
    // 如果是整数，不显示小数
    if (Number.isInteger(value)) {
      return value.toString();
    }
    // 如果是小数，保留2位小数
    return value.toFixed(2);
  }
  return String(value);
};

// 导入Excel
const handleImportExcel = async () => {
  if (!trainSelectedFile.value) {
    ElMessage.warning('请先选择Excel文件');
    return;
  }

  try {
    importing.value = true;
    const result = await importTrainingData(trainSelectedFile.value);
    
    // 构建详细的导入结果消息
    const messages = [];
    if (result.imported_rows > 0) {
      messages.push(`成功导入 ${result.imported_rows} 条数据`);
      if (result.new_rows > 0) {
        messages.push(`新增 ${result.new_rows} 条`);
      }
      if (result.updated_rows > 0) {
        messages.push(`更新 ${result.updated_rows} 条`);
      }
    }
    if (result.failed_rows > 0) {
      messages.push(`失败 ${result.failed_rows} 条`);
    }
    if (result.duplicate_rows > 0) {
      messages.push(`跳过重复 ${result.duplicate_rows} 条`);
    }
    
    const message = messages.length > 0 ? messages.join('，') : (result.message || '导入完成');
    
    if (result.failed_rows > 0) {
      ElMessage.warning(message);
    } else {
      ElMessage.success(message);
    }
    
    // 如果有错误详情，显示详细信息
    if (result.error_details && result.error_details.length > 0) {
      // 错误详情已在通知中显示
      // 使用 ElNotification 显示详细的错误信息
      // 将错误信息转换为 HTML 格式，使用 <br> 换行
      const errorMessage = result.error_details.join('<br>');
      ElNotification({
        title: `导入失败 ${result.failed_rows} 条数据`,
        message: errorMessage,
        type: 'error',
        duration: 10000,  // 显示10秒，让用户有足够时间查看
        dangerouslyUseHTMLString: true,  // 允许 HTML 格式
        showClose: true
      });
    }
    
    // 导入成功后，清除文件状态以便重新选择
    clearFileState();
  } catch (error) {
    // 如果错误未被处理，显示错误消息
    if (!isErrorHandled(error)) {
      const errorMsg = extractErrorMessage(error);
      ElMessage.error(errorMsg);
    }
  } finally {
    importing.value = false;
  }
};

// 格式化日期时间（使用统一的时区格式化函数）
const formatDateTime = (dateTimeStr) => {
  return formatDateTimeWithTimezone(dateTimeStr);
};

// 组件挂载时加载状态
onMounted(() => {
  loadModelStatus();
});
</script>

<style scoped>
.ml-model-management {
  width: 100%;
  padding: 0;
}

.header-card {
  margin-bottom: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.header-card :deep(.el-card__body) {
  padding: var(--spacing-xl);
}

.card-header h2 {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.subtitle {
  margin: var(--spacing-sm) 0 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-base);
}

.status-card {
  height: 100%;
}

.main-row {
  margin-top: var(--spacing-xl);
}

.file-select-wrapper {
  margin-bottom: var(--spacing-xl);
}

.file-name-hint {
  margin-left: var(--spacing-md);
  color: var(--text-regular);
  font-size: var(--font-size-base);
}

.file-info-alert {
  margin-bottom: var(--spacing-xl);
}

.parsing-hint {
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.field-key-text {
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.button-row {
  margin-top: var(--spacing-xl);
}

.warning-alert {
  margin-top: var(--spacing-md);
}

.result-card {
  margin-top: var(--spacing-md);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.tag-margin {
  margin-right: var(--spacing-xs);
}

.column-tag {
  margin: var(--spacing-xs);
}

.empty-preview {
  text-align: center;
  padding: var(--spacing-xxxxl);
  color: var(--text-secondary);
}

.empty-icon {
  margin-bottom: var(--spacing-md);
}

.import-button-wrapper {
  margin-top: var(--spacing-xl);
  text-align: center;
}

.status-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.status-info {
  flex: 1;
}

.status-label {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-xs);
}

.status-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.train-section,
.validate-section {
  min-height: 400px;
}

.form-hint {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

.train-info {
  margin-top: var(--spacing-md);
}

.validation-result {
  margin-top: var(--spacing-xl);
}

.mapping-card {
  text-align: center;
  padding: var(--spacing-xl);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-light);
}

.mapping-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
}

.status-text {
  text-align: center;
}

.status-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--spacing-xs);
}

.status-detail {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}

.mapping-complete .status-title {
  color: var(--success-color);
}

.mapping-incomplete .status-title {
  color: var(--warning-color);
}

.excel-columns {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.recommendations {
  margin: 0;
  padding-left: var(--spacing-xl);
}

.recommendations li {
  margin-bottom: var(--spacing-sm);
  line-height: var(--line-height-base);
}

.upload-demo {
  width: 100%;
}

:deep(.el-upload-dragger) {
  width: 100%;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .ml-model-management {
    padding: var(--spacing-md);
  }

  .header-card {
    margin-bottom: var(--spacing-md);
  }

  .header-card :deep(.el-card__body) {
    padding: var(--spacing-md);
  }

  .card-header h2 {
    font-size: var(--font-size-xl);
  }

  .section-header {
    font-size: var(--font-size-base);
  }

  .train-section,
  .validate-section {
    min-height: auto;
  }

  /* 按钮移动端优化 */
  .el-button {
    min-height: var(--touch-target-size);
    width: 100%;
    margin-bottom: var(--spacing-sm);
  }

  .el-row :deep(.el-col) {
    margin-bottom: var(--spacing-md);
  }

  /* 表格移动端优化 */
  .el-table {
    font-size: var(--font-size-sm);
    min-width: 600px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  /* 表格容器优化 */
  .el-card :deep(.el-card__body) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .el-table :deep(.el-table__header-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .el-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .el-table :deep(.el-table__cell) {
    padding: var(--spacing-xs) var(--spacing-sm);
    word-break: break-word;
  }

  .el-table :deep(.el-table__header th),
  .el-table :deep(.el-table__body td) {
    font-size: var(--font-size-xs);
    padding: var(--spacing-xs);
  }

  /* 选择器移动端优化 */
  .el-select {
    width: 100% !important;
  }

  .el-select :deep(.el-input__wrapper) {
    min-height: var(--touch-target-size);
  }

  /* 文件上传移动端优化 */
  .el-upload {
    width: 100%;
  }

  :deep(.el-upload-dragger) {
    padding: var(--spacing-md);
  }

  /* 状态卡片移动端优化 */
  .status-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .status-value {
    font-size: var(--font-size-base);
  }

  /* 映射卡片移动端优化 */
  .mapping-card {
    padding: var(--spacing-md);
  }

  .mapping-status {
    gap: var(--spacing-sm);
  }

  .status-title {
    font-size: var(--font-size-base);
  }

  .status-detail {
    font-size: var(--font-size-sm);
  }

  /* 按钮组移动端优化 */
  .el-row :deep(.el-col) {
    width: 100% !important;
    margin-bottom: var(--spacing-sm);
  }

  .el-row :deep(.el-col .el-button) {
    width: 100%;
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
