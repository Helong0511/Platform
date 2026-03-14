<!--
Offer 列表组件
从 OfferManagement.vue 拆分
负责 Offer 数据的列表展示、筛选、分页
-->
<template>
  <div class="offer-list-container">
    <!-- 筛选表单 -->
    <el-card class="filter-card">
      <el-form :model="filterForm" :inline="true" size="default">
        <el-form-item label="搜索">
          <el-input
            v-model="filterForm.search"
            placeholder="搜索 Offer 名称"
            clearable
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="广告主">
          <el-select
            v-model="filterForm.advertiser_id"
            placeholder="全部"
            clearable
            class="w-200"
          >
            <el-option
              v-for="adv in advertisers"
              :key="adv.id"
              :label="adv.advertiser_name"
              :value="adv.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select
            v-model="filterForm.status"
            placeholder="全部"
            clearable
            class="w-200"
          >
            <el-option label="激活" value="active" />
            <el-option label="暂停" value="paused" />
            <el-option label="归档" value="archived" />
          </el-select>
        </el-form-item>

        <el-form-item label="国家">
          <el-input
            v-model="filterForm.country"
            placeholder="国家代码"
            clearable
            class="w-150"
            @keyup.enter="handleSearch"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>
            搜索
          </el-button>
          <el-button @click="handleReset">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="table-card">
      <div class="table-header">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建 Offer
        </el-button>
        <el-button @click="handleExport">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="offers"
        border
        stripe
        class="offer-table"
        @sort-change="handleSortChange"
      >
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="offer_name" label="Offer 名称" min-width="200" />
        <el-table-column prop="advertiser_name" label="广告主" width="150" />
        <el-table-column prop="country" label="国家" width="100" />
        <el-table-column prop="price" label="价格" width="100" sortable>
          <template #default="{ row }">
            <span>${{ row.price?.toFixed(2) || '0.00' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleEdit(row)">
              编辑
            </el-button>
            <el-button link type="primary" @click="handleView(row)">
              查看
            </el-button>
            <el-button link type="danger" @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Search, Refresh, Plus, Download } from '@element-plus/icons-vue';
import { getOffers, deleteOffer } from '@/api/offer';
import { getAdvertisers } from '@/api/advertiser';

// 筛选表单
const filterForm = reactive({
  search: '',
  advertiser_id: null,
  status: '',
  country: ''
});

// 分页
const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
});

// 数据
const offers = ref([]);
const advertisers = ref([]);
const loading = ref(false);

// 加载数据
const loadOffers = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size,
      ...filterForm
    };
    
    const response = await getOffers(params);
    offers.value = response.data.data || [];
    pagination.total = response.data.total || 0;
  } catch (error) {
    ElMessage.error('加载 Offer 列表失败');
  } finally {
    loading.value = false;
  }
};

// 加载广告主列表
const loadAdvertisers = async () => {
  try {
    const response = await getAdvertisers();
    advertisers.value = response.data.data || [];
  } catch (error) {
    console.error('加载广告主列表失败:', error);
  }
};

// 搜索
const handleSearch = () => {
  pagination.page = 1;
  loadOffers();
};

// 重置
const handleReset = () => {
  filterForm.search = '';
  filterForm.advertiser_id = null;
  filterForm.status = '';
  filterForm.country = '';
  pagination.page = 1;
  loadOffers();
};

// 分页
const handlePageChange = (page) => {
  pagination.page = page;
  loadOffers();
};

const handleSizeChange = (size) => {
  pagination.page_size = size;
  pagination.page = 1;
  loadOffers();
};

// 排序
const handleSortChange = ({ prop, order }) => {
  // TODO: 实现服务端排序
  console.log('排序:', prop, order);
};

// 操作
const handleCreate = () => {
  // TODO: 打开创建对话框
  ElMessage.info('打开创建对话框');
};

const handleEdit = (row) => {
  // TODO: 打开编辑对话框
  ElMessage.info(`编辑 Offer: ${row.offer_name}`);
};

const handleView = (row) => {
  // TODO: 打开详情对话框
  ElMessage.info(`查看 Offer: ${row.offer_name}`);
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 Offer "${row.offer_name}" 吗？`,
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );
    
    await deleteOffer(row.id);
    ElMessage.success('删除成功');
    loadOffers();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

const handleExport = () => {
  // TODO: 实现导出功能
  ElMessage.info('导出功能开发中');
};

// 辅助函数
const getStatusType = (status) => {
  const types = {
    active: 'success',
    paused: 'warning',
    archived: 'info'
  };
  return types[status] || 'info';
};

const getStatusText = (status) => {
  const texts = {
    active: '激活',
    paused: '暂停',
    archived: '归档'
  };
  return texts[status] || status;
};

// 初始化
onMounted(() => {
  loadOffers();
  loadAdvertisers();
});

// 导出给父组件使用
defineExpose({
  refresh: loadOffers
});
</script>

<style scoped>
.offer-list-container {
  padding: 20px;
}

.filter-card {
  margin-bottom: 20px;
}

.w-200 {
  width: 200px;
}

.w-150 {
  width: 150px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
