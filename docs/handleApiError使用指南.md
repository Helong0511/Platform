# handleApiError 使用指南

## 📖 简介

`handleApiError` 是一个统一的API错误处理函数，用于在组件的catch块中处理错误，避免重复显示已处理的错误（如401/403错误）。

## 🎯 主要功能

1. **自动识别已处理的错误**：401和403错误通常由axios拦截器处理，不会重复显示
2. **友好的错误提示**：显示后端返回的具体错误信息，而不是通用的"操作失败"
3. **日志记录**：自动记录错误日志，方便调试
4. **灵活配置**：支持自定义错误消息、日志上下文等

## 📝 基本用法

### 1. 最简单的用法

```javascript
try {
  await createOffer(formData);
  ElMessage.success('创建成功');
} catch (error) {
  handleApiError(error, '操作失败', { logContext: '创建Offer' });
}
```

### 2. 根据返回值处理

```javascript
try {
  await updateOffer(id, formData);
  ElMessage.success('更新成功');
} catch (error) {
  // 如果返回true，说明错误已被处理（401/403），可以提前返回
  if (handleApiError(error, '操作失败', { logContext: '更新Offer' })) {
    return; // 401/403错误已由拦截器处理，直接返回
  }
  // 其他错误处理逻辑（如果需要）
}
```

### 3. 不显示错误消息（仅记录日志）

```javascript
try {
  await someApiCall();
} catch (error) {
  // 只记录日志，不显示错误消息
  handleApiError(error, '操作失败', { 
    showMessage: false,
    logContext: '静默操作'
  });
}
```

### 4. 自定义错误消息

```javascript
try {
  await deleteOffer(id);
  ElMessage.success('删除成功');
} catch (error) {
  handleApiError(error, '删除失败，请稍后重试', { 
    logContext: '删除Offer'
  });
}
```

## 🔍 错误处理逻辑

### 401错误（Token过期）
- **处理方式**：自动识别，不显示错误消息
- **原因**：axios拦截器已处理（清除认证信息并跳转登录页）
- **返回值**：`true`（表示错误已被处理）

### 403错误（CSRF Token问题）
- **处理方式**：检查是否已被处理（`_handled`标记）
- **原因**：axios拦截器可能已自动刷新token并重试
- **返回值**：
  - `true`：错误已被处理，不显示错误消息
  - `false`：错误未被处理，显示错误消息

### 其他错误
- **处理方式**：显示后端返回的具体错误信息
- **返回值**：`false`（表示错误需要进一步处理）

## 📋 参数说明

### error (必需)
错误对象，通常是catch块捕获的Error对象。

### defaultMessage (可选)
默认错误消息，当无法从错误对象中提取错误信息时使用。
- 默认值：`'操作失败'`

### options (可选)
配置选项对象，包含以下属性：

#### showMessage (可选)
是否显示错误消息。
- 类型：`boolean`
- 默认值：`true`

#### logError (可选)
是否记录错误日志。
- 类型：`boolean`
- 默认值：`true`

#### logContext (可选)
日志上下文，用于标识错误来源。
- 类型：`string`
- 默认值：`'API调用'`

## 💡 最佳实践

### 1. 在提交操作中使用

```javascript
const handleSubmit = async () => {
  submitting.value = true;
  try {
    const response = await createOffer(formData);
    if (response.code === 200) {
      ElMessage.success('创建成功');
      dialogVisible.value = false;
      loadData();
    } else {
      ElMessage.error(response.message || '操作失败');
    }
  } catch (error) {
    // 使用handleApiError统一处理错误
    handleApiError(error, '操作失败', { logContext: '提交Offer' });
  } finally {
    submitting.value = false;
  }
};
```

### 2. 在删除操作中使用

```javascript
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定要删除吗？`, '确认删除');
    const response = await deleteOffer(row.id);
    if (response.code === 200) {
      ElMessage.success('删除成功');
      loadData();
    } else {
      ElMessage.error(response.message || '删除失败');
    }
  } catch (error) {
    if (error !== 'cancel') {
      // 使用handleApiError统一处理错误
      handleApiError(error, '删除失败', { logContext: '删除Offer' });
    }
  }
};
```

### 3. 在数据加载中使用

```javascript
const loadData = async () => {
  loading.value = true;
  try {
    const response = await getOffers(params);
    if (response.code === 200) {
      tableData.value = response.data || [];
    }
  } catch (error) {
    // 使用handleApiError统一处理错误
    handleApiError(error, '获取数据失败', { logContext: '加载Offer列表' });
  } finally {
    loading.value = false;
  }
};
```

## ⚠️ 注意事项

1. **函数是同步的**：虽然内部有异步操作，但函数本身是同步的，不会阻塞调用
2. **401/403错误**：这些错误通常由axios拦截器处理，不需要额外处理
3. **错误消息优先级**：后端返回的`detail` > `message` > `error.message` > `defaultMessage`
4. **日志记录**：错误日志是异步记录的，不会影响性能

## 🔄 迁移指南

### 从旧代码迁移

**旧代码**：
```javascript
catch (error) {
  logger.error('提交失败:', error);
  ElMessage.error('操作失败');
}
```

**新代码**：
```javascript
catch (error) {
  handleApiError(error, '操作失败', { logContext: '提交数据' });
}
```

### 已修复的错误处理

**已修复的代码**（可以直接使用）：
```javascript
catch (error) {
  logger.error('提交失败:', error);
  
  if (error.response && error.response.status === 401) {
    return;
  }
  
  if (error.response && error.response.status === 403 && error._handled) {
    return;
  }
  
  const errorMsg = error.response?.data?.detail || 
                  error.response?.data?.message || 
                  error.message || 
                  '操作失败';
  ElMessage.error(errorMsg);
}
```

**可以简化为**：
```javascript
catch (error) {
  handleApiError(error, '操作失败', { logContext: '提交数据' });
}
```

## 📚 相关文档

- [认证问题全面排查报告.md](./认证问题全面排查报告.md)
- [修复总结.md](./修复总结.md)
- [frontend/src/utils/api.js](./frontend/src/utils/api.js)

---

**最后更新**: 2024年

