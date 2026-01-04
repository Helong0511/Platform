#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表管理工具 - PyQt5版本
支持CPL表系列和其他表的分类管理
"""

import re
import os
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QTextEdit, QTabWidget, QPushButton, QLabel, QDialog, QDialogButtonBox,
    QLineEdit, QSpinBox, QMessageBox, QFileDialog, QStatusBar, QToolBar,
    QGroupBox, QFormLayout, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
import mysql.connector
from mysql.connector import Error
from typing import Dict, List, Tuple, Optional


class SQLParser:
    """SQL文件解析器"""
    
    # CPL系统相关表（根据业务逻辑定义）
    CPL_TABLES = {
        'clicks', 'offers', 'advertisers', 'publishers', 
        'offer_caps', 'offer_discounts', 'offer_publisher_assignments',
        'advertiser_tests', 'affiliate_tests', 'postback_conversions',
        'postback_forward_logs', 'postback_notifications', 'postback_forward_queue'
    }
    
    def __init__(self, sql_file: str):
        self.sql_file = sql_file
        self.tables: Dict[str, Dict] = {}
        
    def parse(self) -> Dict[str, Dict]:
        """解析SQL文件，提取表结构"""
        try:
            with open(self.sql_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用正则表达式提取表定义
            table_pattern = r'CREATE TABLE `(\w+)`\s*\((.*?)\)\s*ENGINE'
            
            for match in re.finditer(table_pattern, content, re.DOTALL | re.IGNORECASE):
                table_name = match.group(1)
                table_body = match.group(2)
                
                # 提取字段信息
                columns = self._parse_columns(table_body)
                
                # 提取索引信息
                indexes = self._parse_indexes(table_body)
                
                # 提取外键信息
                foreign_keys = self._parse_foreign_keys(table_body)
                
                # 判断是否为CPL表
                is_cpl = table_name.lower() in self.CPL_TABLES
                
                self.tables[table_name] = {
                    'name': table_name,
                    'columns': columns,
                    'indexes': indexes,
                    'foreign_keys': foreign_keys,
                    'is_cpl': is_cpl,
                    'comment': self._extract_comment(content, table_name)
                }
            
            return self.tables
            
        except Exception as e:
            raise Exception(f"解析SQL文件失败: {str(e)}")
    
    def _parse_columns(self, table_body: str) -> List[Dict]:
        """解析字段定义"""
        columns = []
        lines = table_body.split('\n')
        
        for line in lines:
            line = line.strip()
            # 跳过非字段定义行
            if not line or line.startswith('PRIMARY') or line.startswith('UNIQUE') or \
               line.startswith('INDEX') or line.startswith('CONSTRAINT') or \
               line.startswith('KEY') or line.startswith('FOREIGN'):
                continue
            
            # 提取字段名（必须以反引号开始）
            field_match = re.match(r'`(\w+)`', line)
            if not field_match:
                continue
            
            field_name = field_match.group(1)
            
            # 提取类型（字段名后的第一个词，可能包含括号）
            type_match = re.search(r'`\w+`\s+(\w+(?:\([^)]+\))?)', line)
            field_type = type_match.group(1) if type_match else 'unknown'
            
            # 提取注释
            comment_match = re.search(r"COMMENT\s+['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
            comment = comment_match.group(1) if comment_match else ''
            
            # 判断是否可空（默认可空，除非明确NOT NULL）
            nullable = 'NOT NULL' not in line.upper() or ('NULL' in line.upper() and 'NOT NULL' not in line.upper())
            
            # 判断是否主键
            is_primary = 'PRIMARY KEY' in line.upper() or 'AUTO_INCREMENT' in line.upper()
            
            # 提取默认值
            default_match = re.search(r"DEFAULT\s+([^,\s]+)", line, re.IGNORECASE)
            default_value = default_match.group(1) if default_match else None
            
            columns.append({
                'name': field_name,
                'type': field_type,
                'nullable': nullable,
                'primary_key': is_primary,
                'comment': comment,
                'default': default_value,
                'raw': line
            })
        
        return columns
    
    def _parse_indexes(self, table_body: str) -> List[Dict]:
        """解析索引定义"""
        indexes = []
        # 匹配索引定义
        index_pattern = r'(?:UNIQUE\s+)?INDEX\s+`?(\w+)`?\s*\(([^)]+)\)'
        
        for match in re.finditer(index_pattern, table_body, re.IGNORECASE):
            index_name = match.group(1)
            index_fields = match.group(2)
            is_unique = 'UNIQUE' in match.group(0).upper()
            
            indexes.append({
                'name': index_name,
                'fields': [f.strip().strip('`') for f in index_fields.split(',')],
                'unique': is_unique
            })
        
        return indexes
    
    def _parse_foreign_keys(self, table_body: str) -> List[Dict]:
        """解析外键定义"""
        foreign_keys = []
        # 匹配外键定义
        fk_pattern = r"CONSTRAINT\s+`?(\w+)`?\s+FOREIGN\s+KEY\s+\(`?(\w+)`?\)\s+REFERENCES\s+`(\w+)`\s+\(`(\w+)`\)"
        
        for match in re.finditer(fk_pattern, table_body, re.IGNORECASE):
            fk_name = match.group(1)
            local_field = match.group(2)
            ref_table = match.group(3)
            ref_field = match.group(4)
            
            foreign_keys.append({
                'name': fk_name,
                'local_field': local_field,
                'ref_table': ref_table,
                'ref_field': ref_field
            })
        
        return foreign_keys
    
    def _extract_comment(self, content: str, table_name: str) -> str:
        """提取表注释"""
        # 查找表注释
        comment_pattern = rf"COMMENT\s*=\s*['\"]([^'\"]+)['\"]"
        table_section = content[content.find(f"CREATE TABLE `{table_name}`"):]
        match = re.search(comment_pattern, table_section, re.IGNORECASE)
        return match.group(1) if match else ''


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.connection = None
        self.cursor = None
    
    @staticmethod
    def _validate_table_name(table_name: str) -> bool:
        """
        验证表名是否安全
        只允许字母、数字、下划线和反引号
        """
        if not table_name:
            return False
        # 移除反引号后检查
        clean_name = table_name.strip('`')
        # 只允许字母、数字、下划线
        import re
        return bool(re.match(r'^[a-zA-Z0-9_]+$', clean_name))
    
    def connect(self, host: str, port: int, user: str, password: str, database: str) -> bool:
        """连接数据库"""
        try:
            self.connection = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset='utf8mb4',
                autocommit=False
            )
            self.cursor = self.connection.cursor(dictionary=True)
            return True
        except Error as e:
            raise Exception(f"数据库连接失败: {str(e)}")
    
    def disconnect(self):
        """断开数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
    
    def get_tables(self) -> List[str]:
        """获取所有表名"""
        self.cursor.execute("SHOW TABLES")
        return [list(row.values())[0] for row in self.cursor.fetchall()]
    
    def get_table_structure(self, table_name: str) -> Dict:
        """获取表结构"""
        # 验证表名安全性
        if not self._validate_table_name(table_name):
            raise ValueError(f"无效的表名: {table_name}")
        
        # 使用参数化查询（MySQL不支持表名参数化，但我们已经验证了表名）
        # 清理表名，移除可能的反引号并重新添加
        clean_table_name = table_name.strip('`')
        safe_table_name = f"`{clean_table_name}`"
        
        self.cursor.execute(f"DESCRIBE {safe_table_name}")
        columns = self.cursor.fetchall()
        
        self.cursor.execute(f"SHOW CREATE TABLE {safe_table_name}")
        create_table = self.cursor.fetchone()
        
        return {
            'columns': columns,
            'create_sql': create_table['Create Table'] if create_table else ''
        }
    
    def get_table_data(self, table_name: str, limit: int = 100, offset: int = 0) -> Tuple[List[Dict], int]:
        """获取表数据"""
        # 验证表名安全性
        if not self._validate_table_name(table_name):
            raise ValueError(f"无效的表名: {table_name}")
        
        # 验证limit和offset参数
        if not isinstance(limit, int) or limit < 0 or limit > 10000:
            raise ValueError(f"无效的limit参数: {limit}")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError(f"无效的offset参数: {offset}")
        
        # 清理表名，移除可能的反引号并重新添加
        clean_table_name = table_name.strip('`')
        safe_table_name = f"`{clean_table_name}`"
        
        # 获取总数（使用参数化查询）
        self.cursor.execute(f"SELECT COUNT(*) as total FROM {safe_table_name}")
        total = self.cursor.fetchone()['total']
        
        # 获取数据（使用参数化查询，limit和offset是整数，安全）
        self.cursor.execute(f"SELECT * FROM {safe_table_name} LIMIT %s OFFSET %s", (limit, offset))
        data = self.cursor.fetchall()
        
        return data, total
    
    def execute_query(self, query: str) -> Tuple[List[Dict], Optional[str]]:
        """执行查询"""
        try:
            self.cursor.execute(query)
            if query.strip().upper().startswith('SELECT'):
                return self.cursor.fetchall(), None
            else:
                self.connection.commit()
                return [], f"执行成功，影响行数: {self.cursor.rowcount}"
        except Error as e:
            return [], f"执行失败: {str(e)}"


