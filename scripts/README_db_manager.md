# 数据库表管理工具使用说明

## 功能特点

1. **SQL文件解析**：自动解析SQL文件，提取表结构信息
2. **CPL表分类**：自动区分CPL系统表和其他表
3. **表结构查看**：查看表的字段、索引、外键等详细信息
4. **数据浏览**：连接数据库后可以查看表数据
5. **SQL查询**：支持执行自定义SQL查询

## CPL表系列

工具会自动识别以下CPL系统相关表：

- `clicks` - 点击记录表
- `offers` - Offer表（单子表）
- `advertisers` - 广告主表（上游）
- `publishers` - 渠道表（下游）
- `offer_caps` - Cap配置表
- `offer_discounts` - 扣量配置表
- `offer_publisher_assignments` - Offer-渠道分配表
- `advertiser_tests` - 上游测试记录表
- `affiliate_tests` - 下游测试记录表
- `postback_conversions` - Postback转化事件表
- `postback_forward_logs` - Postback转发日志
- `postback_notifications` - Postback通知记录
- `postback_forward_queue` - Postback转发队列

## 安装依赖

```bash
pip install mysql-connector-python
```

或者使用requirements文件：

```bash
pip install -r requirements_db_manager.txt
```

## 使用方法

### 1. 直接运行

```bash
python scripts/db_manager_gui.py
```

### 2. 使用步骤

1. **加载SQL文件**
   - 点击"加载SQL文件"按钮
   - 选择 `scripts/data/platform20251230.sql` 文件
   - 工具会自动解析并显示所有表

2. **连接数据库**（可选）
   - 点击"连接数据库"按钮
   - 输入数据库连接信息：
     - 主机：数据库服务器地址
     - 端口：默认3306
     - 用户名：数据库用户名
     - 密码：数据库密码
     - 数据库：数据库名称（如platform）

3. **查看表结构**
   - 在左侧表列表中选择表（CPL表系列或其他表）
   - 在"表结构"标签页查看详细信息：
     - 字段列表（字段名、类型、是否可空、是否主键、注释）
     - 索引列表
     - 外键列表

4. **查看表数据**（需要连接数据库）
   - 选择表后，切换到"表数据"标签页
   - 可以设置每页显示数量
   - 点击"刷新数据"更新数据

5. **执行SQL查询**（需要连接数据库）
   - 切换到"SQL查询"标签页
   - 输入SQL语句
   - 点击"执行查询"查看结果

## 界面说明

### 左侧面板
- **CPL表系列**：显示所有CPL系统相关表
- **其他表**：显示其他业务表

### 右侧面板
- **表结构**：显示选中表的详细结构信息
- **表数据**：显示表中的数据（需要连接数据库）
- **SQL查询**：执行自定义SQL查询

## 注意事项

1. 首次使用需要加载SQL文件来解析表结构
2. 查看数据和执行查询需要先连接数据库
3. SQL查询功能支持SELECT、INSERT、UPDATE、DELETE等操作
4. 执行非SELECT语句时会自动提交事务

## 故障排除

### 连接数据库失败
- 检查数据库服务是否运行
- 检查连接参数是否正确
- 检查防火墙设置
- 检查用户权限

### SQL文件解析失败
- 确保SQL文件格式正确
- 检查文件编码是否为UTF-8
- 确保SQL文件包含CREATE TABLE语句

