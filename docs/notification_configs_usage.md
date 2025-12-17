# 通知配置功能使用说明

## 📋 概述

已为三个通知相关表实现了完整的前后端功能：

1. **`client_notification_configs`** - 客户通知配置
2. **`product_notification_configs`** - 产品通知配置
3. **`postback_notifications`** - 通知记录查询

---

## 🔧 后端 API

### 客户通知配置 API

**基础路径：** `/api/v1/notification-configs/clients/{client_id}/config`

- `GET` - 获取客户通知配置
- `POST` - 创建或更新客户通知配置
- `DELETE` - 删除客户通知配置

### 产品通知配置 API

**基础路径：** `/api/v1/notification-configs/products/{product_id}/config`

- `GET` - 获取产品通知配置
- `POST` - 创建或更新产品通知配置
- `DELETE` - 删除产品通知配置

### 通知记录查询 API

**基础路径：** `/api/v1/notification-configs/notifications`

- `GET` - 获取通知记录列表（支持分页和过滤）
  - 查询参数：
    - `page` - 页码
    - `page_size` - 每页条数
    - `client_id` - 客户ID过滤
    - `product_id` - 产品ID过滤
    - `notification_status` - 状态过滤（sent, failed, pending）
    - `notification_channel` - 渠道过滤（telegram, email, sms）
    - `start_date` - 开始日期（YYYY-MM-DD）
    - `end_date` - 结束日期（YYYY-MM-DD）

- `GET /{notification_id}` - 获取通知记录详情

---

## 🎨 前端组件

### 1. 客户通知配置组件

**组件路径：** `frontend/src/components/admin/ClientNotificationConfigDialog.vue`

**使用方式：**
```vue
<template>
  <ClientNotificationConfigDialog
    v-model="configVisible"
    :client-id="clientId"
    :client-name="clientName"
    @saved="handleConfigSaved"
  />
</template>

<script setup>
import ClientNotificationConfigDialog from '@/components/admin/ClientNotificationConfigDialog.vue';

const configVisible = ref(false);
const clientId = ref(1);
const clientName = ref('客户名称');

const handleConfigSaved = () => {
  // 配置保存后的回调
  console.log('配置已保存');
};
</script>
```

**功能特性：**
- ✅ 启用/禁用通知
- ✅ 通知转化事件开关
- ✅ 高价值转化通知（可设置阈值）
- ✅ 多通知渠道选择（Telegram、邮箱、短信）
- ✅ 各渠道接收人配置
- ✅ 通知频率设置（实时、每小时、每天）

### 2. 产品通知配置组件

**组件路径：** `frontend/src/components/admin/ProductNotificationConfigDialog.vue`

**使用方式：**
```vue
<template>
  <ProductNotificationConfigDialog
    v-model="configVisible"
    :product-id="productId"
    :product-name="productName"
    @saved="handleConfigSaved"
  />
</template>

<script setup>
import ProductNotificationConfigDialog from '@/components/admin/ProductNotificationConfigDialog.vue';

const configVisible = ref(false);
const productId = ref(1);
const productName = ref('产品名称');
</script>
```

**功能特性：**
- ✅ 与客户通知配置相同的功能
- ✅ 优先级高于客户配置

### 3. 通知记录查看组件

**组件路径：** `frontend/src/components/admin/NotificationRecordsDialog.vue`

**使用方式：**
```vue
<template>
  <NotificationRecordsDialog
    v-model="recordsVisible"
    :client-id="clientId"
    :product-id="productId"
  />
</template>

<script setup>
import NotificationRecordsDialog from '@/components/admin/NotificationRecordsDialog.vue';

const recordsVisible = ref(false);
const clientId = ref(1);  // 可选
const productId = ref(1);  // 可选
</script>
```

**功能特性：**
- ✅ 通知记录列表展示
- ✅ 状态和渠道筛选
- ✅ 分页支持
- ✅ 错误信息查看

---

## 📝 API 调用示例

### 前端 API 调用

**文件路径：** `frontend/src/api/notification.js`

```javascript
import {
  getClientNotificationConfig,
  saveClientNotificationConfig,
  deleteClientNotificationConfig,
  getProductNotificationConfig,
  saveProductNotificationConfig,
  deleteProductNotificationConfig,
  getNotificationRecords,
  getNotificationRecord
} from '@/api/notification';

// 获取客户通知配置
const config = await getClientNotificationConfig(clientId);

// 保存客户通知配置
await saveClientNotificationConfig(clientId, {
  notification_enabled: true,
  notify_on_conversion: true,
  notify_on_high_value: true,
  high_value_threshold: 100.0,
  notify_channels: '["telegram", "email"]',
  telegram_chat_id: '123456789',
  email_address: 'client@example.com',
  notification_frequency: 'realtime'
});

// 获取通知记录
const records = await getNotificationRecords({
  page: 1,
  page_size: 20,
  notification_status: 'sent',
  notification_channel: 'telegram'
});
```

---

## 🔗 集成到现有页面

### 在客户管理页面添加通知配置按钮

```vue
<template>
  <el-button @click="openNotificationConfig">通知配置</el-button>
  <ClientNotificationConfigDialog
    v-model="notificationConfigVisible"
    :client-id="currentClientId"
    :client-name="currentClientName"
  />
</template>

<script setup>
import ClientNotificationConfigDialog from '@/components/admin/ClientNotificationConfigDialog.vue';

const notificationConfigVisible = ref(false);
const currentClientId = ref(null);
const currentClientName = ref('');

const openNotificationConfig = () => {
  notificationConfigVisible.value = true;
};
</script>
```

### 在产品管理页面添加通知配置按钮

```vue
<template>
  <el-button @click="openNotificationConfig(product)">通知配置</el-button>
  <ProductNotificationConfigDialog
    v-model="notificationConfigVisible"
    :product-id="selectedProductId"
    :product-name="selectedProductName"
  />
</template>

<script setup>
import ProductNotificationConfigDialog from '@/components/admin/ProductNotificationConfigDialog.vue';

const notificationConfigVisible = ref(false);
const selectedProductId = ref(null);
const selectedProductName = ref('');

const openNotificationConfig = (product) => {
  selectedProductId.value = product.id;
  selectedProductName.value = product.name;
  notificationConfigVisible.value = true;
};
</script>
```

---

## 🎯 功能说明

### 配置优先级

```
产品通知配置 > 客户通知配置 > 默认配置
```

### 通知渠道

- **Telegram**：需要配置 `telegram_chat_id`
- **邮箱**：需要配置 `email_address`
- **短信**：需要配置 `phone_number`

### 通知频率

- **realtime**：转化发生时立即发送通知
- **hourly**：每小时汇总发送一次
- **daily**：每天汇总发送一次

### 高价值转化通知

- 启用后，只有收益超过阈值的转化才会通知
- 阈值单位为美元（USD）

---

## ✅ 完成状态

- ✅ 后端 Schema 定义
- ✅ 后端 API 端点实现
- ✅ 前端 API 调用封装
- ✅ 前端组件实现
- ✅ 权限控制
- ✅ 数据验证

所有功能已完整实现，可以直接使用！

