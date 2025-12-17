# 短链接服务使用说明

## 📋 概述

实现了类似 Bitly 的自建短链接服务，可以将长 URL 转换为短链接，并提供完整的管理功能。

---

## 🎯 功能特性

### 核心功能

- ✅ **短链接生成**：自动生成或自定义短链接代码
- ✅ **URL 重定向**：访问短链接自动跳转到原始 URL
- ✅ **点击统计**：自动记录点击次数
- ✅ **链接管理**：创建、编辑、删除、禁用短链接
- ✅ **过期控制**：支持设置链接过期时间
- ✅ **权限控制**：管理员可查看所有，普通用户只能查看自己的

### 高级功能

- ✅ **自定义代码**：支持自定义短链接代码（3-20个字符）
- ✅ **Base62 编码**：使用 Base62 编码生成短链接（更短、更高效）
- ✅ **搜索功能**：支持按标题、URL、代码搜索
- ✅ **统计分析**：提供总链接数、总点击次数等统计

---

## 🔧 后端实现

### 数据模型

**表名：** `short_links`

**字段：**
- `id` - 短链接ID（主键）
- `short_code` - 短链接代码（唯一索引）
- `original_url` - 原始URL
- `title` - 短链接标题（可选）
- `description` - 短链接描述（可选）
- `created_by` - 创建者用户ID
- `click_count` - 点击次数
- `is_active` - 是否激活
- `expires_at` - 过期时间（可选）
- `created_at` - 创建时间
- `updated_at` - 更新时间

### API 端点

**基础路径：** `/api/v1/short-links/`

#### 1. 创建短链接
- **方法：** `POST /`
- **认证：** 需要登录
- **请求体：**
```json
{
  "original_url": "https://example.com/very/long/url",
  "short_code": "abc123",  // 可选，不填则自动生成
  "title": "示例链接",
  "description": "这是一个示例",
  "expires_at": "2024-12-31 23:59:59",  // 可选
  "is_active": true
}
```

#### 2. 获取短链接列表
- **方法：** `GET /`
- **认证：** 需要登录
- **查询参数：**
  - `page` - 页码
  - `page_size` - 每页条数
  - `search` - 搜索关键词
  - `is_active` - 是否激活过滤
  - `created_by` - 创建者ID过滤

#### 3. 获取短链接详情
- **方法：** `GET /{link_id}/detail`
- **认证：** 需要登录

#### 4. 更新短链接
- **方法：** `PUT /{link_id}`
- **认证：** 需要登录

#### 5. 删除短链接
- **方法：** `DELETE /{link_id}`
- **认证：** 需要登录

#### 6. 获取统计信息
- **方法：** `GET /stats/summary`
- **认证：** 需要登录

#### 7. 短链接重定向（公开）
- **方法：** `GET /s/{short_code}`
- **认证：** 无需认证
- **说明：** 访问短链接时自动重定向到原始URL

---

## 🎨 前端实现

### 组件

**组件路径：** `frontend/src/components/admin/ShortLinkManagement.vue`

**功能：**
- ✅ 短链接列表展示
- ✅ 创建/编辑短链接
- ✅ 删除短链接
- ✅ 搜索和筛选
- ✅ 统计信息展示
- ✅ 一键复制短链接

### API 调用

**文件路径：** `frontend/src/api/shortLink.js`

**方法：**
- `createShortLink(linkData)` - 创建短链接
- `getShortLinks(params)` - 获取短链接列表
- `getShortLinkDetail(linkId)` - 获取详情
- `updateShortLink(linkId, linkData)` - 更新短链接
- `deleteShortLink(linkId)` - 删除短链接
- `getShortLinkStats()` - 获取统计

---

## 📝 使用示例

### 创建短链接

```javascript
import { createShortLink } from '@/api/shortLink';

const link = await createShortLink({
  original_url: 'https://example.com/very/long/url',
  title: '示例链接',
  short_code: 'demo'  // 可选
});

console.log(link.short_url);  // https://yourdomain.com/s/demo
```

### 访问短链接

用户访问 `https://yourdomain.com/s/demo` 时，会自动重定向到原始URL。

### 在前端页面中使用

```vue
<template>
  <ShortLinkManagement />
</template>

<script setup>
import ShortLinkManagement from '@/components/admin/ShortLinkManagement.vue';
</script>
```

---

## 🔐 权限说明

- **管理员**：可以查看和管理所有短链接
- **普通用户**：只能查看和管理自己创建的短链接
- **公开访问**：短链接重定向（/s/{code}）无需认证

---

## 🎯 短链接生成算法

### Base62 编码

使用 Base62 编码（0-9, a-z, A-Z）生成短链接代码：

- **优点**：代码更短、URL友好
- **长度**：默认4-6个字符
- **唯一性**：自动检查并生成唯一代码

### 生成策略

1. **自定义代码**：如果用户提供了自定义代码，直接使用（需检查唯一性）
2. **ID编码**：优先使用链接ID的Base62编码
3. **随机生成**：如果ID编码已存在，使用随机生成

---

## 📊 数据库迁移

**SQL 脚本：** `scripts/data/short_links_table.sql`

**执行方式：**
```bash
mysql -u username -p database_name < scripts/data/short_links_table.sql
```

---

## 🎉 功能总结

- ✅ 完整的 CRUD 操作
- ✅ 短链接生成和重定向
- ✅ 点击统计
- ✅ 过期控制
- ✅ 权限管理
- ✅ 搜索和筛选
- ✅ 统计分析
- ✅ 前端管理界面

所有功能已完整实现，可以直接使用！

