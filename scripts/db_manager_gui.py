#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表管理工具 - 带GUI界面
支持CPL表系列和其他表的分类管理
"""

import re
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
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
        self.cursor.execute(f"DESCRIBE `{table_name}`")
        columns = self.cursor.fetchall()
        
        self.cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
        create_table = self.cursor.fetchone()
        
        return {
            'columns': columns,
            'create_sql': create_table['Create Table'] if create_table else ''
        }
    
    def get_table_data(self, table_name: str, limit: int = 100, offset: int = 0) -> Tuple[List[Dict], int]:
        """获取表数据"""
        # 获取总数
        self.cursor.execute(f"SELECT COUNT(*) as total FROM `{table_name}`")
        total = self.cursor.fetchone()['total']
        
        # 获取数据
        self.cursor.execute(f"SELECT * FROM `{table_name}` LIMIT {limit} OFFSET {offset}")
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


class DatabaseManagerGUI:
    """数据库管理工具GUI"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("数据库表管理工具 - CPL系统")
        self.root.geometry("1200x800")
        
        self.sql_parser = None
        self.db_manager = DatabaseManager()
        self.current_table = None
        self.tables_data = {}
        
        self._create_widgets()
        self._load_sql_file()
        
    def _create_widgets(self):
        """创建GUI组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # 顶部工具栏
        toolbar = ttk.Frame(main_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(toolbar, text="加载SQL文件", command=self._load_sql_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="连接数据库", command=self._show_db_connection_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="刷新", command=self._refresh_tables).pack(side=tk.LEFT, padx=5)
        
        # 左侧：表列表
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        
        # 表分类标签
        ttk.Label(left_frame, text="表列表", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        # 创建Notebook用于分类显示
        self.table_notebook = ttk.Notebook(left_frame)
        self.table_notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # CPL表列表
        self.cpl_frame = ttk.Frame(self.table_notebook)
        self.table_notebook.add(self.cpl_frame, text="CPL表系列")
        
        self.cpl_tree = ttk.Treeview(self.cpl_frame, show="tree")
        self.cpl_tree.pack(fill=tk.BOTH, expand=True)
        self.cpl_tree.bind("<<TreeviewSelect>>", lambda e: self._on_table_select(e, is_cpl=True))
        
        # 其他表列表
        self.other_frame = ttk.Frame(self.table_notebook)
        self.table_notebook.add(self.other_frame, text="其他表")
        
        self.other_tree = ttk.Treeview(self.other_frame, show="tree")
        self.other_tree.pack(fill=tk.BOTH, expand=True)
        self.other_tree.bind("<<TreeviewSelect>>", lambda e: self._on_table_select(e, is_cpl=False))
        
        # 右侧：表详情
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        # 创建Notebook用于显示表详情
        self.detail_notebook = ttk.Notebook(right_frame)
        self.detail_notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 表结构标签页
        self.structure_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(self.structure_frame, text="表结构")
        
        self.structure_text = scrolledtext.ScrolledText(self.structure_frame, wrap=tk.WORD, height=20)
        self.structure_text.pack(fill=tk.BOTH, expand=True)
        
        # 表数据标签页
        self.data_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(self.data_frame, text="表数据")
        
        # 数据表格
        data_toolbar = ttk.Frame(self.data_frame)
        data_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(data_toolbar, text="刷新数据", command=self._refresh_data).pack(side=tk.LEFT, padx=5)
        ttk.Label(data_toolbar, text="每页:").pack(side=tk.LEFT, padx=5)
        self.page_size_var = tk.StringVar(value="100")
        ttk.Spinbox(data_toolbar, from_=10, to=1000, textvariable=self.page_size_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # 创建表格
        self.data_tree = ttk.Treeview(self.data_frame)
        self.data_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # 滚动条
        data_scrollbar = ttk.Scrollbar(self.data_frame, orient=tk.VERTICAL, command=self.data_tree.yview)
        data_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.data_tree.configure(yscrollcommand=data_scrollbar.set)
        
        # SQL查询标签页
        self.query_frame = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(self.query_frame, text="SQL查询")
        
        query_toolbar = ttk.Frame(self.query_frame)
        query_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(query_toolbar, text="执行查询", command=self._execute_query).pack(side=tk.LEFT, padx=5)
        ttk.Button(query_toolbar, text="清空", command=self._clear_query).pack(side=tk.LEFT, padx=5)
        
        self.query_text = scrolledtext.ScrolledText(self.query_frame, wrap=tk.WORD, height=10)
        self.query_text.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        
        self.query_result_text = scrolledtext.ScrolledText(self.query_frame, wrap=tk.WORD, height=10)
        self.query_result_text.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
    def _load_sql_file(self):
        """加载SQL文件"""
        import os
        
        # 首先尝试使用默认路径
        default_path = os.path.join(os.path.dirname(__file__), "data", "platform20251230.sql")
        file_path = None
        
        if os.path.exists(default_path):
            file_path = default_path
        else:
            # 如果默认路径不存在，弹出文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择SQL文件",
                filetypes=[("SQL files", "*.sql"), ("All files", "*.*")]
            )
        
        if not file_path:
            return
        
        try:
            self.sql_parser = SQLParser(file_path)
            self.tables_data = self.sql_parser.parse()
            self._populate_table_list()
            self.status_var.set(f"已加载 {len(self.tables_data)} 个表定义")
        except Exception as e:
            messagebox.showerror("错误", f"加载SQL文件失败: {str(e)}")
    
    def _populate_table_list(self):
        """填充表列表"""
        # 清空现有列表
        for item in self.cpl_tree.get_children():
            self.cpl_tree.delete(item)
        for item in self.other_tree.get_children():
            self.other_tree.delete(item)
        
        # 分类添加表
        for table_name, table_info in sorted(self.tables_data.items()):
            if table_info['is_cpl']:
                self.cpl_tree.insert("", tk.END, text=table_name, values=(table_info['comment'],))
            else:
                self.other_tree.insert("", tk.END, text=table_name, values=(table_info['comment'],))
    
    def _on_table_select(self, event, is_cpl: bool):
        """表选择事件"""
        tree = self.cpl_tree if is_cpl else self.other_tree
        selection = tree.selection()
        if not selection:
            return
        
        table_name = tree.item(selection[0])['text']
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
        structure += "\n" + "="*50 + "\n\n"
        
        structure += "字段列表:\n"
        structure += "-"*50 + "\n"
        for col in table_info['columns']:
            pk_mark = " [PK]" if col['primary_key'] else ""
            null_mark = " [NULL]" if col['nullable'] else " [NOT NULL]"
            default_mark = f" DEFAULT {col['default']}" if col.get('default') else ""
            structure += f"  {col['name']:25} {col['type']:25} {pk_mark}{null_mark}{default_mark}\n"
            if col['comment']:
                structure += f"    └─ {col['comment']}\n"
        
        if table_info['indexes']:
            structure += "\n索引列表:\n"
            structure += "-"*50 + "\n"
            for idx in table_info['indexes']:
                unique_mark = " [UNIQUE]" if idx['unique'] else ""
                structure += f"  {idx['name']}{unique_mark}: {', '.join(idx['fields'])}\n"
        
        if table_info['foreign_keys']:
            structure += "\n外键列表:\n"
            structure += "-"*50 + "\n"
            for fk in table_info['foreign_keys']:
                structure += f"  {fk['name']}: {fk['local_field']} -> {fk['ref_table']}.{fk['ref_field']}\n"
        
        self.structure_text.delete(1.0, tk.END)
        self.structure_text.insert(1.0, structure)
    
    def _show_table_data(self):
        """显示表数据"""
        if not self.current_table or not self.db_manager.connection:
            return
        
        try:
            # 清空现有数据
            for item in self.data_tree.get_children():
                self.data_tree.delete(item)
            
            # 获取数据
            limit = int(self.page_size_var.get())
            data, total = self.db_manager.get_table_data(self.current_table, limit=limit)
            
            if not data:
                self.status_var.set(f"表 {self.current_table} 无数据")
                return
            
            # 设置列
            columns = list(data[0].keys())
            self.data_tree['columns'] = columns
            self.data_tree['show'] = 'headings'
            
            # 配置列
            for col in columns:
                self.data_tree.heading(col, text=col)
                self.data_tree.column(col, width=100, anchor=tk.W)
            
            # 插入数据
            for row in data:
                values = [str(row.get(col, ''))[:50] for col in columns]  # 限制显示长度
                self.data_tree.insert("", tk.END, values=values)
            
            self.status_var.set(f"表 {self.current_table}: 显示 {len(data)}/{total} 条记录")
            
        except Exception as e:
            messagebox.showerror("错误", f"获取表数据失败: {str(e)}")
    
    def _refresh_data(self):
        """刷新数据"""
        self._show_table_data()
    
    def _refresh_tables(self):
        """刷新表列表"""
        if self.db_manager.connection:
            try:
                db_tables = self.db_manager.get_tables()
                # 可以在这里对比SQL定义和实际数据库
                self.status_var.set(f"数据库中有 {len(db_tables)} 个表")
            except Exception as e:
                messagebox.showerror("错误", f"刷新失败: {str(e)}")
    
    def _show_db_connection_dialog(self):
        """显示数据库连接对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("数据库连接")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 连接参数
        ttk.Label(dialog, text="主机:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        host_var = tk.StringVar(value="43.156.101.243")
        ttk.Entry(dialog, textvariable=host_var, width=30).grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Label(dialog, text="端口:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        port_var = tk.StringVar(value="3306")
        ttk.Entry(dialog, textvariable=port_var, width=30).grid(row=1, column=1, padx=10, pady=5)
        
        ttk.Label(dialog, text="用户名:").grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        user_var = tk.StringVar(value="remote")
        ttk.Entry(dialog, textvariable=user_var, width=30).grid(row=2, column=1, padx=10, pady=5)
        
        ttk.Label(dialog, text="密码:").grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)
        password_var = tk.StringVar(value='kb7$rL3d8!tQ')
        ttk.Entry(dialog, textvariable=password_var, width=30, show="*").grid(row=3, column=1, padx=10, pady=5)
        
        ttk.Label(dialog, text="数据库:").grid(row=4, column=0, padx=10, pady=5, sticky=tk.W)
        database_var = tk.StringVar(value="platform")
        ttk.Entry(dialog, textvariable=database_var, width=30).grid(row=4, column=1, padx=10, pady=5)
        
        def connect():
            try:
                port = int(port_var.get())
                self.db_manager.connect(
                    host_var.get(),
                    port,
                    user_var.get(),
                    password_var.get(),
                    database_var.get()
                )
                self.status_var.set("数据库连接成功")
                dialog.destroy()
                if self.current_table:
                    self._show_table_data()
            except Exception as e:
                messagebox.showerror("连接失败", str(e))
        
        ttk.Button(dialog, text="连接", command=connect).grid(row=5, column=0, columnspan=2, pady=20)
    
    def _execute_query(self):
        """执行SQL查询"""
        if not self.db_manager.connection:
            messagebox.showwarning("警告", "请先连接数据库")
            return
        
        query = self.query_text.get(1.0, tk.END).strip()
        if not query:
            messagebox.showwarning("警告", "请输入SQL查询")
            return
        
        try:
            results, message = self.db_manager.execute_query(query)
            
            self.query_result_text.delete(1.0, tk.END)
            
            if message:
                self.query_result_text.insert(1.0, message)
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
                    self.query_result_text.insert(1.0, output)
                else:
                    self.query_result_text.insert(1.0, "查询成功，无结果")
            else:
                self.query_result_text.insert(1.0, "执行成功")
                
        except Exception as e:
            self.query_result_text.delete(1.0, tk.END)
            self.query_result_text.insert(1.0, f"执行失败: {str(e)}")
    
    def _clear_query(self):
        """清空查询"""
        self.query_text.delete(1.0, tk.END)
        self.query_result_text.delete(1.0, tk.END)
    
    def __del__(self):
        """析构函数，关闭数据库连接"""
        if hasattr(self, 'db_manager'):
            self.db_manager.disconnect()


def main():
    """主函数"""
    root = tk.Tk()
    app = DatabaseManagerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

