<!--
  产品通知配置弹窗（兼容入口，委托 NotificationConfigDialog）
  @file components/admin/ProductNotificationConfigDialog.vue
-->
<template>
  <NotificationConfigDialog
    v-model="visible"
    entity-type="product"
    :entity-id="productId"
    :entity-name="productName"
    @saved="emit('saved')"
  />
</template>

<script setup>
import { computed } from 'vue';
import NotificationConfigDialog from './NotificationConfigDialog.vue';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  productId: { type: Number, required: true },
  productName: { type: String, default: '产品' },
});

const emit = defineEmits(['update:modelValue', 'saved']);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
});
</script>
