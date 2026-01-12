# 客户 Telegram 通知前端实现说明

## 一、实现概述

客户 Telegram 通知配置的前端实现已经完成，管理员可以在用户管理页面为每个客户配置 Telegram 通知。

## 二、前端实现位置

### 2.1 主要文件

1. **客户通知配置对话框组件**
   - 文件路径：`frontend/src/components/admin/ClientNotificationConfigDialog.vue`
   - 功能：提供客户通知配置的完整界面

2. **用户管理页面**
   - 文件路径：`frontend/src/views/admin/UserManagement.vue`
   - 功能：在用户列表中添加"通知配置"按钮，打开通知配置对话框

3. **API 客户端**
   - 文件路径：`frontend/src/api/notification.js`
   - 功能：提供客户通知配置的 API 调用方法

## 三、使用方式

### 3.1 访问路径

1. 登录系统（管理员）
2. 进入 **用户管理** 页面（侧边栏 → 用户管理）
3. 在用户列表中找到客户用户（role = 'client'）
4. 点击操作列中的 **"通知"** 按钮
5. 打开客户通知配置对话框

### 3.2 配置步骤

1. **启用通知**
   - 打开"启用通知"开关
   - 关闭后，该客户的所有产品转化都不会发送通知

2. **通知转化事件**
   - 打开"通知转化事件"开关
   - 是否在转化发生时发送通知

3. **高价值转化通知**（可选）
   - 打开"高价值转化通知"开关
   - 设置"高价值阈值"（例如：$10.00）
   - 只有收益超过此金额的转化才会通知

4. **通知渠道**
   - 选择通知渠道（Telegram、邮箱、短信）
   - 可以选择多个通知渠道

5. **Telegram Chat ID**
   - 如果选择了 Telegram 渠道，需要填写 Chat ID
   - 获取 Chat ID 的方法：
     - 在 Telegram 中搜索 `@userinfobot`
     - 发送 `/start` 命令
     - 机器人会返回您的 Chat ID
     - 或者点击对话框中的链接获取

6. **通知频率**
   - 实时通知：立即发送
   - 每小时汇总：每小时汇总后发送
   - 每天汇总：每天汇总后发送

7. **保存配置**
   - 点击"保存"按钮
   - 配置保存成功后，对话框会自动关闭

## 四、界面展示

### 4.1 用户管理页面

在用户列表的操作列中，对于客户用户（role = 'client'），会显示以下按钮：

- **查看**：查看用户详情
- **编辑**：编辑用户信息
- **产品**：管理客户产品
- **通知**：配置客户通知（新增）
- **禁用/启用**：切换用户状态
- **删除**：删除用户

### 4.2 通知配置对话框

对话框包含以下配置项：

```
┌─────────────────────────────────────────┐
│  客户名称 - 通知配置                      │
├─────────────────────────────────────────┤
│                                          │
│  ☑ 启用通知                              │
│    关闭后，该客户的所有产品转化都不会发送通知│
│                                          │
│  ─────────────────────────────────────  │
│                                          │
│  ☑ 通知转化事件                           │
│    是否在转化发生时发送通知                │
│                                          │
│  ☐ 高价值转化通知                         │
│    只通知超过阈值的转化                    │
│                                          │
│  高价值阈值: [10.00]                      │
│    只有收益超过此金额的转化才会通知         │
│                                          │
│  ─────────────────────────────────────  │
│                                          │
│  通知渠道:                               │
│  ☑ Telegram  ☐ 邮箱  ☐ 短信              │
│                                          │
│  Telegram Chat ID:                       │
│  [________________]                      │
│  ℹ️ 获取 Chat ID：与 @BotFather 创建的    │
│     机器人对话，发送 /start，然后发送任意  │
│     消息，[点击这里]获取您的 Chat ID       │
│                                          │
│  ─────────────────────────────────────  │
│                                          │
│  通知频率:                               │
│  ⚪ 实时通知  ⚪ 每小时汇总  ⚪ 每天汇总    │
│                                          │
│  [取消]  [保存]                          │
│                                          │
└─────────────────────────────────────────┘
```

## 五、代码实现

### 5.1 用户管理页面修改

**添加通知配置按钮**：

```vue
<el-button 
  v-if="scope.row.role === 'client'"
  size="small" 
  type="warning" 
  :icon="Bell"
  @click="handleNotificationConfig(scope.row)"
  title="通知配置"
>
  通知
</el-button>
```

**导入组件和图标**：

```javascript
import ClientNotificationConfigDialog from '../../components/admin/ClientNotificationConfigDialog.vue';
import { ..., Bell } from '@element-plus/icons-vue';
```

**添加对话框**：

