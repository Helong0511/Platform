<!--
  客户通知配置弹窗（兼容入口，委托 NotificationConfigDialog）
  @file components/admin/ClientNotificationConfigDialog.vue
-->
<template>
  <NotificationConfigDialog
    v-model="visible"
    entity-type="client"
    :entity-id="clientId"
    :entity-name="clientName"
    @saved="emit('saved')"
  />
</template>

<script setup>
import { computed } from 'vue';
import NotificationConfigDialog from './NotificationConfigDialog.vue';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  clientId: { type: Number, required: true },
  clientName: { type: String, default: '客户' },
});

const emit = defineEmits(['update:modelValue', 'saved']);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
});
</script>
