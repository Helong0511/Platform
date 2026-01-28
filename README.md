# 广告数据管理服务平台 开发手册

## 📋 目录

1. [项目概述](#项目概述)
2. [技术栈](#技术栈)
3. [项目架构](#项目架构)
4. [环境配置](#环境配置)
5. [后端开发指南](#后端开发指南)
6. [前端开发指南](#前端开发指南)
7. [数据库设计](#数据库设计)
8. [部署指南](#部署指南)
9. [开发规范](#开发规范)
10. [常见问题](#常见问题)

---

## 项目概述

### 项目简介
广告数据管理服务平台 是一个广告联盟管理系统，用于管理广告主、渠道、Offer、转化数据等核心业务。系统提供完整的CPL（Cost Per Lead）管理功能，包括Cap限制、扣量管理、Postback回调、短链接服务等。

### 核心功能
- **用户管理**：管理员和客户角色的权限管理
- **客户管理**：客户信息、产品分配、通知配置
- **CPL系统**：广告主、渠道、Offer、Cap、扣量管理
- **转化追踪**：点击追踪、Postback回调、短链接服务
- **数据分析**：广告数据统计、转化统计、仪表盘
- **系统管理**：定时任务、审计日志、会话管理
- **通知服务**：Telegram Bot通知、邮件通知

### 业务术语
- **上游**：广告主（Advertiser）
- **下游**：客户 = 渠道 = 商户（Publisher）
- **Offer**：广告任务
- **Cap**：转化上限限制
- **Postback**：转化回调通知
- **扣量**：转化数据调整

---

## 快速开始

### 5分钟快速启动

#### Windows开发环境
```bash
# 1. 克隆项目
git clone <repository-url>
cd Platform

# 2. 创建虚拟环境
py -m venv venv
venv\Scripts\activate

# 3. 安装后端依赖
pip install -r requirements.txt

# 4. 生成环境配置（自动检测系统）
python scripts/自动生成配置/auto_generate_env_config.py --no-interactive

# 5. 启动后端服务
py -m uvicorn app.main:app --reload --port 8960

# 6. 新开终端，安装前端依赖
cd frontend
npm install

# 7. 启动前端服务
npm run dev

# 8. 访问应用
# 前端：http://localhost:3310
# 后端API：http://localhost:8960/api/v1/docs
# 默认账号：admin / admin123
```

#### Ubuntu生产环境
```bash
# 1. 克隆项目
cd /data
git clone <repository-url> Platform
cd Platform

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装后端依赖
pip install -r requirements.txt

# 4. 生成环境配置（生产模式）
sudo python3 scripts/自动生成配置/auto_generate_env_config.py --env production --no-interactive

# 5. 配置数据库
sudo mysql -u root -p
# 在MySQL中执行：
# CREATE DATABASE platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
# CREATE USER 'platform'@'localhost' IDENTIFIED BY 'your_password';
# GRANT ALL PRIVILEGES ON platform.* TO 'platform'@'localhost';
# FLUSH PRIVILEGES;

# 6. 导入初始数据
mysql -u platform -p platform < scripts/data/platform20260112.sql

# 7. 生成RSA密钥
python scripts/生成RSA密钥/generate_rsa_keys.py --output-dir keys

# 8. 配置systemd服务
sudo cp systemd/Platform-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable Platform-backend
sudo systemctl start Platform-backend

# 9. 构建前端
cd frontend
npm install
npm run build

# 10. 配置Nginx
sudo cp nginx/btfrx.online/nginx.conf /etc/nginx/sites-available/platform
sudo ln -s /etc/nginx/sites-available/platform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 11. 获取SSL证书
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### 自动化配置脚本

项目提供了智能的环境配置生成脚本，可以自动检测系统并生成合适的配置。

#### 使用方法

```bash
# 方式1：自动检测系统（推荐）
python scripts/自动生成配置/auto_generate_env_config.py

# 方式2：强制指定环境
python scripts/自动生成配置/auto_generate_env_config.py --env production

# 方式3：非交互模式（适合自动化）
python scripts/自动生成配置/auto_generate_env_config.py --no-interactive

# 方式4：指定输出文件
python scripts/自动生成配置/auto_generate_env_config.py --output .env.prod
```

#### 配置特点

**生产环境（production）**
- JWT算法：RS256（非对称加密）
- 访问令牌过期：240分钟
- CSRF防护：启用
- 日志级别：INFO
- Telegram通知：启用
- API限流：100次/分钟
- 数据库连接池：15个连接

**开发环境（development）**
- JWT算法：HS256（对称加密）
- 访问令牌过期：120分钟
- CSRF防护：禁用
- 日志级别：DEBUG
- Telegram通知：禁用
- API限流：1000次/分钟
- 数据库连接池：5个连接

#### Ubuntu权限自动设置

脚本会自动处理文件权限：

```bash
# 如果以root权限运行，自动设置：
# - 所有者：www-data:www-data
# - 权限：640（所有者可读写，组可读）

# 如果不是root权限，提示手动执行：
sudo chown www-data:www-data .env
sudo chmod 640 .env
```

详细说明请参考：[自动配置生成脚本使用说明](scripts/自动生成配置/README_自动配置生成.md)

---

## 技术栈

### 后端技术栈
```
FastAPI 0.104.1          # Web框架
SQLAlchemy 2.0.23        # ORM框架
Pydantic 2.7.0           # 数据验证
Redis 5.0+               # 缓存和限流
MySQL 8.0                # 数据库
Gunicorn 21.2.0          # WSGI服务器
Uvicorn 0.24.0           # ASGI服务器
APScheduler 3.10.4       # 定时任务
python-jose 3.3.0        # JWT处理
bcrypt 4.0.1             # 密码加密
```

### 前端技术栈
```
Vue 3.5.22               # 前端框架
Vite 7.1.7               # 构建工具
Element Plus 2.11.7      # UI组件库
Vue Router 4.6.3         # 路由管理
Pinia 3.0.3              # 状态管理
Axios 1.13.1             # HTTP客户端
ECharts 6.0.0            # 图表库
```

### 开发工具
```
Python 3.10              # Python运行环境
Node.js                  # Node运行环境
Git                      # 版本控制
VS Code                  # 代码编辑器
```

---

## 项目架构

### 整体架构图
```
┌─────────────────────────────────────────────────────────┐
│                      Nginx (反向代理)                    │
│                   HTTPS / 443, 80                       │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐       ┌────────▼────────┐
│  Frontend      │       │  Backend        │
│  (Vue 3)       │       │  (FastAPI)      │
│  Port: 3310    │       │  Port: 8960     │
└────────────────┘       └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
              ┌─────▼────┐  ┌────▼────┐  ┌────▼────┐
              │  MySQL   │  │  Redis  │  │Telegram │
              │  :3306   │  │  :6379  │  │   Bot   │
              └──────────┘  └─────────┘  └─────────┘
```

### 后端目录结构
```
app/
├── api/                    # API路由层
│   └── api_v1/
│       ├── endpoints/       # API端点
│       │   ├── auth/       # 认证模块（auth.py, refresh.py）
│       │   ├── users/      # 用户管理（users.py）
│       │   ├── clients/    # 客户管理（clients.py）
│       │   ├── cpl/        # CPL系统
│       │   │   ├── conversions/  # 转化管理
│       │   │   │   ├── clicks.py      # 点击记录
│       │   │   │   ├── deductions.py  # 扣减记录
│       │   │   │   ├── log.py         # 转化日志
│       │   │   │   └── summary.py     # 转化统计
│       │   │   └── tests/         # 下游测试（affiliate_tests.py）
│       │   ├── postback/   # Postback服务（postback.py, bft.py, ip_whitelist.py）
│       │   ├── tracking/   # 追踪服务（tracking.py, short_links.py）
│       │   ├── products/   # 产品管理（products.py, assignments.py）
│       │   ├── system/     # 系统管理
│       │   │   ├── audit_logs.py          # 审计日志
│       │   │   ├── notification_configs.py # 通知配置
│       │   │   ├── scheduled_tasks.py     # 定时任务
│       │   │   └── sessions.py            # 会话管理
│       │   ├── external/   # 外部接口（client_api.py, telegram.py）
│       │   ├── excel/      # Excel处理（import_handler.py, export_handler.py）
│       │   ├── ml_model/   # ML模型管理（ml_model.py）
│       │   ├── examples/   # 示例代码
│       │   ├── ad_data.py  # 广告数据
│       │   ├── dashboard.py # 仪表盘
│       │   └── tb_search_data.py # TB搜索数据
│       └── api.py          # 路由聚合
├── core/                   # 核心模块
│   ├── cap/               # Cap管理（cap_manager.py, redis_counter.py, consistency_checker.py）
│   ├── deduction/         # 扣量管理（deduction_manager.py）
│   ├── discount/          # 折扣管理（discount_manager.py）
│   ├── infrastructure/    # 基础设施（cache.py, cache_compat.py）
│   ├── postback/          # Postback处理（processor.py, forwarder.py, handlers.py, bft_handler.py, notifier.py）
│   ├── short_link/        # 短链接（generator.py）
│   ├── tracking/          # 追踪功能（click_id_generator.py, tracklink_generator.py）
│   ├── config.py          # 配置管理
│   ├── database.py        # 数据库连接
│   ├── security.py        # 安全相关（JWT、密码加密）
│   ├── redis_client.py    # Redis客户端
│   ├── cache.py           # 缓存管理
│   ├── cache_manager.py   # 缓存管理器
│   ├── csrf.py            # CSRF防护
│   ├── dependencies.py    # 依赖注入
│   ├── decorators.py      # 装饰器
│   ├── errors.py          # 错误处理
│   ├── exceptions.py      # 异常定义
│   ├── middleware.py      # 中间件
│   ├── audit_log.py       # 审计日志
│   ├── utils.py           # 工具函数
│   └── ...                # 其他核心模块
├── models/                 # 数据模型
│   └── models.py          # ORM模型定义（User, Client, Advertiser, Publisher, Offer等）
├── schemas/                # Pydantic模式
│   ├── cpl/               # CPL相关模式
│   │   ├── advertiser.py  # 广告主模式
│   │   ├── publisher.py   # 渠道模式
│   │   ├── offer.py       # Offer模式
│   │   ├── cap.py         # Cap模式
│   │   ├── discount.py    # 折扣模式
│   │   ├── click.py       # 点击模式
│   │   ├── deduction.py   # 扣减模式
│   │   └── test.py        # 测试模式
│   ├── auth.py            # 认证模式
│   ├── user.py            # 用户模式
│   ├── client.py          # 客户模式
│   ├── product.py         # 产品模式
│   ├── product_assignment.py # 产品分配模式
│   ├── postback.py        # Postback模式
│   ├── short_link.py      # 短链接模式
│   ├── ad_data.py         # 广告数据模式
│   ├── tb_search_data.py  # TB搜索数据模式
│   ├── audit_log.py       # 审计日志模式
│   ├── notification.py    # 通知模式
│   ├── excel.py           # Excel模式
│   └── base.py            # 基础模式
├── services/               # 业务逻辑层
│   ├── cpl/               # CPL服务
│   │   ├── advertiser_service.py       # 广告主服务
│   │   ├── publisher_service.py        # 渠道服务
│   │   ├── offer_service.py            # Offer服务
│   │   ├── cap_service.py              # Cap服务
│   │   ├── discount_service.py         # 折扣服务
│   │   ├── conversion_service.py       # 转化服务
│   │   ├── conversion_deduction_service.py # 转化扣减服务
│   │   ├── conversion_log_service.py   # 转化日志服务
│   │   └── __init__.py
│   ├── user_service.py    # 用户服务
│   ├── client_service.py  # 客户服务
│   ├── product_service.py # 产品服务
│   ├── product_assignment_service.py # 产品分配服务
│   ├── dashboard_service.py # 仪表盘服务
│   ├── ad_data_service.py # 广告数据服务
│   ├── click_service.py  # 点击服务
│   ├── short_link_service.py # 短链接服务
│   ├── telegram_notification_service.py # Telegram通知服务
│   ├── audit_log_service.py # 审计日志服务
│   ├── scheduled_task_service.py # 定时任务服务
│   ├── session_service.py # 会话服务
│   ├── notification_config_service.py # 通知配置服务
│   ├── base_service.py    # 基础服务
│   └── __init__.py
├── scheduler_module/       # 定时任务模块
│   ├── tasks/             # 定时任务
│   │   ├── addermobi_task.py      # Addermobi任务
│   │   ├── skymobi_task.py        # Skymobi任务
│   │   ├── tbsj_task.py           # TBSJ任务
│   │   ├── tqt_task.py            # TQT任务
│   │   ├── archive_old_clicks.py   # 归档旧点击
│   │   ├── archive_old_data.py     # 归档旧数据
│   │   ├── cleanup_expired_sessions.py # 清理过期会话
│   │   ├── cleanup_old_logs.py     # 清理旧日志
│   │   └── notification_summary_task.py # 通知汇总任务
│   ├── scheduler.py       # 调度器
│   ├── task_init.py       # 任务初始化
│   ├── task_registry.py   # 任务注册
│   ├── task_queue.py      # 任务队列
│   ├── task_result_registry.py # 任务结果注册
│   ├── task_config.py     # 任务配置
│   ├── task_names.py      # 任务名称
│   ├── task_utils.py      # 任务工具
│   ├── process_allocator.py # 进程分配器
│   ├── lock.py            # 锁机制
│   └── __init__.py
├── db/                     # 数据库
│   └── database.py        # 数据库配置
├── repositories/           # 仓储层
│   ├── base_repository.py # 基础仓储
│   ├── offer_repository.py # Offer仓储
│   └── __init__.py
├── routes/                 # 路由层 - 处理HTTP请求和响应
│   ├── short_link/        # 短链接路由模块 - 短链接系统的核心组件
│   │   ├── handlers.py    # 短链接重定向请求处理模块 - 处理缓存命中和数据库查询两种场景的重定向逻辑
│   │   ├── router.py      # 短链接重定向路由模块 - 定义短链接重定向的API端点（/s/{short_code}）
│   │   ├── url_builder.py # URL构建服务 - 处理URL参数合并和最终URL构建逻辑
│   │   ├── utils.py       # 短链接重定向工具函数 - 提供Offer ID解析和点击记录创建功能
│   │   └── placeholder.py # 占位符替换服务 - 处理短链接URL中的占位符替换逻辑（支持{click_id}、{offer_id}等）
│   ├── short_link_redirect.py # 短链接重定向路由（完整版）- 包含完整的短链接重定向逻辑和占位符替换
│   └── __init__.py
├── scheduler/              # 调度器（旧版）- 定时任务模块
│   ├── clicks_batch_processor.py # 点击记录批量处理任务 - 从Redis队列批量取出点击记录，批量插入到数据库（高并发优化）
│   ├── cpl_tasks.py        # CPL系统定时任务 - 每日Cap重置任务（每天00:00 UTC执行）
│   ├── forward_tasks.py    # Postback下游转发任务 - 处理PostbackForwardQueue中的任务，包含重试机制（最大重试5次）
│   └── short_link_tasks.py # 短链接相关定时任务 - 同步短链接点击次数到数据库（每5分钟）和批量处理点击记录队列（每10秒）
└── main.py                # 应用入口 - FastAPI应用启动入口
```

### 前端目录结构
```
frontend/
├── src/
│   ├── api/               # API接口
│   │   ├── auth.js        # 认证接口
│   │   ├── user.js        # 用户接口
│   │   ├── client.js      # 客户接口
│   │   ├── product.js     # 产品接口
│   │   ├── advertiser.js  # 广告主接口
│   │   ├── publisher.js   # 渠道接口
│   │   ├── offer.js       # Offer接口
│   │   ├── cap.js         # Cap接口
│   │   ├── discount.js    # 折扣接口
│   │   ├── deduction.js   # 扣减接口
│   │   ├── conversionSummary.js # 转化统计接口
│   │   ├── affiliateTest.js # 下游测试接口
│   │   ├── clicks.js      # 点击记录接口
│   │   ├── postback.js    # Postback接口
│   │   ├── shortLink.js   # 短链接接口
│   │   ├── adData.js      # 广告数据接口
│   │   ├── tbSearchData.js # TB搜索数据接口
│   │   ├── dashboard.js   # 仪表盘接口
│   │   ├── auditLog.js    # 审计日志接口
│   │   ├── session.js     # 会话接口
│   │   ├── scheduledTask.js # 定时任务接口
│   │   ├── notification.js # 通知接口
│   │   └── mlModel.js     # ML模型接口
│   ├── components/        # 公共组件
│   │   ├── Layout/        # 布局组件
│   │   │   ├── MainLayout.vue  # 主布局
│   │   │   └── Sidebar.vue     # 侧边栏
│   │   ├── admin/         # 管理组件
│   │   │   ├── ClickLogDetailDialog.vue      # 点击日志详情对话框
│   │   │   ├── ClickLogFilter.vue           # 点击日志过滤器
│   │   │   ├── ClientFormDialog.vue         # 客户表单对话框
│   │   │   ├── ClientNotificationConfigDialog.vue # 客户通知配置对话框
│   │   │   ├── ClientTable.vue              # 客户表格
│   │   │   ├── FilterForm.vue               # 过滤表单
│   │   │   ├── NotificationRecordsDialog.vue # 通知记录对话框
│   │   │   ├── ProductAssignmentHistoryDialog.vue # 产品分配历史对话框
│   │   │   ├── ProductManagementDialog.vue  # 产品管理对话框
│   │   │   ├── ProductNotificationConfigDialog.vue # 产品通知配置对话框
│   │   │   ├── ShortLinkFormDialog.vue      # 短链接表单对话框
│   │   │   ├── ShortLinkManagement.vue      # 短链接管理
│   │   │   └── StatsCards.vue              # 统计卡片
│   │   ├── VirtualList.vue  # 虚拟列表
│   │   └── VirtualTable.vue # 虚拟表格
│   ├── composables/       # 组合式函数
│   │   ├── useClientForm.js       # 客户表单
│   │   ├── useClientProducts.js   # 客户产品
│   │   ├── useClientStats.js      # 客户统计
│   │   ├── useClients.js          # 客户管理
│   │   ├── useDevice.js           # 设备检测
│   │   ├── useMobileTouch.js      # 移动端触摸
│   │   ├── usePageAuth.js         # 页面权限
│   │   └── usePagination.js       # 分页
│   ├── router/            # 路由配置
│   │   └── index.js       # 路由定义
│   ├── services/          # 服务层
│   │   └── telegram_notification_service.js # Telegram通知服务
│   ├── store/             # 状态管理
│   │   └── index.js       # Pinia Store
│   ├── styles/            # 样式文件
│   │   ├── common.css     # 通用样式
│   │   ├── mobile.css     # 移动端样式
│   │   └── variables.css  # CSS变量
│   ├── utils/             # 工具函数
│   │   ├── api.js         # API封装
│   │   ├── axiosConfig.js # Axios配置
│   │   ├── crudApi.js     # CRUD API
│   │   ├── csrfToken.js   # CSRF Token
│   │   ├── date.js        # 日期工具
│   │   ├── dateFormat.js  # 日期格式化
│   │   ├── domFixes.js    # DOM修复
│   │   ├── errorFilter.js # 错误过滤
│   │   ├── globalErrorHandler.js # 全局错误处理
│   │   ├── logger.js      # 日志工具
│   │   ├── messages.js    # 消息提示
│   │   └── versionCheck.js # 版本检查
│   ├── views/             # 页面组件
│   │   ├── ad-data/       # 广告数据页面
│   │   │   ├── DailyReport.vue    # 日报表
│   │   │   └── TBSearchData.vue   # TB搜索数据
│   │   ├── admin/         # 管理页面
│   │   │   ├── UserManagement.vue              # 用户管理
│   │   │   ├── AdvertiserManagement.vue       # 广告主管理
│   │   │   ├── PublisherManagement.vue         # 渠道管理
│   │   │   ├── OfferManagement.vue            # Offer管理
│   │   │   ├── CapManagement.vue              # Cap管理
│   │   │   ├── DiscountManagement.vue         # 折扣管理
│   │   │   ├── ConversionDeductionManagement.vue # 转化扣减管理
│   │   │   ├── DeductionStats.vue             # 扣减统计
│   │   │   ├── DeductionLogs.vue              # 扣减日志
│   │   │   ├── AffiliateTest.vue              # 下游测试
│   │   │   ├── ConversionSummary.vue          # 转化统计
│   │   │   ├── PostbackManagement.vue         # Postback管理
│   │   │   ├── PostbackIpWhitelist.vue        # Postback IP白名单
│   │   │   ├── ShortLinkManagement.vue        # 短链接管理
│   │   │   ├── ClickLog.vue                  # 点击日志
│   │   │   ├── SessionManagement.vue         # 会话管理
│   │   │   ├── ScheduledTaskManagement.vue    # 定时任务管理
│   │   │   ├── AuditLogManagement.vue         # 审计日志管理
│   │   │   ├── TelegramNotificationConfig.vue  # Telegram通知配置
│   │   │   └── MLModelManagement.vue          # ML模型管理
│   │   ├── client/        # 客户页面
│   │   │   └── ClientUserManagement.vue       # 客户用户管理
│   │   ├── Login.vue      # 登录页
│   │   ├── Dashboard.vue   # 仪表盘
│   │   ├── AdData.vue     # 广告数据
│   │   ├── ApiDocumentation.vue # API文档
│   │   └── NotFound.vue   # 404页面
│   ├── App.vue            # 根组件
│   ├── main.js            # 应用入口
│   └── style.css         # 全局样式
├── index.html             # HTML模板
├── package.json           # 依赖配置
├── vite.config.js         # Vite配置
└── vite-plugin-version.js # 版本插件
```

---

## 环境配置

### 开发环境要求
- **操作系统**：Windows 10/11 或 Ubuntu 22.04
- **Python**：3.10+
- **Node.js**：16+
- **MySQL**：8.0+
- **Redis**：5.0+

### 后端环境配置

#### 1. 创建虚拟环境
```bash
# Windows
py -m venv venv
venv\Scripts\activate

# Ubuntu
python3 -m venv venv
source venv/bin/activate
```

#### 2. 安装依赖
```bash
pip install -r requirements.txt
```

#### 3. 配置环境变量
复制 `env.example` 为 `.env` 并修改配置：

```bash
# Windows
copy env.example .env

# Ubuntu
cp env.example .env
```

关键配置项：
```env
# 环境类型
PRODUCTION_ENV=development

# 安全配置
SECRET_KEY=your-secret-key-here

# 数据库配置
DATABASE_URL=mysql+aiomysql://root:password@127.0.0.1:3306/platform

# Redis配置
REDIS_HOST=127.0.0.1

# CORS配置
BACKEND_CORS_ORIGINS=http://localhost:3310

# 管理员账户
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=admin123
```

#### 4. 初始化数据库
```bash
# 创建数据库
mysql -u root -p
CREATE DATABASE platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 导入初始数据
mysql -u root -p platform < scripts/data/platform20260112.sql
```

#### 5. 启动后端服务
```bash
# 开发环境
py -m uvicorn app.main:app --reload --port 8960

# 生产环境（使用Gunicorn）
gunicorn --config gunicorn.conf.py app.main:app
```

### 前端环境配置

#### 1. 安装依赖
```bash
cd frontend
npm install
```

#### 2. 配置API地址
编辑 `frontend/src/utils/api.js`，设置后端API地址：
```javascript
const API_BASE_URL = 'http://localhost:8960/api/v1';
```

#### 3. 启动前端服务
```bash
# 开发环境
npm run dev

# 生产构建
npm run build
```

---

## 后端开发指南

### 项目结构说明

#### 1. API路由层（app/api/）
负责处理HTTP请求和响应，定义API端点。

**示例：创建新的API端点**
```python
# app/api/api_v1/endpoints/example.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.example import ExampleCreate, ExampleResponse

router = APIRouter()

@router.post("/", response_model=ExampleResponse)
async def create_example(
    example_data: ExampleCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    创建示例
    
    Args:
        example_data: 示例数据
        db: 数据库会话
        
    Returns:
        创建的示例对象
    """
    # 业务逻辑
    pass
```

**注册路由：**
```python
# app/api/api_v1/api.py
from app.api.api_v1.endpoints import example

api_router.include_router(example.router, prefix="/examples", tags=["示例管理"])
```

#### 2. 数据模型层（app/models/）
定义数据库表结构和ORM映射。

**示例：创建新的数据模型**
```python
# app/models/models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.core.utils import get_app_now_naive

class Example(Base):
    """
    示例模型
    
    表名: examples
    
    字段说明：
    - id: 主键
    - name: 名称
    - created_at: 创建时间
    """
    __tablename__ = "examples"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=get_app_now_naive)
```

#### 3. Pydantic模式层（app/schemas/）
定义请求和响应的数据验证模式。

**示例：创建Pydantic模式**
```python
# app/schemas/example.py
from pydantic import BaseModel, Field
from datetime import datetime

class ExampleBase(BaseModel):
    """示例基础模式"""
    name: str = Field(..., max_length=100, description="名称")

class ExampleCreate(ExampleBase):
    """创建示例模式"""
    pass

class ExampleResponse(ExampleBase):
    """示例响应模式"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
```

#### 4. 服务层（app/services/）
实现业务逻辑，处理数据操作。

**示例：创建服务**
```python
# app/services/example_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.models import Example
from app.schemas.example import ExampleCreate

class ExampleService:
    """示例服务"""
    
    @staticmethod
    async def create_example(
        db: AsyncSession,
        example_data: ExampleCreate
    ) -> Example:
        """
        创建示例
        
        Args:
            db: 数据库会话
            example_data: 示例数据
            
        Returns:
            创建的示例对象
        """
        db_example = Example(**example_data.model_dump())
        db.add(db_example)
        await db.commit()
        await db.refresh(db_example)
        return db_example
    
    @staticmethod
    async def get_example(
        db: AsyncSession,
        example_id: int
    ) -> Example | None:
        """
        获取示例
        
        Args:
            db: 数据库会话
            example_id: 示例ID
            
        Returns:
            示例对象或None
        """
        result = await db.execute(
            select(Example).where(Example.id == example_id)
        )
        return result.scalars().first()
```

#### 5. 核心模块（app/core/）
提供通用功能和工具。

**主要模块：**
- **config.py**：配置管理
- **database.py**：数据库连接
- **security.py**：安全相关（JWT、密码加密）
- **redis_client.py**：Redis客户端
- **cache.py**：缓存管理
- **utils.py**：工具函数

### 数据库操作

#### 异步查询示例
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.models import User

# 查询单个对象
async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalars().first()

# 查询多个对象
async def get_active_users(db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User).where(User.is_active == True)
    )
    return result.scalars().all()

# 分页查询
async def get_users_paginated(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100
) -> list[User]:
    result = await db.execute(
        select(User).offset(skip).limit(limit)
    )
    return result.scalars().all()
```

#### 创建和更新示例
```python
# 创建对象
async def create_user(db: AsyncSession, user_data: dict) -> User:
    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

# 更新对象
async def update_user(
    db: AsyncSession,
    user_id: int,
    user_data: dict
) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()
    if user:
        for key, value in user_data.items():
            setattr(user, key, value)
        await db.commit()
        await db.refresh(user)
    return user

# 删除对象
async def delete_user(db: AsyncSession, user_id: int) -> bool:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()
    if user:
        await db.delete(user)
        await db.commit()
        return True
    return False
```

### 认证和授权

#### JWT认证
```python
from fastapi import Depends, HTTPException, status
from app.core.security import JWTUtils
from app.core.dependencies import get_current_user

# 获取当前用户
@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """获取当前用户信息"""
    return current_user

# 管理员权限检查
@router.get("/admin-only")
async def admin_only_endpoint(
    current_user: User = Depends(get_current_user)
):
    """仅管理员可访问"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    return {"message": "管理员访问成功"}
```

### 定时任务开发

#### 创建定时任务
```python
# app/scheduler_module/tasks/example_task.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def example_task():
    """
    示例定时任务
    
    功能说明：
    - 每天凌晨执行
    - 清理过期数据
    """
    try:
        logger.info(f"开始执行示例任务: {datetime.now()}")
        
        # 任务逻辑
        pass
        
        logger.info("示例任务执行完成")
    except Exception as e:
        logger.error(f"示例任务执行失败: {e}")
        raise
```

#### 注册定时任务
```python
# app/scheduler_module/task_init.py
from app.scheduler_module.tasks import example_task

def init_scheduled_tasks_in_db():
    """
    初始化定时任务到数据库
    
    在应用启动时调用，确保数据库中有任务配置
    """
    tasks = [
        {
            "name": "example_task",
            "description": "示例定时任务",
            "cron_expression": "0 0 * * *",  # 每天凌晨
            "task_path": "app.scheduler_module.tasks.example_task:example_task",
            "is_active": True
        }
    ]
    # 注册任务到数据库
    pass
```

### 错误处理

#### 自定义异常
```python
from app.core.errors import ErrorCode, create_error_response

# 抛出业务异常
@router.post("/example")
async def example_endpoint():
    raise create_error_response(
        ErrorCode.VALIDATION_ERROR,
        "数据验证失败"
    )
```

#### 全局异常处理
```python
# app/main.py
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"}
    )
```

---

## 前端开发指南

### 项目结构说明

#### 1. API接口层（src/api/）
封装后端API调用。

**示例：创建API接口**
```javascript
// src/api/example.js
import request from '../utils/api';

/**
 * 获取示例列表
 * @param {Object} params - 查询参数
 * @returns {Promise} 返回示例列表
 */
export const getExamples = (params) => {
  return request({
    url: '/examples',
    method: 'get',
    params
  });
};

/**
 * 创建示例
 * @param {Object} data - 示例数据
 * @returns {Promise} 返回创建的示例
 */
export const createExample = (data) => {
  return request({
    url: '/examples',
    method: 'post',
    data
  });
};
```

#### 2. 组件层（src/components/）
可复用的Vue组件。

**示例：创建组件**
```vue
<!-- src/components/ExampleComponent.vue -->
<template>
  <div class="example-component">
    <h3>{{ title }}</h3>
    <slot></slot>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue';

// 定义props
const props = defineProps({
  title: {
    type: String,
    default: '默认标题'
  }
});

// 定义emits
const emit = defineEmits(['update', 'delete']);

// 组件逻辑
const handleClick = () => {
  emit('update', { id: 1 });
};
</script>

<style scoped>
.example-component {
  padding: 20px;
  border: 1px solid #ddd;
}
</style>
```

#### 3. 页面层（src/views/）
页面级组件。

**示例：创建页面**
```vue
<!-- src/views/ExamplePage.vue -->
<template>
  <div class="example-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>示例页面</span>
          <el-button type="primary" @click="handleAdd">新增</el-button>
        </div>
      </template>
      
      <el-table :data="tableData" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { getExamples, deleteExample } from '../api/example';
import { ElMessage, ElMessageBox } from 'element-plus';

// 响应式数据
const tableData = ref([]);
const loading = ref(false);

// 获取列表
const fetchData = async () => {
  loading.value = true;
  try {
    const res = await getExamples();
    tableData.value = res.data;
  } catch (error) {
    ElMessage.error('获取数据失败');
  } finally {
    loading.value = false;
  }
};

// 新增
const handleAdd = () => {
  // 打开新增对话框
};

// 编辑
const handleEdit = (row) => {
  // 打开编辑对话框
};

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除吗？', '提示', {
      type: 'warning'
    });
    await deleteExample(row.id);
    ElMessage.success('删除成功');
    fetchData();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

// 生命周期
onMounted(() => {
  fetchData();
});
</script>
```

#### 4. 组合式函数（src/composables/）
可复用的逻辑函数。

**示例：创建组合式函数**
```javascript
// src/composables/usePagination.js
import { ref, computed } from 'vue';

export function usePagination(fetchData) {
  // 分页参数
  const currentPage = ref(1);
  const pageSize = ref(10);
  const total = ref(0);

  // 计算偏移量
  const offset = computed(() => {
    return (currentPage.value - 1) * pageSize.value;
  });

  // 获取数据
  const loadData = async () => {
    await fetchData({
      skip: offset.value,
      limit: pageSize.value
    });
  };

  // 改变页码
  const handlePageChange = (page) => {
    currentPage.value = page;
    loadData();
  };

  // 改变每页数量
  const handleSizeChange = (size) => {
    pageSize.value = size;
    currentPage.value = 1;
    loadData();
  };

  return {
    currentPage,
    pageSize,
    total,
    loadData,
    handlePageChange,
    handleSizeChange
  };
}
```

#### 5. 状态管理（src/store/）
使用Pinia进行状态管理。

**示例：创建Store**
```javascript
// src/store/example.js
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getExamples } from '../api/example';

export const useExampleStore = defineStore('example', () => {
  // 状态
  const examples = ref([]);
  const loading = ref(false);

  // 计算属性
  const totalCount = computed(() => examples.value.length);

  // 操作
  const fetchExamples = async () => {
    loading.value = true;
    try {
      const res = await getExamples();
      examples.value = res.data;
    } catch (error) {
      console.error('获取示例失败:', error);
    } finally {
      loading.value = false;
    }
  };

  const addExample = (example) => {
    examples.value.push(example);
  };

  const updateExample = (id, data) => {
    const index = examples.value.findIndex(e => e.id === id);
    if (index !== -1) {
      examples.value[index] = { ...examples.value[index], ...data };
    }
  };

  const deleteExample = (id) => {
    examples.value = examples.value.filter(e => e.id !== id);
  };

  return {
    examples,
    loading,
    totalCount,
    fetchExamples,
    addExample,
    updateExample,
    deleteExample
  };
});
```

### 路由配置

#### 添加新路由
```javascript
// src/router/index.js
import { createAsyncComponent } from './index';

const ExamplePage = createAsyncComponent(
  () => import('../views/ExamplePage.vue'),
  'ExamplePage'
);

const routes = [
  {
    path: '/app/example',
    name: 'Example',
    component: ExamplePage,
    meta: { 
      requiresAuth: true,
      requiresAdmin: false  // 是否需要管理员权限
    }
  }
];
```

### API请求封装

#### 统一请求处理
```javascript
// src/utils/api.js
import axios from 'axios';
import { ElMessage } from 'element-plus';
import { useAuthStore } from '../store';

// 创建axios实例
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8960/api/v1',
  timeout: 30000
});

// 请求拦截器
request.interceptors.request.use(
  config => {
    const authStore = useAuthStore();
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data;
  },
  error => {
    if (error.response) {
      const { status, data } = error.response;
      
      switch (status) {
        case 401:
          ElMessage.error('登录已过期，请重新登录');
          // 跳转到登录页
          break;
        case 403:
          ElMessage.error('权限不足');
          break;
        case 404:
          ElMessage.error('请求的资源不存在');
          break;
        case 500:
          ElMessage.error('服务器错误');
          break;
        default:
          ElMessage.error(data.detail || '请求失败');
      }
    } else {
      ElMessage.error('网络错误');
    }
    
    return Promise.reject(error);
  }
);

export default request;
```

### Element Plus使用

#### 表单示例
```vue
<template>
  <el-form 
    ref="formRef" 
    :model="formData" 
    :rules="formRules"
    label-width="120px"
  >
    <el-form-item label="用户名" prop="username">
      <el-input v-model="formData.username" placeholder="请输入用户名" />
    </el-form-item>
    
    <el-form-item label="邮箱" prop="email">
      <el-input v-model="formData.email" placeholder="请输入邮箱" />
    </el-form-item>
    
    <el-form-item>
      <el-button type="primary" @click="handleSubmit">提交</el-button>
      <el-button @click="handleReset">重置</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { ref, reactive } from 'vue';
import { ElMessage } from 'element-plus';

const formRef = ref(null);

const formData = reactive({
  username: '',
  email: ''
});

const formRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '长度在3到50个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ]
};

const handleSubmit = async () => {
  try {
    await formRef.value.validate();
    // 提交逻辑
    ElMessage.success('提交成功');
  } catch (error) {
    ElMessage.error('表单验证失败');
  }
};

const handleReset = () => {
  formRef.value.resetFields();
};
</script>
```

#### 表格示例
```vue
<template>
  <el-table 
    :data="tableData" 
    v-loading="loading"
    border
    stripe
  >
    <el-table-column type="selection" width="55" />
    <el-table-column prop="id" label="ID" width="80" />
    <el-table-column prop="name" label="名称" />
    <el-table-column prop="status" label="状态">
      <template #default="{ row }">
        <el-tag :type="row.status ? 'success' : 'danger'">
          {{ row.status ? '启用' : '禁用' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="200">
      <template #default="{ row }">
        <el-button size="small" @click="handleEdit(row)">编辑</el-button>
        <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
      </template>
    </el-table-column>
  </el-table>
  
  <el-pagination
    v-model:current-page="currentPage"
    v-model:page-size="pageSize"
    :total="total"
    :page-sizes="[10, 20, 50, 100]"
    layout="total, sizes, prev, pager, next, jumper"
    @size-change="handleSizeChange"
    @current-change="handlePageChange"
  />
</template>
```

---

## 数据库设计

### 核心表结构

#### 1. 用户表（users）
```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名称(登录名称)',
    hashed_password VARCHAR(191) NOT NULL COMMENT '用户Hash密码',
    full_name VARCHAR(100) COMMENT '用户全名',
    email VARCHAR(100) UNIQUE COMMENT '用户邮箱',
    role ENUM('admin', 'client') NOT NULL DEFAULT 'client' COMMENT '用户角色',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    login_restricted BOOLEAN DEFAULT FALSE COMMENT '是否限制登录',
    login_message TEXT COMMENT '登录提示消息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_username (username),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';
```

#### 2. 客户表（clients）
```sql
CREATE TABLE clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '关联用户ID',
    client_name VARCHAR(100) NOT NULL COMMENT '客户名称',
    client_code VARCHAR(50) UNIQUE COMMENT '客户代码',
    contact_person VARCHAR(100) COMMENT '联系人',
    contact_email VARCHAR(100) COMMENT '联系邮箱',
    contact_phone VARCHAR(20) COMMENT '联系电话',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_client_code (client_code),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户表';
```

#### 3. 广告主表（advertisers）
```sql
CREATE TABLE advertisers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    advertiser_name VARCHAR(100) NOT NULL COMMENT '广告主名称',
    advertiser_code VARCHAR(50) UNIQUE COMMENT '广告主代码',
    contact_person VARCHAR(100) COMMENT '联系人',
    contact_email VARCHAR(100) COMMENT '联系邮箱',
    contact_phone VARCHAR(20) COMMENT '联系电话',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_advertiser_code (advertiser_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='广告主表';
```

#### 4. 渠道表（publishers）
```sql
CREATE TABLE publishers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    publisher_name VARCHAR(100) NOT NULL COMMENT '渠道名称',
    publisher_code VARCHAR(50) UNIQUE COMMENT '渠道代码',
    contact_person VARCHAR(100) COMMENT '联系人',
    contact_email VARCHAR(100) COMMENT '联系邮箱',
    contact_phone VARCHAR(20) COMMENT '联系电话',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_publisher_code (publisher_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='渠道表';
```

#### 5. Offer表（offers）
```sql
CREATE TABLE offers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    offer_name VARCHAR(200) NOT NULL COMMENT 'Offer名称',
    offer_code VARCHAR(50) UNIQUE COMMENT 'Offer代码',
    advertiser_id INT NOT NULL COMMENT '关联广告主ID',
    payout DECIMAL(10, 2) NOT NULL COMMENT '单价',
    currency VARCHAR(10) DEFAULT 'USD' COMMENT '货币',
    country VARCHAR(10) COMMENT '国家代码',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE CASCADE,
    INDEX idx_offer_code (offer_code),
    INDEX idx_advertiser_id (advertiser_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Offer表';
```

#### 6. Cap表（offer_caps）
```sql
CREATE TABLE offer_caps (
    id INT AUTO_INCREMENT PRIMARY KEY,
    offer_id INT NOT NULL COMMENT '关联Offer ID',
    publisher_id INT COMMENT '关联渠道ID（NULL表示所有渠道）',
    advertiser_id INT COMMENT '关联广告主ID（用于advertiser_offer类型）',
    cap_type ENUM('offer', 'advertiser_offer') NOT NULL DEFAULT 'offer' COMMENT 'Cap类型',
    daily_cap INT COMMENT '每日上限',
    total_cap INT COMMENT '总上限',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE,
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    UNIQUE KEY uk_offer_publisher (offer_id, publisher_id, cap_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Cap表';
```

#### 7. Postback转化表（postback_conversions）
```sql
CREATE TABLE postback_conversions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    click_id VARCHAR(100) NOT NULL COMMENT '点击ID',
    offer_id INT NOT NULL COMMENT '关联Offer ID',
    publisher_id INT NOT NULL COMMENT '关联渠道ID',
    advertiser_id INT NOT NULL COMMENT '关联广告主ID',
    conversion_time DATETIME NOT NULL COMMENT '转化时间',
    payout DECIMAL(10, 2) COMMENT '单价',
    status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending' COMMENT '状态',
    is_deducted BOOLEAN DEFAULT FALSE COMMENT '是否已扣量',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE CASCADE,
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id) ON DELETE CASCADE,
    INDEX idx_click_id (click_id),
    INDEX idx_offer_id (offer_id),
    INDEX idx_publisher_id (publisher_id),
    INDEX idx_conversion_time (conversion_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Postback转化表';
```

#### 8. 短链接表（short_links）
```sql
CREATE TABLE short_links (
    id INT AUTO_INCREMENT PRIMARY KEY,
    short_code VARCHAR(20) NOT NULL UNIQUE COMMENT '短链接代码',
    original_url TEXT NOT NULL COMMENT '原始URL',
    offer_id INT COMMENT '关联Offer ID',
    publisher_id INT COMMENT '关联渠道ID',
    click_count INT DEFAULT 0 COMMENT '点击次数',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    expires_at DATETIME COMMENT '过期时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE SET NULL,
    INDEX idx_short_code (short_code),
    INDEX idx_offer_id (offer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短链接表';
```

### 数据库优化建议

#### 1. 索引优化
```sql
-- 为常用查询字段添加索引
CREATE INDEX idx_conversion_status ON postback_conversions(status);
CREATE INDEX idx_conversion_deducted ON postback_conversions(is_deducted);
CREATE INDEX idx_client_active ON clients(is_active);
CREATE INDEX idx_offer_active ON offers(is_active);
```

#### 2. 分区表
```sql
-- 对大表进行分区（如postback_conversions按月分区）
ALTER TABLE postback_conversions 
PARTITION BY RANGE (YEAR(conversion_time) * 100 + MONTH(conversion_time)) (
    PARTITION p202501 VALUES LESS THAN (202502),
    PARTITION p202502 VALUES LESS THAN (202503),
    PARTITION p202503 VALUES LESS THAN (202504),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

#### 3. 查询优化
```sql
-- 使用EXPLAIN分析查询
EXPLAIN SELECT * FROM postback_conversions 
WHERE offer_id = 1 AND conversion_time >= '2025-01-01';

-- 优化JOIN查询
SELECT pc.*, o.offer_name, p.publisher_name
FROM postback_conversions pc
INNER JOIN offers o ON pc.offer_id = o.id
INNER JOIN publishers p ON pc.publisher_id = p.id
WHERE pc.status = 'approved'
LIMIT 100;
```

---

## 部署指南

### 生产环境配置

#### 1. 服务器要求
- **操作系统**：Ubuntu 22.04 LTS
- **CPU**：2核+
- **内存**：4GB+
- **磁盘**：50GB+
- **网络**：公网IP

#### 2. 安装系统依赖
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装Python 3.10
sudo apt install python3.10 python3.10-venv python3-pip -y

# 安装MySQL 8.0
sudo apt install mysql-server -y

# 安装Redis
sudo apt install redis-server -y

# 安装Nginx
sudo apt install nginx -y

# 安装Git
sudo apt install git -y
```

#### 3. 配置MySQL
```bash
# 启动MySQL
sudo systemctl start mysql
sudo systemctl enable mysql

# 安全配置
sudo mysql_secure_installation

# 创建数据库和用户
sudo mysql -u root -p
```

```sql
-- 创建数据库
CREATE DATABASE platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户
CREATE USER 'platform'@'localhost' IDENTIFIED BY 'your_secure_password';

-- 授权
GRANT ALL PRIVILEGES ON platform.* TO 'platform'@'localhost';
FLUSH PRIVILEGES;

-- 导入初始数据
USE platform;
SOURCE /data/Platform/scripts/data/platform20260112.sql;
```

#### 4. 配置Redis
```bash
# 启动Redis
sudo systemctl start redis
sudo systemctl enable redis

# 测试连接
redis-cli ping
```

#### 5. 部署后端
```bash
# 克隆代码
cd /data
git clone <repository-url> Platform
cd Platform

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp env.example .env
nano .env
```

编辑 `.env` 文件，设置生产环境配置：
```env
PRODUCTION_ENV=production
SECRET_KEY=your-production-secret-key
DATABASE_URL=mysql+aiomysql://platform:password@127.0.0.1:3306/platform
REDIS_HOST=127.0.0.1
BACKEND_CORS_ORIGINS=https://your-domain.com
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=your-secure-password
```

```bash
# 生成RSA密钥
python scripts/生成RSA密钥/generate_rsa_keys.py --output-dir keys

# 设置权限
sudo chown -R www-data:www-data /data/Platform
sudo chmod -R 755 /data/Platform
sudo chmod 600 /data/Platform/.env
sudo chmod 700 /data/Platform/keys

# 配置systemd服务
sudo cp systemd/Platform-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable Platform-backend
sudo systemctl start Platform-backend

# 查看状态
sudo systemctl status Platform-backend
```

#### 6. 部署前端
```bash
# 安装Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 构建前端
cd /data/Platform/frontend
npm install
npm run build

# 配置Nginx
sudo nano /etc/nginx/sites-available/platform
```

Nginx配置示例：
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL证书配置
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 前端静态文件
    location / {
        root /data/Platform/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # 后端API代理
    location /api/ {
        proxy_pass http://127.0.0.1:8960;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Postback回调代理
    location /postback/ {
        proxy_pass http://127.0.0.1:8960;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 短链接代理
    location /s/ {
        proxy_pass http://127.0.0.1:8960;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/platform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 获取SSL证书
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

#### 7. 配置防火墙
```bash
# 配置UFW防火墙
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

#### 8. 配置日志轮转
```bash
# 创建日志轮转配置
sudo nano /etc/logrotate.d/platform
```

```
/data/Platform/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload Platform-backend
    endscript
}
```

### 监控和维护

#### 1. 查看日志
```bash
# 后端日志
sudo journalctl -u Platform-backend -f

# Gunicorn日志
tail -f /data/Platform/logs/gunicorn_error.log

# 应用日志
tail -f /data/Platform/logs/app.log

# Nginx日志
tail -f /var/log/nginx/error.log
```

#### 2. 重启服务
```bash
# 重启后端
sudo systemctl restart Platform-backend

# 重启Nginx
sudo systemctl restart nginx

# 重启MySQL
sudo systemctl restart mysql

# 重启Redis
sudo systemctl restart redis
```

#### 3. 数据库备份
```bash
# 创建备份脚本
nano /data/Platform/scripts/backup.sh
```

```bash
#!/bin/bash
# 数据库备份脚本

BACKUP_DIR="/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="platform"
DB_USER="platform"
DB_PASS="your_password"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
mysqldump -u $DB_USER -p$DB_PASS $DB_NAME | gzip > $BACKUP_DIR/platform_$DATE.sql.gz

# 删除7天前的备份
find $BACKUP_DIR -name "platform_*.sql.gz" -mtime +7 -delete

echo "Backup completed: platform_$DATE.sql.gz"
```

```bash
# 设置执行权限
chmod +x /data/Platform/scripts/backup.sh

# 添加定时任务
crontab -e
```

```
# 每天凌晨2点备份数据库
0 2 * * * /data/Platform/scripts/backup.sh >> /data/Platform/logs/backup.log 2>&1
```

#### 4. 性能监控
```bash
# 查看系统资源
htop

# 查看MySQL性能
sudo mysqladmin -u root -p status

# 查看Redis性能
redis-cli info stats

# 查看Nginx状态
curl http://localhost/nginx_status
```

---

## 开发规范

### 代码风格

#### Python代码规范
```python
# 使用类型注解
from typing import Optional, List
from datetime import datetime

async def get_user(
    db: AsyncSession,
    user_id: int
) -> Optional[User]:
    """
    获取用户
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        
    Returns:
        用户对象或None
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalars().first()
```

#### JavaScript代码规范
```javascript
// 使用ES6+语法
import { ref, onMounted } from 'vue';

// 使用箭头函数
const fetchData = async () => {
  try {
    const res = await getExamples();
    tableData.value = res.data;
  } catch (error) {
    console.error('获取数据失败:', error);
  }
};

// 使用解构赋值
const { currentPage, pageSize, total } = usePagination(fetchData);
```

### 命名规范

#### Python命名
- **类名**：大驼峰（PascalCase）- `UserService`
- **函数名**：小写下划线（snake_case）- `get_user_by_id`
- **变量名**：小写下划线（snake_case）- `user_id`
- **常量名**：大写下划线（UPPER_SNAKE_CASE）- `MAX_RETRY_COUNT`

#### JavaScript命名
- **组件名**：大驼峰（PascalCase）- `UserManagement`
- **函数名**：小驼峰（camelCase）- `getUserById`
- **变量名**：小驼峰（camelCase）- `userId`
- **常量名**：大写下划线（UPPER_SNAKE_CASE）- `MAX_RETRY_COUNT`

### 注释规范

#### Python注释
```python
def calculate_cap(
    daily_cap: int,
    current_count: int
) -> bool:
    """
    检查是否达到Cap限制
    
    Args:
        daily_cap: 每日上限
        current_count: 当前计数
        
    Returns:
        是否达到上限
        
    Example:
        >>> calculate_cap(100, 99)
        False
        >>> calculate_cap(100, 100)
        True
    """
    return current_count >= daily_cap
```

#### JavaScript注释
```javascript
/**
 * 获取用户列表
 * 
 * @param {Object} params - 查询参数
 * @param {number} params.page - 页码
 * @param {number} params.pageSize - 每页数量
 * @returns {Promise<Array>} 用户列表
 * 
 * @example
 * const users = await getUsers({ page: 1, pageSize: 10 });
 */
export const getUsers = (params) => {
  return request({
    url: '/users',
    method: 'get',
    params
  });
};
```

### Git提交规范

#### 提交信息格式
```
<type>(<scope>): <subject>

<body>

<footer>
```

#### Type类型
- `feat`：新功能
- `fix`：修复bug
- `docs`：文档更新
- `style`：代码格式调整
- `refactor`：重构
- `test`：测试相关
- `chore`：构建过程或辅助工具的变动

#### 示例
```
feat(user): 添加用户管理功能

- 添加用户列表页面
- 添加用户创建和编辑功能
- 添加用户删除功能

Closes #123
```

### 测试规范

#### 单元测试
```python
# tests/test_user_service.py
import pytest
from app.services.user_service import UserService

@pytest.mark.asyncio
async def test_create_user(db_session):
    """测试创建用户"""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "role": "client"
    }
    user = await UserService.create_user(db_session, user_data)
    assert user.username == "testuser"
    assert user.email == "test@example.com"

@pytest.mark.asyncio
async def test_get_user_not_found(db_session):
    """测试获取不存在的用户"""
    user = await UserService.get_user_by_id(db_session, 999)
    assert user is None
```

#### 集成测试
```javascript
// tests/integration/user.spec.js
import { describe, it, expect } from 'vitest';
import { getUsers, createUser } from '@/api/user';

describe('用户API集成测试', () => {
  it('应该获取用户列表', async () => {
    const users = await getUsers({ page: 1, pageSize: 10 });
    expect(users).toBeDefined();
    expect(Array.isArray(users.data)).toBe(true);
  });

  it('应该创建新用户', async () => {
    const userData = {
      username: 'testuser',
      email: 'test@example.com'
    };
    const user = await createUser(userData);
    expect(user.username).toBe('testuser');
  });
});
```

---

## 常见问题

### 后端问题

#### 1. 数据库连接失败
**问题**：`Can't connect to MySQL server`
**解决方案**：
```bash
# 检查MySQL服务状态
sudo systemctl status mysql

# 检查数据库配置
sudo nano /data/Platform/.env
# 确认DATABASE_URL配置正确

# 测试连接
mysql -u platform -p -h 127.0.0.1 platform
```

#### 2. Redis连接失败
**问题**：`Redis connection error`
**解决方案**：
```bash
# 检查Redis服务状态
sudo systemctl status redis

# 测试连接
redis-cli ping

# 检查配置
sudo nano /data/Platform/.env
# 确认REDIS_HOST配置正确
```

#### 3. JWT验证失败
**问题**：`Invalid token`
**解决方案**：
```bash
# 检查密钥配置
sudo nano /data/Platform/.env
# 确认SECRET_KEY配置正确

# 检查RSA密钥
ls -la /data/Platform/keys/
# 确认密钥文件存在且权限正确

# 重新生成密钥
python scripts/生成RSA密钥/generate_rsa_keys.py --output-dir keys
```

#### 4. 定时任务不执行
**问题**：定时任务没有按预期执行
**解决方案**：
```bash
# 检查调度器状态
sudo journalctl -u Platform-backend | grep scheduler

# 检查任务配置
mysql -u platform -p platform
SELECT * FROM scheduled_tasks WHERE is_active = 1;

# 手动触发任务测试
# 在管理界面点击"立即执行"按钮
```

### 前端问题

#### 1. API请求失败
**问题**：`Network Error` 或 `401 Unauthorized`
**解决方案**：
```javascript
// 检查API地址配置
// frontend/src/utils/api.js
const API_BASE_URL = 'http://localhost:8960/api/v1';

// 检查Token是否过期
// 清除本地存储重新登录
localStorage.clear();
sessionStorage.clear();
```

#### 2. 路由跳转失败
**问题**：页面无法访问或404错误
**解决方案**：
```javascript
// 检查路由配置
// frontend/src/router/index.js
// 确认路由路径和组件配置正确

// 检查权限配置
// 确认meta.requiresAuth和meta.requiresAdmin配置正确
```

#### 3. 样式问题
**问题**：页面样式显示异常
**解决方案**：
```vue
<!-- 检查scoped样式 -->
<style scoped>
/* 确保使用scoped避免样式污染 */
.example {
  padding: 20px;
}
</style>

<!-- 检查Element Plus版本 -->
npm list element-plus
```

### 部署问题

#### 1. Nginx 502 Bad Gateway
**问题**：访问网站时出现502错误
**解决方案**：
```bash
# 检查后端服务状态
sudo systemctl status Platform-backend

# 检查Nginx配置
sudo nginx -t

# 检查端口是否监听
sudo netstat -tlnp | grep 8960

# 查看Nginx错误日志
sudo tail -f /var/log/nginx/error.log
```

#### 2. SSL证书问题
**问题**：HTTPS无法访问或证书过期
**解决方案**：
```bash
# 续期证书
sudo certbot renew

# 强制续期
sudo certbot renew --force-renewal

# 检查证书有效期
sudo certbot certificates
```

#### 3. 磁盘空间不足
**问题**：服务器磁盘空间不足导致服务异常
**解决方案**：
```bash
# 检查磁盘使用情况
df -h

# 清理日志文件
sudo find /data/Platform/logs -name "*.log" -mtime +30 -delete

# 清理旧备份
sudo find /data/backups -name "*.sql.gz" -mtime +30 -delete

# 清理APT缓存
sudo apt clean
sudo apt autoremove
```

### 性能问题

#### 1. 数据库查询慢
**问题**：页面加载缓慢，数据库查询耗时
**解决方案**：
```sql
-- 分析慢查询
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';

-- 启用慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 2;

-- 查看慢查询
sudo tail -f /var/log/mysql/slow.log

-- 使用EXPLAIN分析查询
EXPLAIN SELECT * FROM postback_conversions WHERE offer_id = 1;

-- 添加索引
CREATE INDEX idx_offer_id ON postback_conversions(offer_id);
```

#### 2. 内存占用过高
**问题**：服务器内存占用过高
**解决方案**：
```bash
# 查看内存使用情况
free -h

# 查看进程内存占用
ps aux --sort=-%mem | head

# 调整Gunicorn worker数量
sudo nano /data/Platform/.env
# 设置WORKERS=2

# 重启服务
sudo systemctl restart Platform-backend
```

#### 3. 并发处理能力不足
**问题**：高并发时响应缓慢
**解决方案**：
```bash
# 增加worker数量
sudo nano /data/Platform/.env
# 设置WORKERS=4

# 调整数据库连接池
sudo nano /data/Platform/.env
# 设置DB_POOL_SIZE=20
# 设置DB_MAX_OVERFLOW=10

# 启用Redis缓存
sudo nano /data/Platform/.env
# 确认REDIS_HOST配置正确

# 重启服务
sudo systemctl restart Platform-backend
```

---

## Docker部署指南

### Docker Compose部署（推荐）

#### 1. 创建Docker配置文件

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  # MySQL数据库
  mysql:
    image: mysql:8.0
    container_name: platform-mysql
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: platform
      MYSQL_USER: platform
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./scripts/data:/docker-entrypoint-initdb.d
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
    networks:
      - platform-network

  # Redis缓存
  redis:
    image: redis:7-alpine
    container_name: platform-redis
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - platform-network

  # 后端API
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: platform-backend
    restart: always
    ports:
      - "8960:8960"
    environment:
      - PRODUCTION_ENV=production
      - DATABASE_URL=mysql+aiomysql://platform:${MYSQL_PASSWORD}@mysql:3306/platform
      - REDIS_HOST=redis
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - ./logs:/app/logs
      - ./keys:/app/keys
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # 前端
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: platform-frontend
    restart: always
    ports:
      - "3310:80"
    depends_on:
      - backend
    networks:
      - platform-network

  # Nginx反向代理
  nginx:
    image: nginx:alpine
    container_name: platform-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx:/etc/nginx/conf.d
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - frontend
      - backend
    networks:
      - platform-network

volumes:
  mysql_data:
  redis_data:

networks:
  platform-network:
    driver: bridge
```

#### 2. 创建后端Dockerfile

创建 `Dockerfile.backend`：

```dockerfile
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY models/ ./models/
COPY scripts/ ./scripts/

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口
EXPOSE 8960

# 启动命令
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.main:app"]
```

#### 3. 创建前端Dockerfile

创建 `frontend/Dockerfile`：

```dockerfile
# 构建阶段
FROM node:18-alpine as build

WORKDIR /app

# 复制依赖文件
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制源代码
COPY . .

# 构建应用
RUN npm run build

# 生产阶段
FROM nginx:alpine

# 复制构建产物
COPY --from=build /app/dist /usr/share/nginx/html

# 复制Nginx配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 启动Nginx
CMD ["nginx", "-g", "daemon off;"]
```

#### 4. 创建环境变量文件

创建 `.env.docker`：

```env
# MySQL配置
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_PASSWORD=your_mysql_password

# 应用配置
SECRET_KEY=your-secret-key-here
```

#### 5. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart
```

### Windows本地开发Docker

#### 1. 使用Docker Desktop

```bash
# 启动Docker Desktop

# 克隆项目
cd E:\data\Platform

# 创建开发环境配置
python scripts/自动生成配置/auto_generate_env_config.py --env development --no-interactive

# 启动开发服务
docker-compose -f docker-compose.dev.yml up -d
```

#### 2. 开发环境docker-compose.dev.yml

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: platform-mysql-dev
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: platform
      MYSQL_USER: platform
      MYSQL_PASSWORD: platform
    ports:
      - "3306:3306"
    volumes:
      - mysql_dev_data:/var/lib/mysql
      - ./scripts/data:/docker-entrypoint-initdb.d

  redis:
    image: redis:7-alpine
    container_name: platform-redis-dev
    ports:
      - "6379:6379"

volumes:
  mysql_dev_data:
```

### Ubuntu生产环境Docker

#### 1. 部署步骤

```bash
# 1. 安装Docker和Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

sudo usermod -aG docker $USER

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 2. 克隆项目
cd /data
git clone <repository-url> Platform
cd Platform

# 3. 生成环境配置
sudo python3 scripts/自动生成配置/auto_generate_env_config.py --env production --no-interactive

# 4. 生成RSA密钥
python scripts/生成RSA密钥/generate_rsa_keys.py --output-dir keys

# 5. 创建生产环境配置
cp .env.docker .env.production
nano .env.production

# 6. 启动服务
docker-compose -f docker-compose.prod.yml up -d

# 7. 查看服务状态
docker-compose ps

# 8. 查看日志
docker-compose logs -f backend
```

#### 2. 生产环境docker-compose.prod.yml

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: platform-mysql-prod
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: platform
      MYSQL_USER: platform
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "127.0.0.1:3306:3306"
    volumes:
      - mysql_prod_data:/var/lib/mysql
      - ./backups:/backups
    networks:
      - platform-network

  redis:
    image: redis:7-alpine
    container_name: platform-redis-prod
    restart: always
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_prod_data:/data
    networks:
      - platform-network

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: platform-backend-prod
    restart: always
    ports:
      - "127.0.0.1:8960:8960"
    env_file:
      - .env.production
    volumes:
      - ./logs:/app/logs
      - ./keys:/app/keys
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: platform-frontend-prod
    restart: always
    ports:
      - "127.0.0.1:3310:80"
    depends_on:
      - backend
    networks:
      - platform-network

  nginx:
    image: nginx:alpine
    container_name: platform-nginx-prod
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx:/etc/nginx/conf.d
      - ./ssl:/etc/nginx/ssl
      - ./logs/nginx:/var/log/nginx
    depends_on:
      - frontend
      - backend
    networks:
      - platform-network

volumes:
  mysql_prod_data:
  redis_prod_data:

networks:
  platform-network:
    driver: bridge
```

### Docker常用命令

```bash
# 查看运行中的容器
docker ps

# 查看所有容器
docker ps -a

# 查看容器日志
docker logs -f platform-backend-prod

# 进入容器
docker exec -it platform-backend-prod /bin/bash

# 停止容器
docker stop platform-backend-prod

# 启动容器
docker start platform-backend-prod

# 重启容器
docker restart platform-backend-prod

# 删除容器
docker rm platform-backend-prod

# 查看镜像
docker images

# 删除镜像
docker rmi <image-id>

# 清理未使用的资源
docker system prune -a

# 查看容器资源使用
docker stats
```

---

## 微服务架构设计

### 架构概述

将单体应用拆分为多个独立的服务，每个服务负责特定的业务功能，通过API网关统一对外提供服务。

### 服务拆分方案

#### 1. 核心服务

```
platform-core/          # 核心服务（用户、认证、权限）
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── auth/
│   │       └── users/
│   ├── services/
│   │   ├── user_service.py
│   │   └── auth_service.py
│   └── models/
│       └── user.py
├── Dockerfile
└── requirements-core.txt

platform-cpl/           # CPL服务（广告主、渠道、Offer、Cap）
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── advertisers/
│   │       ├── publishers/
│   │       ├── offers/
│   │       └── caps/
│   ├── services/
│   │   ├── advertiser_service.py
│   │   ├── publisher_service.py
│   │   ├── offer_service.py
│   │   └── cap_service.py
│   └── models/
│       ├── advertiser.py
│       ├── publisher.py
│       └── offer.py
├── Dockerfile
└── requirements-cpl.txt

platform-tracking/      # 追踪服务（点击、短链接）
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── tracking/
│   │       └── short_links/
│   ├── services/
│   │   ├── tracking_service.py
│   │   └── short_link_service.py
│   └── models/
│       ├── click.py
│       └── short_link.py
├── Dockerfile
└── requirements-tracking.txt

platform-postback/      # Postback服务（转化回调）
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       └── postback/
│   ├── services/
│   │   └── postback_service.py
│   └── models/
│       └── conversion.py
├── Dockerfile
└── requirements-postback.txt

platform-analytics/     # 数据分析服务（报表、统计）
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── dashboard/
│   │       └── reports/
│   ├── services/
│   │   ├── dashboard_service.py
│   │   └── report_service.py
│   └── models/
│       └── analytics.py
├── Dockerfile
└── requirements-analytics.txt

platform-notification/  # 通知服务（Telegram、邮件）
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       └── notification/
│   ├── services/
│   │   ├── telegram_service.py
│   │   └── email_service.py
│   └── models/
│       └── notification.py
├── Dockerfile
└── requirements-notification.txt
```

#### 2. 共享模块

```
platform-shared/        # 共享模块
├── core/
│   ├── config.py
│   ├── database.py
│   ├── redis_client.py
│   ├── security.py
│   └── utils.py
├── models/
│   └── base.py
├── schemas/
│   └── base.py
└── requirements-shared.txt
```

#### 3. API网关

```
platform-gateway/       # API网关
├── app/
│   ├── main.py
│   ├── routes/
│   │   ├── core.py
│   │   ├── cpl.py
│   │   ├── tracking.py
│   │   ├── postback.py
│   │   ├── analytics.py
│   │   └── notification.py
│   └── middleware/
│       ├── auth.py
│       ├── rate_limit.py
│       └── logging.py
├── Dockerfile
└── requirements-gateway.txt
```

### Docker Compose配置

```yaml
version: '3.8'

services:
  # API网关
  gateway:
    build:
      context: ./platform-gateway
      dockerfile: Dockerfile
    container_name: platform-gateway
    restart: always
    ports:
      - "8960:8960"
    environment:
      - CORE_SERVICE_URL=http://core:8961
      - CPL_SERVICE_URL=http://cpl:8962
      - TRACKING_SERVICE_URL=http://tracking:8963
      - POSTBACK_SERVICE_URL=http://postback:8964
      - ANALYTICS_SERVICE_URL=http://analytics:8965
      - NOTIFICATION_SERVICE_URL=http://notification:8966
    networks:
      - platform-network

  # 核心服务
  core:
    build:
      context: ./platform-core
      dockerfile: Dockerfile
    container_name: platform-core
    restart: always
    ports:
      - "8961:8960"
    environment:
      - DATABASE_URL=mysql+aiomysql://platform:password@mysql:3306/platform
      - REDIS_HOST=redis
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # CPL服务
  cpl:
    build:
      context: ./platform-cpl
      dockerfile: Dockerfile
    container_name: platform-cpl
    restart: always
    ports:
      - "8962:8960"
    environment:
      - DATABASE_URL=mysql+aiomysql://platform:password@mysql:3306/platform
      - REDIS_HOST=redis
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # 追踪服务
  tracking:
    build:
      context: ./platform-tracking
      dockerfile: Dockerfile
    container_name: platform-tracking
    restart: always
    ports:
      - "8963:8960"
    environment:
      - DATABASE_URL=mysql+aiomysql://platform:password@mysql:3306/platform
      - REDIS_HOST=redis
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # Postback服务
  postback:
    build:
      context: ./platform-postback
      dockerfile: Dockerfile
    container_name: platform-postback
    restart: always
    ports:
      - "8964:8960"
    environment:
      - DATABASE_URL=mysql+aiomysql://platform:password@mysql:3306/platform
      - REDIS_HOST=redis
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # 数据分析服务
  analytics:
    build:
      context: ./platform-analytics
      dockerfile: Dockerfile
    container_name: platform-analytics
    restart: always
    ports:
      - "8965:8960"
    environment:
      - DATABASE_URL=mysql+aiomysql://platform:password@mysql:3306/platform
      - REDIS_HOST=redis
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # 通知服务
  notification:
    build:
      context: ./platform-notification
      dockerfile: Dockerfile
    container_name: platform-notification
    restart: always
    ports:
      - "8966:8960"
    environment:
      - DATABASE_URL=mysql+aiomysql://platform:password@mysql:3306/platform
      - REDIS_HOST=redis
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
    depends_on:
      - mysql
      - redis
    networks:
      - platform-network

  # MySQL数据库
  mysql:
    image: mysql:8.0
    container_name: platform-mysql
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: platform
      MYSQL_USER: platform
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    networks:
      - platform-network

  # Redis缓存
  redis:
    image: redis:7-alpine
    container_name: platform-redis
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - platform-network

volumes:
  mysql_data:
  redis_data:

networks:
  platform-network:
    driver: bridge
```

### Worker数量智能分配

根据服务器硬件信息自动分配每个服务的Worker数量：

```python
# scripts/auto_allocate_workers.py
import psutil
import os

def get_system_info():
    """获取系统信息"""
    cpu_count = psutil.cpu_count()
    memory_gb = psutil.virtual_memory().total / (1024**3)
    return cpu_count, memory_gb

def allocate_workers(service_name, cpu_count, memory_gb):
    """
    根据服务类型和系统资源分配Worker数量
    
    Args:
        service_name: 服务名称
        cpu_count: CPU核心数
        memory_gb: 内存大小（GB）
        
    Returns:
        Worker数量
    """
    # 服务权重（根据服务重要性）
    service_weights = {
        'core': 1.0,           # 核心服务：高权重
        'cpl': 0.8,            # CPL服务：中高权重
        'tracking': 1.2,       # 追踪服务：最高权重（高并发）
        'postback': 1.0,       # Postback服务：高权重
        'analytics': 0.6,      # 分析服务：中权重
        'notification': 0.4    # 通知服务：低权重
    }
    
    # 基础Worker数量
    base_workers = max(2, (cpu_count * 2) + 1)
    
    # 根据内存调整
    if memory_gb < 4:
        memory_factor = 0.5
    elif memory_gb < 8:
        memory_factor = 0.8
    else:
        memory_factor = 1.0
    
    # 计算服务Worker数量
    weight = service_weights.get(service_name, 0.5)
    workers = int(base_workers * weight * memory_factor)
    
    # 确保至少1个Worker
    return max(1, workers)

def generate_gunicorn_config():
    """生成Gunicorn配置"""
    cpu_count, memory_gb = get_system_info()
    
    services = ['core', 'cpl', 'tracking', 'postback', 'analytics', 'notification']
    
    config = {}
    for service in services:
        workers = allocate_workers(service, cpu_count, memory_gb)
        config[service] = {
            'workers': workers,
            'worker_class': 'uvicorn.workers.UvicornWorker',
            'worker_connections': 1000,
            'max_requests': 1000,
            'timeout': 60,
            'keepalive': 10
        }
    
    return config

if __name__ == '__main__':
    config = generate_gunicorn_config()
    print("Worker配置：")
    for service, cfg in config.items():
        print(f"{service}: {cfg['workers']} workers")
```

### 微服务部署步骤

#### 1. Windows本地开发

```bash
# 1. 克隆项目
git clone <repository-url>
cd Platform

# 2. 创建共享模块
mkdir platform-shared
# 复制共享代码到platform-shared

# 3. 拆分服务
# 按照服务拆分方案，将代码拆分到对应目录

# 4. 生成Worker配置
python scripts/auto_allocate_workers.py

# 5. 启动开发环境
docker-compose -f docker-compose.dev.yml up -d
```

#### 2. Ubuntu生产环境

```bash
# 1. 克隆项目
cd /data
git clone <repository-url> Platform
cd Platform

# 2. 生成环境配置
sudo python3 scripts/自动生成配置/auto_generate_env_config.py --env production --no-interactive

# 3. 生成Worker配置
python3 scripts/auto_allocate_workers.py > docker-compose.workers.yml

# 4. 启动所有服务
docker-compose -f docker-compose.prod.yml up -d

# 5. 查看服务状态
docker-compose ps

# 6. 查看日志
docker-compose logs -f gateway
```

### 微服务优势

1. **独立部署**：每个服务可以独立部署和更新，互不影响
2. **横向扩展**：根据负载情况，独立扩展需要的服务
3. **技术栈灵活**：不同服务可以使用不同的技术栈
4. **故障隔离**：单个服务故障不会影响整个系统
5. **团队协作**：不同团队可以独立开发和维护不同的服务

### 微服务挑战

1. **复杂性增加**：服务间通信、数据一致性、分布式事务
2. **运维成本**：需要监控、日志聚合、链路追踪等基础设施
3. **网络延迟**：服务间调用增加网络开销
4. **数据管理**：需要处理分布式数据存储和同步

---

## 性能优化

### 数据库优化

#### 1. 索引优化

```sql
-- 分析慢查询
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';

-- 启用慢查询日志
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 2;

-- 查看慢查询
sudo tail -f /var/log/mysql/slow.log

-- 使用EXPLAIN分析查询
EXPLAIN SELECT * FROM postback_conversions 
WHERE offer_id = 1 AND conversion_time >= '2025-01-01';

-- 添加复合索引
CREATE INDEX idx_offer_conversion_time ON postback_conversions(offer_id, conversion_time);
CREATE INDEX idx_publisher_status ON postback_conversions(publisher_id, status);
```

#### 2. 查询优化

```python
# 使用批量查询代替循环查询
# 不推荐
for conversion_id in conversion_ids:
    conversion = await db.get_conversion(conversion_id)

# 推荐
conversions = await db.get_conversions(conversion_ids)

# 使用JOIN代替多次查询
# 不推荐
offer = await db.get_offer(offer_id)
publisher = await db.get_publisher(publisher_id)

# 推荐
result = await db.execute(
    select(Offer, Publisher)
    .join(Publisher, Offer.publisher_id == Publisher.id)
    .where(Offer.id == offer_id)
)
```

#### 3. 连接池优化

```python
# gunicorn.conf.py
import multiprocessing

cpu_count = multiprocessing.cpu_count()

# 根据CPU核心数调整连接池大小
DB_POOL_SIZE = min(20, cpu_count * 5)
DB_MAX_OVERFLOW = min(10, cpu_count * 2)
DB_POOL_RECYCLE = 3600  # 1小时回收连接
```

### 缓存优化

#### 1. Redis缓存策略

```python
# app/core/cache_manager.py
from functools import wraps
import json
import hashlib
from app.core.redis_client import get_redis_client

def cache_result(ttl=3600, key_prefix=None):
    """
    缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix or func.__name__}:{hashlib.md5(str(args + tuple(kwargs.items())).hexdigest()}"
            
            # 尝试从缓存获取
            redis = await get_redis_client()
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 缓存结果
            await redis.setex(cache_key, ttl, json.dumps(result))
            
            return result
        return wrapper
    return decorator

# 使用示例
@cache_result(ttl=1800, key_prefix="offers")
async def get_offers(db: AsyncSession, offer_id: int):
    """获取Offer（缓存30分钟）"""
    result = await db.execute(select(Offer).where(Offer.id == offer_id))
    return result.scalars().first()
```

#### 2. 缓存预热

```python
# app/scheduler_module/tasks/cache_warmup.py
async def warmup_cache():
    """缓存预热任务"""
    redis = await get_redis_client()
    
    # 预热热门Offer
    popular_offers = await get_popular_offers()
    for offer in popular_offers:
        cache_key = f"offer:{offer.id}"
        await redis.setex(cache_key, 3600, json.dumps(offer.dict()))
    
    # 预热活跃渠道
    active_publishers = await get_active_publishers()
    for publisher in active_publishers:
        cache_key = f"publisher:{publisher.id}"
        await redis.setex(cache_key, 3600, json.dumps(publisher.dict()))
```

### 应用层优化

#### 1. 异步处理

```python
# 使用异步IO提高并发性能
import asyncio
from aiohttp import ClientSession

async def fetch_multiple_urls(urls):
    """并发获取多个URL"""
    async with ClientSession() as session:
        tasks = [session.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return responses
```

#### 2. 批量操作

```python
# 批量插入
async def bulk_create_conversions(db: AsyncSession, conversions: list):
    """批量创建转化"""
    db.add_all(conversions)
    await db.commit()
    return len(conversions)

# 批量更新
async def bulk_update_caps(db: AsyncSession, updates: list):
    """批量更新Cap"""
    for cap_id, data in updates:
        await db.execute(
            update(OfferCap)
            .where(OfferCap.id == cap_id)
            .values(**data)
        )
    await db.commit()
```

#### 3. 分页优化

```python
# 使用游标分页代替偏移分页
async def get_conversions_cursor(
    db: AsyncSession,
    last_id: int = None,
    limit: int = 100
):
    """游标分页获取转化"""
    query = select(PostbackConversion).order_by(PostbackConversion.id)
    
    if last_id:
        query = query.where(PostbackConversion.id > last_id)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()
```

---

## 安全加固

### 应用安全

#### 1. 输入验证

```python
from pydantic import BaseModel, validator, Field
from typing import Optional

class ConversionCreate(BaseModel):
    """转化创建模式"""
    click_id: str = Field(..., min_length=1, max_length=100)
    payout: float = Field(..., gt=0, le=1000)
    offer_id: int = Field(..., gt=0)
    
    @validator('click_id')
    def validate_click_id(cls, v):
        """验证click_id格式"""
        if not v.isalnum():
            raise ValueError('click_id只能包含字母和数字')
        return v
```

#### 2. SQL注入防护

```python
# 使用参数化查询，避免SQL注入
# 不推荐
query = f"SELECT * FROM users WHERE username = '{username}'"

# 推荐
result = await db.execute(
    select(User).where(User.username == username)
)
```

#### 3. XSS防护

```python
from fastapi import Request
from fastapi.responses import JSONResponse
import html

async def sanitize_input(request: Request, call_next):
    """输入清理中间件"""
    # 清理请求体
    if request.method in ['POST', 'PUT', 'PATCH']:
        body = await request.body()
        # 清理HTML标签
        sanitized = html.escape(body.decode())
        request._body = sanitized.encode()
    
    response = await call_next(request)
    return response
```

### 网络安全

#### 1. HTTPS强制

```nginx
# nginx配置
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL证书
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # SSL安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

#### 2. 防火墙配置

```bash
# UFW防火墙配置
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 允许SSH
sudo ufw allow 22/tcp

# 允许HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 限制MySQL访问（仅本地）
sudo ufw allow from 127.0.0.1 to any port 3306

# 限制Redis访问（仅本地）
sudo ufw allow from 127.0.0.1 to any port 6379

# 启用防火墙
sudo ufw enable

# 查看状态
sudo ufw status
```

#### 3. 限流配置

```python
# app/core/middleware.py
from fastapi import Request, HTTPException
from app.core.redis_client import get_redis_client
import time

async def rate_limit_middleware(request: Request, call_next):
    """限流中间件"""
    client_ip = request.client.host
    redis = await get_redis_client()
    
    # 获取客户端请求计数
    key = f"rate_limit:{client_ip}"
    count = await redis.incr(key)
    
    # 首次请求，设置过期时间
    if count == 1:
        await redis.expire(key, 60)
    
    # 超过限制
    if count > 100:  # 每分钟100次
        raise HTTPException(status_code=429, detail="请求过于频繁")
    
    response = await call_next(request)
    return response
```

### 数据安全

#### 1. 密码加密

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)
```

#### 2. 敏感数据加密

```python
from cryptography.fernet import Fernet
import os

# 生成加密密钥
key = Fernet.generate_key()
cipher_suite = Fernet(key)

def encrypt_data(data: str) -> bytes:
    """加密数据"""
    return cipher_suite.encrypt(data.encode())

def decrypt_data(encrypted_data: bytes) -> str:
    """解密数据"""
    return cipher_suite.decrypt(encrypted_data).decode()
```

#### 3. 审计日志

```python
# app/core/audit_log.py
async def log_sensitive_action(
    db: AsyncSession,
    user_id: int,
    action: str,
    resource: str,
    details: dict
):
    """记录敏感操作"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        details=details,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )
    db.add(audit_log)
    await db.commit()
```

---

## 监控和故障排查

### 系统监控

#### 1. 应用监控

```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time

# 定义指标
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')
active_connections = Gauge('active_connections', 'Active database connections')

async def monitor_request(request: Request, call_next):
    """请求监控中间件"""
    start_time = time.time()
    
    # 记录请求
    response = await call_next(request)
    
    # 记录指标
    request_count.labels(
        method=request.method,
        endpoint=request.url.path
    ).inc()
    
    duration = time.time() - start_time
    request_duration.observe(duration)
    
    return response
```

#### 2. 数据库监控

```python
# app/core/database.py
from sqlalchemy import event
from sqlalchemy.engine import Engine
import logging

logger = logging.getLogger(__name__)

@event.listens_for(Engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """数据库连接监控"""
    logger.info(f"New database connection: {connection_record.connection}")

@event.listens_for(Engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """数据库连接池监控"""
    logger.info(f"Connection checked out: {connection_proxy.info}")

@event.listens_for(Engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """数据库连接归还监控"""
    logger.info(f"Connection checked in: {connection_record.connection}")
```

#### 3. Redis监控

```python
# app/core/redis_monitor.py
from app.core.redis_client import get_redis_client

async def check_redis_health():
    """检查Redis健康状态"""
    redis = await get_redis_client()
    
    try:
        # 测试连接
        await redis.ping()
        
        # 获取信息
        info = await redis.info()
        
        return {
            'status': 'healthy',
            'connected_clients': info.get('connected_clients'),
            'used_memory': info.get('used_memory_human'),
            'total_commands': info.get('total_commands_processed')
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }
```

### 日志管理

#### 1. 结构化日志

```python
# app/core/logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """JSON格式化器"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

# 配置日志
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

#### 2. 日志聚合

```bash
# 使用ELK Stack聚合日志
# docker-compose.yml
services:
  elasticsearch:
    image: elasticsearch:8.0.0
    environment:
      - discovery.type=single-node
    ports:
      - "9200:9200"
  
  logstash:
    image: logstash:8.0.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    depends_on:
      - elasticsearch
  
  kibana:
    image: kibana:8.0.0
    ports:
      - "5601:5601"
    depends_on:
      - elasticsearch
```

### 故障排查

#### 1. 常见问题诊断

```bash
# 检查服务状态
sudo systemctl status Platform-backend

# 检查端口占用
sudo netstat -tlnp | grep 8960

# 检查磁盘空间
df -h

# 检查内存使用
free -h

# 检查CPU使用
top -bn1 | head -20

# 检查进程
ps aux | grep gunicorn

# 检查网络连接
sudo netstat -an | grep ESTABLISHED | wc -l
```

#### 2. 日志分析

```bash
# 查看错误日志
grep ERROR /data/Platform/logs/app.log

# 统计错误类型
grep ERROR /data/Platform/logs/app.log | awk '{print $NF}' | sort | uniq -c | sort -rn

# 查看慢请求
grep "duration" /data/Platform/logs/app.log | awk -F'duration=' '{print $2}' | awk '{if($1>1) print}'

# 查看API调用统计
grep "POST\|GET\|PUT\|DELETE" /data/Platform/logs/app.log | awk '{print $4}' | sort | uniq -c | sort -rn
```

#### 3. 性能分析

```python
# app/core/profiler.py
import cProfile
import pstats
from io import StringIO

def profile_function(func):
    """性能分析装饰器"""
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        
        result = func(*args, **kwargs)
        
        pr.disable()
        
        # 输出分析结果
        s = StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats(10)
        
        print(s.getvalue())
        
        return result
    return wrapper
```

### 告警配置

```python
# app/core/alerts.py
import smtplib
from email.mime.text import MIMEText

async def send_alert(subject: str, message: str):
    """发送告警邮件"""
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = 'alerts@platform.com'
    msg['To'] = 'admin@platform.com'
    
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login('alerts@platform.com', 'password')
        server.send_message(msg)

async def check_system_health():
    """检查系统健康状态"""
    # 检查数据库
    db_health = await check_database_health()
    if db_health['status'] != 'healthy':
        await send_alert('数据库告警', f"数据库状态异常: {db_health}")
    
    # 检查Redis
    redis_health = await check_redis_health()
    if redis_health['status'] != 'healthy':
        await send_alert('Redis告警', f"Redis状态异常: {redis_health}")
    
    # 检查磁盘空间
    disk_usage = check_disk_usage()
    if disk_usage['percent'] > 90:
        await send_alert('磁盘空间告警', f"磁盘使用率: {disk_usage['percent']}%")
```

---

## 附录

### A. 快速命令参考

#### 后端命令
```bash
# 启动开发服务器
py -m uvicorn app.main:app --reload --port 8960

# 启动生产服务器
gunicorn --config gunicorn.conf.py app.main:app

# 查看日志
tail -f logs/app.log

# 运行测试
pytest tests/

# 代码格式化
black app/
isort app/

# 类型检查
mypy app/
```

#### 前端命令
```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview

# 代码检查
npm run lint

# 代码格式化
npm run format
```

#### 数据库命令
```bash
# 连接数据库
mysql -u platform -p platform

# 备份数据库
mysqldump -u platform -p platform > backup.sql

# 恢复数据库
mysql -u platform -p platform < backup.sql

# 查看表结构
DESCRIBE users;

# 查看索引
SHOW INDEX FROM users;
```

### B. 环境变量完整列表

```env
# 环境配置
PRODUCTION_ENV=production

# 安全配置
SECRET_KEY=your-secret-key
JWT_ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=240
RSA_PRIVATE_KEY_PATH=/data/Platform/keys/private_key.pem
RSA_PUBLIC_KEY_PATH=/data/Platform/keys/public_key.pem

# 数据库配置
DATABASE_URL=mysql+aiomysql://platform:password@127.0.0.1:3306/platform
DB_POOL_SIZE=15
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600

# Redis配置
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_MAX_CONNECTIONS=10

# CORS配置
BACKEND_CORS_ORIGINS=https://your-domain.com

# 管理员配置
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=your-secure-password

# API限流配置
API_RATE_LIMIT=100
LOGIN_RATE_LIMIT=10

# 文件上传配置
MAX_UPLOAD_SIZE=10485760

# CSRF配置
ENABLE_CSRF=true
CSRF_TOKEN_EXPIRE_SECONDS=3600

# 定时任务配置
MAX_CONCURRENT_SCHEDULED_TASKS=2

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# 审计日志配置
AUDIT_LOG_RETENTION_DAYS=30
AUDIT_LOG_ARCHIVE=true

# 时区配置
TIMEZONE=Asia/Shanghai

# Telegram配置
TELEGRAM_ENABLE=true
TELEGRAM_TOKEN=your-bot-token
TELEGRAM_ADMIN=your-chat-id

# Gunicorn配置
WORKERS=3
PRELOAD_APP=false
MEMORY_GB=4
```

### C. 有用的资源链接

- **FastAPI官方文档**：https://fastapi.tiangolo.com/
- **Vue 3官方文档**：https://vuejs.org/
- **Element Plus文档**：https://element-plus.org/
- **SQLAlchemy文档**：https://docs.sqlalchemy.org/
- **Pydantic文档**：https://docs.pydantic.dev/
- **MySQL文档**：https://dev.mysql.com/doc/
- **Redis文档**：https://redis.io/docs/
- **Nginx文档**：https://nginx.org/en/docs/

---

## 更新日志

### v1.0.0 (2025-01-27)
- 初始版本发布
- 完整的CPL系统功能
- 用户和权限管理
- Postback回调服务
- 短链接服务
- 定时任务调度
- 审计日志
- Telegram通知

---

**文档版本**：v1.0.0  
**最后更新**：2025-01-27  
**维护者**：Platform开发团队