```vue
<ClientNotificationConfigDialog
  v-model="notificationConfigDialogVisible"
  :client-id="currentClientIdForNotification"
  :client-name="currentClientNameForNotification"
  @saved="handleNotificationConfigSaved"
/>
```

**添加处理函数**：

```javascript
const notificationConfigDialogVisible = ref(false);
const currentClientIdForNotification = ref(null);
const currentClientNameForNotification = ref('');

const handleNotificationConfig = async (user) => {
  if (user.role !== 'client') {
    return;
  }
  
  // 如果没有客户信息，尝试获取最新的用户详情
  if (!user.client?.id) {
    try {
      const userData = await getUserDetail(user.id);
      if (userData.client?.id) {
        user.client = userData.client;
      } else {
        ElMessage.warning('该客户用户还没有关联的客户信息，请先编辑用户并创建客户信息');
        return;
      }
    } catch (error) {
      // 错误处理
      return;
    }
  }
  
  // 打开通知配置对话框
  if (user.client?.id) {
    currentClientIdForNotification.value = user.client.id;
    currentClientNameForNotification.value = user.full_name || user.username || user.client.company_name || '未知客户';
    notificationConfigDialogVisible.value = true;
  }
};

const handleNotificationConfigSaved = () => {
  ElMessage.success('通知配置已保存');
};
```

### 5.2 通知配置对话框组件

**组件 Props**：

```javascript
const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  clientId: {
    type: Number,
    required: true
  },
  clientName: {
    type: String,
    default: '客户'
  }
});
```

**表单数据**：

```javascript
const formData = reactive({
  notification_enabled: true,
  notify_on_conversion: true,
  notify_on_high_value: false,
  high_value_threshold: null,
  notify_channels: null,
  telegram_chat_id: null,
  email_address: null,
  phone_number: null,
  notification_frequency: 'realtime'
});
```

**表单验证**：

```javascript
const formRules = {
  telegram_chat_id: [
    {
      validator: (rule, value, callback) => {
        if (selectedChannels.value.includes('telegram') && formData.notification_enabled) {
          if (!value || !value.trim()) {
            callback(new Error('选择 Telegram 渠道时必须填写 Chat ID'));
          } else if (!/^-?\d+$/.test(value.trim())) {
            callback(new Error('Chat ID 必须是数字（可以是负数）'));
          } else {
            callback();
          }
        } else {
          callback();
        }
      },
      trigger: 'blur'
    }
  ],
  high_value_threshold: [
    {
      validator: (rule, value, callback) => {
        if (formData.notify_on_high_value && (!value || value <= 0)) {
          callback(new Error('启用高价值转化通知时，必须设置阈值'));
        } else {
          callback();
        }
      },
      trigger: 'blur'
    }
  ]
};
```

## 六、功能特性

### 6.1 表单验证

- ✅ Telegram Chat ID 格式验证（必须是数字，可以是负数）
- ✅ 高价值阈值验证（启用时必须设置且大于0）
- ✅ 渠道选择验证（选择 Telegram 时必须填写 Chat ID）

### 6.2 用户体验

- ✅ 实时表单验证
- ✅ 清晰的提示信息
- ✅ 获取 Chat ID 的链接和说明
- ✅ 响应式设计（支持移动端）

### 6.3 数据加载

- ✅ 对话框打开时自动加载配置
- ✅ 如果配置不存在，显示默认值
- ✅ 加载状态提示

### 6.4 数据保存

- ✅ 保存前验证表单
- ✅ 保存成功提示
- ✅ 保存失败错误提示
- ✅ 保存成功后自动关闭对话框

## 七、API 调用

### 7.1 获取客户通知配置

```javascript
GET /api/v1/notification-configs/clients/{client_id}/config
```

### 7.2 保存客户通知配置

```javascript
POST /api/v1/notification-configs/clients/{client_id}/config

Request Body:
{
  "notification_enabled": true,
  "notify_on_conversion": true,
  "notify_on_high_value": false,
  "high_value_threshold": null,
  "notify_channels": "[\"telegram\"]",
  "telegram_chat_id": "-1001234567890",
  "email_address": null,
  "phone_number": null,
  "notification_frequency": "realtime"
}
```

## 八、总结

客户 Telegram 通知配置的前端实现已经完成，包括：

✅ 在用户管理页面添加"通知配置"按钮  
✅ 通知配置对话框组件（完整功能）  
✅ 表单验证（Chat ID 格式、阈值验证等）  
✅ 用户体验优化（提示信息、链接等）  
✅ API 集成（获取和保存配置）  

**使用方式**：管理员在用户管理页面，点击客户用户的"通知"按钮，即可配置该客户的 Telegram 通知。