class DatabaseConnectionDialog(QDialog):
    """数据库连接对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据库连接")
        self.setModal(True)
        self.resize(400, 250)
        
        layout = QFormLayout()
        
        self.host_edit = QLineEdit("43.156.101.243")
        self.port_edit = QLineEdit("3306")
        self.user_edit = QLineEdit("remote")
        self.password_edit = QLineEdit("kb7$rL3d8!tQ")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.database_edit = QLineEdit("platform")
        
        layout.addRow("主机:", self.host_edit)
        layout.addRow("端口:", self.port_edit)
        layout.addRow("用户名:", self.user_edit)
        layout.addRow("密码:", self.password_edit)
        layout.addRow("数据库:", self.database_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addRow(buttons)
        self.setLayout(layout)
    
    def get_connection_info(self):
        """获取连接信息"""
        return {
            'host': self.host_edit.text(),
            'port': int(self.port_edit.text()),
            'user': self.user_edit.text(),
            'password': self.password_edit.text(),
            'database': self.database_edit.text()
        }


class DatabaseManagerGUI(QMainWindow):
    """数据库管理工具GUI - PyQt5版本"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数据库表管理工具 - CPL系统")
        self.setGeometry(100, 100, 1400, 900)
        
        self.sql_parser = None
        self.db_manager = DatabaseManager()
        self.current_table = None
        self.tables_data = {}
        
        self._create_widgets()
        self._load_sql_file()
        
    def _create_widgets(self):
        """创建GUI组件"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧：表列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # 表列表标题
        title_label = QLabel("表列表")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        left_layout.addWidget(title_label)
        
        # 创建标签页用于分类显示
        self.table_tabs = QTabWidget()
        left_layout.addWidget(self.table_tabs)
        
        # CPL表列表
        self.cpl_tree = QTreeWidget()
        self.cpl_tree.setHeaderLabel("CPL表系列")
        self.cpl_tree.itemSelectionChanged.connect(lambda: self._on_table_select(self.cpl_tree, is_cpl=True))
        self.table_tabs.addTab(self.cpl_tree, "CPL表系列")
        
        # 其他表列表
        self.other_tree = QTreeWidget()
        self.other_tree.setHeaderLabel("其他表")
        self.other_tree.itemSelectionChanged.connect(lambda: self._on_table_select(self.other_tree, is_cpl=False))
        self.table_tabs.addTab(self.other_tree, "其他表")
        
        splitter.addWidget(left_widget)
        
        # 右侧：表详情
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建详情标签页
        self.detail_tabs = QTabWidget()
        right_layout.addWidget(self.detail_tabs)
        
        # 表结构标签页
        self.structure_text = QTextEdit()
        self.structure_text.setReadOnly(True)
        self.structure_text.setFont(QFont("Consolas", 10))
        self.detail_tabs.addTab(self.structure_text, "表结构")
        
        # 表数据标签页
        data_widget = QWidget()
        data_layout = QVBoxLayout(data_widget)
        data_layout.setContentsMargins(5, 5, 5, 5)
        
        # 数据工具栏
        data_toolbar = QHBoxLayout()
        refresh_btn = QPushButton("刷新数据")
        refresh_btn.clicked.connect(self._refresh_data)
        data_toolbar.addWidget(refresh_btn)
        
        data_toolbar.addWidget(QLabel("每页:"))
        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(10, 1000)
        self.page_size_spin.setValue(100)
        data_toolbar.addWidget(self.page_size_spin)
        data_toolbar.addStretch()
        
        data_layout.addLayout(data_toolbar)
        
        # 数据表格
        self.data_table = QTableWidget()
        self.data_table.setAlternatingRowColors(True)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        data_layout.addWidget(self.data_table)
        
        self.detail_tabs.addTab(data_widget, "表数据")
        
        # SQL查询标签页
        query_widget = QWidget()
        query_layout = QVBoxLayout(query_widget)
        query_layout.setContentsMargins(5, 5, 5, 5)
        
        # 查询工具栏
        query_toolbar = QHBoxLayout()
        execute_btn = QPushButton("执行查询")
        execute_btn.clicked.connect(self._execute_query)
        query_toolbar.addWidget(execute_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_query)
        query_toolbar.addWidget(clear_btn)
        query_toolbar.addStretch()
        
        query_layout.addLayout(query_toolbar)
        
        # SQL输入框
        self.query_text = QTextEdit()
        self.query_text.setFont(QFont("Consolas", 10))
        self.query_text.setPlaceholderText("输入SQL查询语句...")
        query_layout.addWidget(self.query_text)
        
        # 查询结果
        result_label = QLabel("查询结果:")
        query_layout.addWidget(result_label)
        
        self.query_result_text = QTextEdit()
        self.query_result_text.setReadOnly(True)
        self.query_result_text.setFont(QFont("Consolas", 10))
        query_layout.addWidget(self.query_result_text)
        
        self.detail_tabs.addTab(query_widget, "SQL查询")
        
        splitter.addWidget(right_widget)
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        # 创建工具栏
        toolbar = self.addToolBar("主工具栏")
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        load_sql_action = toolbar.addAction("加载SQL文件")
        load_sql_action.triggered.connect(self._load_sql_file)
        
        connect_db_action = toolbar.addAction("连接数据库")
        connect_db_action.triggered.connect(self._show_db_connection_dialog)
        
        refresh_action = toolbar.addAction("刷新")
        refresh_action.triggered.connect(self._refresh_tables)
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")
        
    def _load_sql_file(self):
        """加载SQL文件"""
        # 首先尝试使用默认路径
        default_path = os.path.join(os.path.dirname(__file__), "data", "platform20251230.sql")
        file_path = None
        
        if os.path.exists(default_path):
            file_path = default_path
        else:
            # 如果默认路径不存在，弹出文件选择对话框
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择SQL文件",
                "",
                "SQL files (*.sql);;All files (*.*)"
            )
        
        if not file_path:
            return
        
        try:
            self.sql_parser = SQLParser(file_path)
            self.tables_data = self.sql_parser.parse()
            self._populate_table_list()
            self.statusBar.showMessage(f"已加载 {len(self.tables_data)} 个表定义", 5000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载SQL文件失败:\n{str(e)}")
    
    def _populate_table_list(self):
        """填充表列表"""
        # 清空现有列表
        self.cpl_tree.clear()
        self.other_tree.clear()
        
        # 分类添加表
        for table_name, table_info in sorted(self.tables_data.items()):
            item = QTreeWidgetItem([table_name])
            if table_info['comment']:
                item.setToolTip(0, table_info['comment'])
            
            if table_info['is_cpl']:
                self.cpl_tree.addTopLevelItem(item)
            else:
                self.other_tree.addTopLevelItem(item)
    
    def _on_table_select(self, tree: QTreeWidget, is_cpl: bool):
        """表选择事件"""
        selected_items = tree.selectedItems()
        if not selected_items:
            return
        
        table_name = selected_items[0].text(0)
        self.current_table = table_name
        self._show_table_structure()
        self._show_table_data()
    
    def _show_table_structure(self):
        """显示表结构"""
        if not self.current_table or self.current_table not in self.tables_data:
            return
        
        table_info = self.tables_data[self.current_table]
        
        # 构建结构信息
        structure = f"表名: {table_info['name']}\n"
        structure += f"类型: {'CPL表' if table_info['is_cpl'] else '其他表'}\n"
        structure += f"注释: {table_info['comment']}\n"
        structure += "\n" + "="*60 + "\n\n"
        
        structure += "字段列表:\n"
        structure += "-"*60 + "\n"
        for col in table_info['columns']:
            pk_mark = " [PK]" if col['primary_key'] else ""
            null_mark = " [NULL]" if col['nullable'] else " [NOT NULL]"
            default_mark = f" DEFAULT {col['default']}" if col.get('default') else ""
            structure += f"  {col['name']:25} {col['type']:25} {pk_mark}{null_mark}{default_mark}\n"
            if col['comment']:
                structure += f"    └─ {col['comment']}\n"
        
        if table_info['indexes']:
            structure += "\n索引列表:\n"
            structure += "-"*60 + "\n"
            for idx in table_info['indexes']:
                unique_mark = " [UNIQUE]" if idx['unique'] else ""
                structure += f"  {idx['name']}{unique_mark}: {', '.join(idx['fields'])}\n"
        
        if table_info['foreign_keys']:
            structure += "\n外键列表:\n"
            structure += "-"*60 + "\n"
            for fk in table_info['foreign_keys']:
                structure += f"  {fk['name']}: {fk['local_field']} -> {fk['ref_table']}.{fk['ref_field']}\n"
        
        self.structure_text.setPlainText(structure)
    
    def _show_table_data(self):
        """显示表数据"""
        if not self.current_table or not self.db_manager.connection:
            return
        
        try:
            # 获取数据
            limit = self.page_size_spin.value()
            data, total = self.db_manager.get_table_data(self.current_table, limit=limit)
            
            if not data:
                self.statusBar.showMessage(f"表 {self.current_table} 无数据", 3000)
                self.data_table.setRowCount(0)
                self.data_table.setColumnCount(0)
                return
            
            # 设置表格
            columns = list(data[0].keys())
            self.data_table.setColumnCount(len(columns))
            self.data_table.setRowCount(len(data))
            self.data_table.setHorizontalHeaderLabels(columns)
            
            # 填充数据
            for row_idx, row_data in enumerate(data):
                for col_idx, col_name in enumerate(columns):
                    value = str(row_data.get(col_name, ''))
                    # 限制显示长度
                    if len(value) > 100:
                        value = value[:100] + "..."
                    item = QTableWidgetItem(value)
                    self.data_table.setItem(row_idx, col_idx, item)
            
            # 调整列宽
            self.data_table.resizeColumnsToContents()
            
            self.statusBar.showMessage(f"表 {self.current_table}: 显示 {len(data)}/{total} 条记录", 5000)
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"获取表数据失败:\n{str(e)}")
    
    def _refresh_data(self):
        """刷新数据"""
        self._show_table_data()
    
    def _refresh_tables(self):
        """刷新表列表"""
        if self.db_manager.connection:
            try:
                db_tables = self.db_manager.get_tables()
                self.statusBar.showMessage(f"数据库中有 {len(db_tables)} 个表", 3000)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"刷新失败:\n{str(e)}")
    
    def _show_db_connection_dialog(self):
        """显示数据库连接对话框"""
        dialog = DatabaseConnectionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                conn_info = dialog.get_connection_info()
                self.db_manager.connect(**conn_info)
                self.statusBar.showMessage("数据库连接成功", 3000)
                if self.current_table:
                    self._show_table_data()
            except Exception as e:
                QMessageBox.critical(self, "连接失败", str(e))
    
    def _execute_query(self):
        """执行SQL查询"""
        if not self.db_manager.connection:
            QMessageBox.warning(self, "警告", "请先连接数据库")
            return
        
        query = self.query_text.toPlainText().strip()
        if not query:
            QMessageBox.warning(self, "警告", "请输入SQL查询")
            return
        
        try:
            results, message = self.db_manager.execute_query(query)
            
            self.query_result_text.clear()
            
            if message:
                self.query_result_text.setPlainText(message)
            elif results:
                # 显示结果
                if results:
                    columns = list(results[0].keys())
                    output = "\t".join(columns) + "\n"
                    output += "-" * 80 + "\n"
                    for row in results[:100]:  # 限制显示100行
                        values = [str(row.get(col, '')) for col in columns]
                        output += "\t".join(values) + "\n"
                    if len(results) > 100:
                        output += f"\n... 共 {len(results)} 行，仅显示前100行"
                    self.query_result_text.setPlainText(output)
                else:
                    self.query_result_text.setPlainText("查询成功，无结果")
            else:
                self.query_result_text.setPlainText("执行成功")
                
        except Exception as e:
            self.query_result_text.clear()
            self.query_result_text.setPlainText(f"执行失败: {str(e)}")
    
    def _clear_query(self):
        """清空查询"""
        self.query_text.clear()
        self.query_result_text.clear()
    
    def closeEvent(self, event):
        """关闭事件"""
        if hasattr(self, 'db_manager'):
            self.db_manager.disconnect()
        event.accept()


def main():
    """主函数"""
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    window = DatabaseManagerGUI()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

