# 数据库表管理工具 - PyQt5版本

## 📋 版本说明

这是使用PyQt5重新开发的数据库表管理工具，相比Tkinter版本具有以下优势：

- ✨ **更现代的界面**：使用Fusion样式，界面更美观
- 🎨 **更好的用户体验**：响应更快，交互更流畅
- 📊 **更强大的表格**：QTableWidget支持更好的数据展示
- 🔧 **更丰富的功能**：支持更多UI组件和自定义样式

## 🚀 快速开始

### 安装依赖

```bash
pip install PyQt5 mysql-connector-python
```

或使用requirements文件：

```bash
pip install -r requirements_db_manager.txt
```

### 运行工具

**Windows:**
```bash
cd scripts
python db_manager_gui_pyqt5.py
```

或双击运行：
```
scripts\run_db_manager_pyqt5.bat
```

**Linux/Mac:**
```bash
cd scripts
python3 db_manager_gui_pyqt5.py
```

或使用shell脚本：
```bash
bash scripts/run_db_manager_pyqt5.sh
```

## 🎨 界面特点

### 主窗口布局

- **左侧面板**：表列表（CPL表系列 / 其他表）
  - 使用QTreeWidget显示表列表
  - 支持工具提示显示表注释
  - 点击表名即可查看详情

- **右侧面板**：表详情（三个标签页）
  - **表结构**：使用QTextEdit显示，等宽字体便于阅读
  - **表数据**：使用QTableWidget显示，支持列宽自动调整
  - **SQL查询**：支持输入和执行SQL语句

### 工具栏

- **加载SQL文件**：加载和解析SQL文件
- **连接数据库**：连接MySQL数据库
- **刷新**：刷新表列表和数据

### 状态栏

显示当前操作状态和提示信息

## 🔧 功能对比

| 功能 | Tkinter版本 | PyQt5版本 |
|------|------------|-----------|
| 界面美观度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 响应速度 | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 表格功能 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 代码可维护性 | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 跨平台支持 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

## 📝 使用说明

### 1. 加载SQL文件

工具启动时会自动尝试加载 `scripts/data/platform20251230.sql` 文件。

如果文件不存在，可以：
- 点击工具栏的"加载SQL文件"按钮
- 选择SQL文件进行加载

### 2. 查看表结构

1. 在左侧表列表中选择表（CPL表系列或其他表）
2. 右侧自动显示表结构信息：
   - 表基本信息
   - 字段列表（名称、类型、约束、注释）
   - 索引列表
   - 外键列表

### 3. 连接数据库

1. 点击工具栏的"连接数据库"按钮
2. 填写连接信息（已预填默认值）：
   - 主机：43.156.101.243
   - 端口：3306
   - 用户名：remote
   - 密码：kb7$rL3d8!tQ
   - 数据库：platform
3. 点击"确定"连接

### 4. 查看表数据

1. 确保已连接数据库
2. 选择要查看的表
3. 切换到"表数据"标签页
4. 可以：
   - 设置每页显示数量（10-1000条）
   - 点击"刷新数据"更新显示
   - 查看表格中的所有数据

### 5. 执行SQL查询

1. 确保已连接数据库
2. 切换到"SQL查询"标签页
3. 在SQL输入框中输入SQL语句
4. 点击"执行查询"按钮
5. 查看执行结果或错误信息

## ⚙️ 技术细节

### 主要组件

- **QMainWindow**：主窗口框架
- **QSplitter**：可调整大小的分割器
- **QTabWidget**：标签页组件
- **QTreeWidget**：树形列表（表列表）
- **QTableWidget**：表格组件（数据展示）
- **QTextEdit**：文本编辑器（SQL输入和结果显示）

### 样式设置

- 使用Fusion样式（`app.setStyle('Fusion')`）
- 表格使用交替行颜色（`setAlternatingRowColors(True)`）
- 等宽字体用于代码显示（Consolas字体）

## 🔍 常见问题

### Q1: 如何安装PyQt5？

```bash
# Windows
pip install PyQt5

# Linux (Ubuntu/Debian)
sudo apt-get install python3-pyqt5

# Mac
brew install pyqt5
```

### Q2: 运行时报错 "No module named 'PyQt5'"

确保已安装PyQt5：
```bash
pip install PyQt5
```

### Q3: 界面显示不正常

- 检查PyQt5版本是否 >= 5.15.0
- 尝试更新PyQt5：`pip install --upgrade PyQt5`

### Q4: 数据库连接失败

- 检查数据库服务是否运行
- 验证连接参数是否正确
- 检查防火墙和网络设置

## 📦 文件说明

- `db_manager_gui_pyqt5.py` - PyQt5版本主程序
- `run_db_manager_pyqt5.bat` - Windows启动脚本
- `run_db_manager_pyqt5.sh` - Linux/Mac启动脚本
- `requirements_db_manager.txt` - 依赖文件（已包含PyQt5）

## 🎯 下一步

- 添加数据编辑功能
- 支持导出数据为CSV/Excel
- 添加表关系图可视化
- 支持多数据库连接

---

**版本**：1.0.0 (PyQt5)  
**更新日期**：2025-01-01

