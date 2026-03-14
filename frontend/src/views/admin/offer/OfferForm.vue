<!--
Offer 表单组件
从 OfferManagement.vue 拆分
负责 Offer 的创建和编辑
-->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑 Offer' : '新建 Offer'"
    width="600px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="120px"
      size="default"
    >
      <el-form-item label="Offer 名称" prop="offer_name">
        <el-input
          v-model="formData.offer_name"
          placeholder="请输入 Offer 名称"
          maxlength="100"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="广告主" prop="advertiser_id">
        <el-select
          v-model="formData.advertiser_id"
          placeholder="请选择广告主"
          class="w-100"
          filterable
        >
          <el-option
            v-for="adv in advertisers"
            :key="adv.id"
            :label="adv.advertiser_name"
            :value="adv.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="Offer ID" prop="advertiser_offer_id">
        <el-input
          v-model="formData.advertiser_offer_id"
          placeholder="上游系统的 Offer ID"
          maxlength="50"
        />
      </el-form-item>

      <el-form-item label="价格" prop="price">
        <el-input-number
          v-model="formData.price"
          :min="0"
          :max="999999"
          :precision="4"
          :step="0.01"
          class="w-100"
        />
      </el-form-item>

      <el-form-item label="国家" prop="country">
        <el-input
          v-model="formData.country"
          placeholder="国家代码（如 US, CN）"
          maxlength="10"
        />
      </el-form-item>

      <el-form-item label="状态" prop="status">
        <el-radio-group v-model="formData.status">
          <el-radio label="active">激活</el-radio>
          <el-radio label="paused">暂停</el-radio>
          <el-radio label="archived">归档</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="4"
          placeholder="Offer 描述（可选）"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="Postback URL" prop="postback_url">
        <el-input
          v-model="formData.postback_url"
          placeholder="Postback 回调地址"
          maxlength="500"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="submitLoading"
        @click="handleSubmit"
      >
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { createOffer, updateOffer, getOfferById } from '@/api/offer';
import { getAdvertisers } from '@/api/advertiser';

// Props
const props = defineProps({
  modelValue: Boolean,
  offerId: {
    type: Number,
    default: null
  }
});

// Emits
const emit = defineEmits(['update:modelValue', 'success']);

// 状态
const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const isEdit = computed(() => !!props.offerId);
const formRef = ref(null);
const submitLoading = ref(false);
const advertisers = ref([]);

// 表单数据
const formData = reactive({
  offer_name: '',
  advertiser_id: null,
  advertiser_offer_id: '',
  price: 0,
  country: '',
  status: 'active',
  description: '',
  postback_url: ''
});

// 验证规则
const rules = {
  offer_name: [
    { required: true, message: '请输入 Offer 名称', trigger: 'blur' },
    { min: 2, max: 100, message: '长度在 2-100 个字符', trigger: 'blur' }
  ],
  advertiser_id: [
    { required: true, message: '请选择广告主', trigger: 'change' }
  ],
  price: [
    { required: true, message: '请输入价格', trigger: 'blur' }
  ],
  status: [
    { required: true, message: '请选择状态', trigger: 'change' }
  ]
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

// 加载 Offer 详情
const loadOffer = async () => {
  if (!props.offerId) return;
  
  try {
    const response = await getOfferById(props.offerId);
    const data = response.data.data;
    
    Object.assign(formData, {
      offer_name: data.offer_name || '',
      advertiser_id: data.advertiser_id,
      advertiser_offer_id: data.advertiser_offer_id || '',
      price: data.price || 0,
      country: data.country || '',
      status: data.status || 'active',
      description: data.description || '',
      postback_url: data.postback_url || ''
    });
  } catch (error) {
    ElMessage.error('加载 Offer 详情失败');
  }
};

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return;
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    
    submitLoading.value = true;
    
    try {
      if (isEdit.value) {
        await updateOffer(props.offerId, formData);
        ElMessage.success('更新成功');
      } else {
        await createOffer(formData);
        ElMessage.success('创建成功');
      }
      
      dialogVisible.value = false;
      emit('success');
    } catch (error) {
      ElMessage.error(isEdit.value ? '更新失败' : '创建失败');
    } finally {
      submitLoading.value = false;
    }
  });
};

// 对话框关闭
const handleClosed = () => {
  formRef.value?.resetFields();
  Object.assign(formData, {
    offer_name: '',
    advertiser_id: null,
    advertiser_offer_id: '',
    price: 0,
    country: '',
    status: 'active',
    description: '',
    postback_url: ''
  });
};

// 监听 offerId 变化
watch(() => props.offerId, () => {
  if (props.offerId && dialogVisible.value) {
    loadOffer();
  }
});

// 初始化
onMounted(() => {
  loadAdvertisers();
});
</script>

<style scoped>
.w-100 {
  width: 100%;
}
</style>
