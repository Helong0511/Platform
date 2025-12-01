import wx
import wx.grid
import pymysql
import threading
import time
import json
from collections import OrderedDict

# ==========================================
# 0. 用户自定义默认配置 (请在此处修改)
# ==========================================
SOURCE_DEFAULTS = {
    'host': '43.156.101.243',
    'port': '3306',
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',  # 数据库连接密码
    'db': 'platform'  # 默认数据库名
}

TARGET_DEFAULTS = {
    'host': '159.138.133.34',
    'port': '3306',  # 建议使用不同端口以区分实例
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',  # 数据库连接密码
    'db': 'platform'  # 默认数据库名
}


# ==========================================
# 1. 核心逻辑层 (DBSyncCore)
# ==========================================
class DBSyncCore:
    def __init__(self):
        self.sqls = []
        self.data_sqls = []  # 数据同步SQL
        self.data_diff_report = []  # 数据差异报告

    def _get_conn(self, conf):
        """根据配置字典创建并返回 pymysql 数据库连接"""
        conf_copy = conf.copy()
        conf_copy['port'] = int(conf_copy['port'])
        return pymysql.connect(**conf_copy, cursorclass=pymysql.cursors.DictCursor)

    def get_all_row_counts(self, conn, db_name):
        """获取目标数据库中所有表的精确行数"""
        counts = {}
        with conn.cursor() as cursor:
            cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s", (db_name,))
            tables = [row['TABLE_NAME'] for row in cursor.fetchall()]

            for t in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) as c FROM `{t}`")
                    counts[t] = cursor.fetchone()['c']
                except Exception:
                    counts[t] = -1
        return counts

    def get_meta(self, conn, db_name):
        """获取全库的结构元数据（表、字段、注释、索引）"""
        tables = {}
        with conn.cursor() as cursor:
            cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s", (db_name,))
            for row in cursor.fetchall():
                tables[row['TABLE_NAME']] = {'columns': {}, 'indexes': {}}

            cursor.execute("""
                           SELECT TABLE_NAME,
                                  COLUMN_NAME,
                                  COLUMN_TYPE,
                                  IS_NULLABLE,
                                  COLUMN_DEFAULT,
                                  EXTRA,
                                  COLUMN_COMMENT
                           FROM information_schema.COLUMNS
                           WHERE TABLE_SCHEMA = %s
                           ORDER BY ORDINAL_POSITION
                           """, (db_name,))
            for row in cursor.fetchall():
                t = row['TABLE_NAME']
                if t in tables: tables[t]['columns'][row['COLUMN_NAME']] = row

            cursor.execute("""
                           SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME, SEQ_IN_INDEX
                           FROM information_schema.STATISTICS
                           WHERE TABLE_SCHEMA = %s
                           ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
                           """, (db_name,))
            for row in cursor.fetchall():
                t = row['TABLE_NAME']
                idx = row['INDEX_NAME']
                if t in tables:
                    if idx not in tables[t]['indexes']:
                        tables[t]['indexes'][idx] = {'unique': row['NON_UNIQUE'] == 0, 'columns': []}
                    tables[t]['indexes'][idx]['columns'].append(row['COLUMN_NAME'])
        return tables

    def get_primary_key(self, conn, db_name, table_name):
        """获取表的主键列名列表，如果没有主键则尝试获取唯一索引"""
        with conn.cursor() as cursor:
            # 先尝试获取主键
            cursor.execute("""
                SELECT COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME = %s
                  AND CONSTRAINT_NAME = 'PRIMARY'
                ORDER BY ORDINAL_POSITION
            """, (db_name, table_name))
            result = cursor.fetchall()
            pk_columns = [row['COLUMN_NAME'] for row in result]
            
            # 如果有主键，直接返回
            if pk_columns:
                return pk_columns
            
            # 如果没有主键，尝试获取第一个唯一索引
            cursor.execute("""
                SELECT DISTINCT INDEX_NAME
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_NAME = %s
                  AND NON_UNIQUE = 0
                  AND INDEX_NAME != 'PRIMARY'
                ORDER BY INDEX_NAME
                LIMIT 1
            """, (db_name, table_name))
            unique_idx = cursor.fetchone()
            if unique_idx:
                idx_name = unique_idx['INDEX_NAME']
                cursor.execute("""
                    SELECT COLUMN_NAME
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = %s
                      AND TABLE_NAME = %s
                      AND INDEX_NAME = %s
                    ORDER BY SEQ_IN_INDEX
                """, (db_name, table_name, idx_name))
                result = cursor.fetchall()
                return [row['COLUMN_NAME'] for row in result]
            
            # 如果都没有，返回空列表，后续会使用所有列
            return []

    def _escape_sql_value(self, value):
        """转义SQL值"""
        if value is None:
            return 'NULL'
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, bool):
            return '1' if value else '0'
        # 字符串需要转义
        value_str = str(value)
        value_str = value_str.replace('\\', '\\\\')
        value_str = value_str.replace("'", "''")
        return f"'{value_str}'"

    def _get_row_key(self, row, key_columns):
        """根据主键列生成行的唯一标识"""
        return tuple(row.get(col) for col in key_columns)

    def _generate_where_clause(self, row, key_columns):
        """根据主键生成WHERE子句"""
        conditions = []
        for col in key_columns:
            val = row.get(col)
            if val is None:
                conditions.append(f"`{col}` IS NULL")
            else:
                conditions.append(f"`{col}` = {self._escape_sql_value(val)}")
        return " AND ".join(conditions)

    def _generate_insert_sql(self, table_name, row, columns):
        """生成INSERT SQL"""
        cols = ", ".join([f"`{c}`" for c in columns])
        vals = ", ".join([self._escape_sql_value(row.get(c)) for c in columns])
        return f"INSERT INTO `{table_name}` ({cols}) VALUES ({vals});"

    def _generate_update_sql(self, table_name, row, key_columns, all_columns):
        """生成UPDATE SQL"""
        set_clauses = []
        for col in all_columns:
            if col not in key_columns:
                set_clauses.append(f"`{col}` = {self._escape_sql_value(row.get(col))}")
        if not set_clauses:
            return None
        where_clause = self._generate_where_clause(row, key_columns)
        return f"UPDATE `{table_name}` SET {', '.join(set_clauses)} WHERE {where_clause};"

    def _generate_delete_sql(self, table_name, row, key_columns):
        """生成DELETE SQL"""
        where_clause = self._generate_where_clause(row, key_columns)
        return f"DELETE FROM `{table_name}` WHERE {where_clause};"

    def compare_table_data(self, source_conf, target_conf, table_name, log_callback=None):
        """对比单个表的数据，返回差异统计和SQL"""
        conn_src = self._get_conn(source_conf)
        conn_tgt = self._get_conn(target_conf)
        
        try:
            # 获取主键或唯一索引
            pk_columns = self.get_primary_key(conn_src, source_conf['db'], table_name)
            if not pk_columns:
                # 如果没有主键和唯一索引，使用所有列作为标识（不推荐，但可以工作）
                with conn_src.cursor() as cursor:
                    cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 0")
                    pk_columns = [desc[0] for desc in cursor.description]
                if log_callback:
                    log_callback(f"警告: 表 {table_name} 无主键和唯一索引，使用所有列作为标识（可能影响性能）")
            
            # 获取所有列名
            with conn_src.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 0")
                all_columns = [desc[0] for desc in cursor.description]
            
            # 读取源库数据
            if log_callback:
                log_callback(f"读取源库表 {table_name} 数据...")
            with conn_src.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{table_name}`")
                src_rows = cursor.fetchall()
            
            # 读取目标库数据
            if log_callback:
                log_callback(f"读取目标库表 {table_name} 数据...")
            with conn_tgt.cursor() as cursor:
                cursor.execute(f"SELECT * FROM `{table_name}`")
                tgt_rows = cursor.fetchall()
            
            # 构建索引字典
            src_dict = {}
            for row in src_rows:
                key = self._get_row_key(row, pk_columns)
                src_dict[key] = row
            
            tgt_dict = {}
            for row in tgt_rows:
                key = self._get_row_key(row, pk_columns)
                tgt_dict[key] = row
            
            # 对比差异
            insert_count = 0
            update_count = 0
            delete_count = 0
            sqls = []
            diff_details = []
            
            # 找出需要插入的记录（源有目标无）
            for key, row in src_dict.items():
                if key not in tgt_dict:
                    insert_count += 1
                    sqls.append(self._generate_insert_sql(table_name, row, all_columns))
                    # 记录差异详情（只记录前几个字段，避免太长）
                    key_str = ", ".join([f"{pk_columns[i]}={row.get(pk_columns[i])}" for i in range(min(3, len(pk_columns)))])
                    diff_details.append(f"需插入: {key_str}")
            
            # 找出需要删除的记录（目标有源无）
            for key, row in tgt_dict.items():
                if key not in src_dict:
                    delete_count += 1
                    sqls.append(self._generate_delete_sql(table_name, row, pk_columns))
                    key_str = ", ".join([f"{pk_columns[i]}={row.get(pk_columns[i])}" for i in range(min(3, len(pk_columns)))])
                    diff_details.append(f"需删除: {key_str}")
            
            # 找出需要更新的记录（两边都有但内容不同）
            for key, src_row in src_dict.items():
                if key in tgt_dict:
                    tgt_row = tgt_dict[key]
                    # 对比所有非主键列
                    has_diff = False
                    diff_fields = []
                    for col in all_columns:
                        if col not in pk_columns:
                            src_val = src_row.get(col)
                            tgt_val = tgt_row.get(col)
                            # 处理None值
                            if src_val != tgt_val and not (src_val is None and tgt_val is None):
                                has_diff = True
                                diff_fields.append(col)
                    
                    if has_diff:
                        update_count += 1
                        update_sql = self._generate_update_sql(table_name, src_row, pk_columns, all_columns)
                        if update_sql:
                            sqls.append(update_sql)
                        key_str = ", ".join([f"{pk_columns[i]}={src_row.get(pk_columns[i])}" for i in range(min(3, len(pk_columns)))])
                        diff_details.append(f"需更新: {key_str} (字段: {', '.join(diff_fields[:5])})")
            
            return {
                'table': table_name,
                'insert_count': insert_count,
                'update_count': update_count,
                'delete_count': delete_count,
                'sqls': sqls,
                'details': diff_details[:20]  # 只保留前20条详情
            }
            
        finally:
            conn_src.close()
            conn_tgt.close()

    def compare_all_data(self, source_conf, target_conf, table_names, log_callback=None):
        """对比所有表的数据"""
        self.data_sqls = []
        self.data_diff_report = []
        
        total_tables = len(table_names)
        for idx, table_name in enumerate(table_names, 1):
            if log_callback:
                log_callback(f"对比数据 [{idx}/{total_tables}]: {table_name}")
            try:
                result = self.compare_table_data(source_conf, target_conf, table_name, log_callback)
                if result['insert_count'] > 0 or result['update_count'] > 0 or result['delete_count'] > 0:
                    self.data_diff_report.append(result)
                    self.data_sqls.extend(result['sqls'])
            except Exception as e:
                if log_callback:
                    log_callback(f"表 {table_name} 数据对比失败: {e}")
                self.data_diff_report.append({
                    'table': table_name,
                    'insert_count': 0,
                    'update_count': 0,
                    'delete_count': 0,
                    'sqls': [],
                    'details': [f"对比失败: {e}"]
                })
        
        return self.data_diff_report, self.data_sqls

    def get_create_table_sql(self, source_conf, table_name):
        """获取创建表的完整 DDL 语句"""
        conn = self._get_conn(source_conf)
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
                return cursor.fetchone()['Create Table']
        finally:
            conn.close()

    def _col_def(self, col):
        """根据字段元数据生成完整的字段定义 SQL 片段"""
        definition = f"{col['COLUMN_TYPE']}"

        definition += " NOT NULL" if col['IS_NULLABLE'] == 'NO' else " NULL"

        if col['COLUMN_DEFAULT'] is not None:
            default_val = col['COLUMN_DEFAULT']
            if 'CURRENT_TIMESTAMP' in str(default_val):
                definition += f" DEFAULT {default_val}"
            else:
                definition += f" DEFAULT '{default_val}'"

        if col['EXTRA']: definition += f" {col['EXTRA']}"

        if col.get('COLUMN_COMMENT'):
            comment = col['COLUMN_COMMENT']
            safe_comment = comment.replace("'", "''")
            definition += f" COMMENT '{safe_comment}'"

        return definition

    def analyze(self, source_conf, target_conf, compare_data=False, log_callback=None):
        """核心对比逻辑：包含明确的异常源标记"""
        self.sqls = []
        self.data_sqls = []
        self.data_diff_report = []
        report = []

        if log_callback: log_callback("正在连接并分析结构 (1/2)...")

        # 1. 连接源数据库并获取结构
        try:
            conn_src = self._get_conn(source_conf)
            src_struct = self.get_meta(conn_src, source_conf['db'])
        except Exception as e:
            # 【关键修改】明确指出源数据库操作失败
            raise Exception(f"【源数据库】连接或获取结构失败: {e}") from e

        # 2. 连接目标数据库并获取结构
        try:
            conn_tgt = self._get_conn(target_conf)
            tgt_struct = self.get_meta(conn_tgt, target_conf['db'])
        except Exception as e:
            # 【关键修改】明确指出目标数据库操作失败
            raise Exception(f"【目标数据库】连接或获取结构失败: {e}") from e

        if log_callback: log_callback("正在统计精确行数 (2/2)...")

        # 3. 统计源库行数
        try:
            src_rows = self.get_all_row_counts(conn_src, source_conf['db'])
        except Exception as e:
            raise Exception(f"【源数据库】行数统计失败: {e}") from e

        # 4. 统计目标库行数
        try:
            tgt_rows = self.get_all_row_counts(conn_tgt, target_conf['db'])
        except Exception as e:
            raise Exception(f"【目标数据库】行数统计失败: {e}") from e

        conn_src.close()
        conn_tgt.close()

        all_tables = sorted(set(src_struct.keys()) | set(tgt_struct.keys()))
        if log_callback: log_callback("正在生成对比报告...")

        # ... (省略结构差异对比及 SQL 生成逻辑) ...
        for t in all_tables:
            s_rows = src_rows.get(t, '-')
            t_rows = tgt_rows.get(t, '-')
            is_in_src = t in src_struct
            is_in_tgt = t in tgt_struct

            if is_in_src and not is_in_tgt:
                report.append(('NEW', t, s_rows, '-', '源库特有 -> 需创建'))
                create_sql = self.get_create_table_sql(source_conf, t)
                self.sqls.append(f"{create_sql};")
                continue

            if not is_in_src and is_in_tgt:
                report.append(('DEL', t, '-', t_rows, '目标库特有 -> 建议删除'))
                self.sqls.append(f"-- DROP TABLE `{t}`; -- [警告] 目标库多余表")
                continue

            cols_src = src_struct[t]['columns']
            cols_tgt = tgt_struct[t]['columns']
            diffs = []

            for c in set(cols_src) - set(cols_tgt):
                diffs.append(f"+列:{c}")
                self.sqls.append(f"ALTER TABLE `{t}` ADD COLUMN `{c}` {self._col_def(cols_src[c])};")
            for c in set(cols_tgt) - set(cols_src):
                diffs.append(f"-列:{c}")
                self.sqls.append(f"ALTER TABLE `{t}` DROP COLUMN `{c}`;")

            for c in set(cols_src).intersection(cols_tgt):
                s, tgt_c = cols_src[c], cols_tgt[c]

                if (s['COLUMN_TYPE'] != tgt_c['COLUMN_TYPE'] or
                        s['IS_NULLABLE'] != tgt_c['IS_NULLABLE'] or
                        str(s['COLUMN_DEFAULT']) != str(tgt_c['COLUMN_DEFAULT']) or
                        s['EXTRA'] != tgt_c['EXTRA'] or
                        s['COLUMN_COMMENT'] != tgt_c['COLUMN_COMMENT']):

                    diffs.append(f"*列:{c}")

                    if (s['COLUMN_TYPE'] == tgt_c['COLUMN_TYPE'] and s['IS_NULLABLE'] == tgt_c['IS_NULLABLE'] and
                            str(s['COLUMN_DEFAULT']) == str(tgt_c['COLUMN_DEFAULT']) and s['EXTRA'] == tgt_c[
                                'EXTRA'] and
                            s['COLUMN_COMMENT'] != tgt_c['COLUMN_COMMENT']):
                        diffs[-1] += " (仅注释变更)"

                    self.sqls.append(f"ALTER TABLE `{t}` MODIFY COLUMN `{c}` {self._col_def(s)};")

            idxs_src = src_struct[t]['indexes']
            idxs_tgt = tgt_struct[t]['indexes']
            for i in set(idxs_src) - set(idxs_tgt):
                diffs.append(f"+索引:{i}")
                cols = ",".join([f"`{c}`" for c in idxs_src[i]['columns']])
                if i == 'PRIMARY':
                    self.sqls.append(f"ALTER TABLE `{t}` ADD PRIMARY KEY ({cols});")
                else:
                    self.sqls.append(
                        f"ALTER TABLE `{t}` ADD {'UNIQUE ' if idxs_src[i]['unique'] else ''}INDEX `{i}` ({cols});")
            for i in set(idxs_tgt) - set(idxs_src):
                diffs.append(f"-索引:{i}")
                if i == 'PRIMARY':
                    self.sqls.append(f"ALTER TABLE `{t}` DROP PRIMARY KEY;")
                else:
                    self.sqls.append(f"ALTER TABLE `{t}` DROP INDEX `{i}`;")
            for i in set(idxs_src).intersection(idxs_tgt):
                s, tgt_i = idxs_src[i], idxs_tgt[i]
                if s['unique'] != tgt_i['unique'] or s['columns'] != tgt_i['columns']:
                    diffs.append(f"*索引:{i}")
                    if i == 'PRIMARY':
                        self.sqls.append(f"ALTER TABLE `{t}` DROP PRIMARY KEY;")
                        self.sqls.append(
                            f"ALTER TABLE `{t}` ADD PRIMARY KEY ({','.join(['`' + c + '`' for c in s['columns']])});")
                    else:
                        self.sqls.append(f"ALTER TABLE `{t}` DROP INDEX `{i}`;")
                        self.sqls.append(
                            f"ALTER TABLE `{t}` ADD {'UNIQUE ' if s['unique'] else ''}INDEX `{i}` ({','.join(['`' + c + '`' for c in s['columns']])});")

            if diffs:
                report.append(('STR', t, s_rows, t_rows, ", ".join(diffs)))
            else:
                if s_rows != t_rows:
                    report.append(('DAT', t, s_rows, t_rows, '结构一致，但行数不同'))
                else:
                    report.append(('OK', t, s_rows, t_rows, '一致'))

        # 如果启用数据对比，进行逐条数据对比
        if compare_data:
            if log_callback:
                log_callback("开始逐条数据对比...")
            # 只对比结构一致且都存在的表
            tables_to_compare = [t for t in all_tables 
                                if t in src_struct and t in tgt_struct 
                                and src_struct[t]['columns'].keys() == tgt_struct[t]['columns'].keys()]
            if tables_to_compare:
                self.compare_all_data(source_conf, target_conf, tables_to_compare, log_callback)
                if log_callback:
                    log_callback(f"数据对比完成，发现 {len(self.data_diff_report)} 个表有数据差异")

        return report, self.sqls

    def execute_sql(self, target_conf, sql_list, log_callback):
        """连接目标库并执行同步 SQL 列表"""
        conn = self._get_conn(target_conf)
        try:
            # ... (省略 SQL 执行逻辑) ...
            with conn.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                for sql in sql_list:
                    if sql.strip().startswith("--"): continue
                    log_callback(f"执行: {sql[:60]}...")
                    cursor.execute(sql)
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()
            return True, "执行成功！"
        except Exception as e:
            conn.rollback()
            # 【关键修改】在执行 SQL 失败时也明确指出是对目标库的操作
            return False, f"目标数据库执行 SQL 失败: {e}"
        finally:
            conn.close()


# ... (UI 组件 MainFrame 保持不变) ...

class DBConfigPanel(wx.Panel):
    # ... (保持不变) ...
    def __init__(self, parent, title, defaults):
        super().__init__(parent)

        box = wx.StaticBox(self, label=title)
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        grid = wx.FlexGridSizer(rows=5, cols=2, vgap=5, hgap=10)
        self.inputs = {}

        fields = [('IP/Host:', 'host'), ('Port:', 'port'),
                  ('User:', 'user'), ('Password:', 'password'), ('Database:', 'db')]

        for label, key in fields:
            initial_value = defaults[key]

            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            style = wx.TE_PASSWORD if key == 'password' else 0
            ctrl = wx.TextCtrl(self, value=initial_value, style=style, size=(150, -1))
            self.inputs[key] = ctrl
            grid.Add(ctrl, 1, wx.EXPAND)

        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(sizer)

    def get_config(self):
        return {k: v.GetValue() for k, v in self.inputs.items()}


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Python 终极数据库对比工具 (结构/注释/行数/数据)", size=(1200, 750))
        self.core = DBSyncCore()
        self.current_sqls = []
        self.current_data_sqls = []

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        config_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.src_panel = DBConfigPanel(panel, "源数据库 (标准)", defaults=SOURCE_DEFAULTS)
        self.tgt_panel = DBConfigPanel(panel, "目标数据库 (待同步)", defaults=TARGET_DEFAULTS)

        config_sizer.Add(self.src_panel, 1, wx.EXPAND | wx.ALL, 5)
        config_sizer.Add(self.tgt_panel, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(config_sizer, 0, wx.EXPAND)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_compare_data = wx.CheckBox(panel, label="同时进行数据逐条对比 (较慢，需主键)")
        self.chk_compare_data.SetValue(False)
        btn_sizer.Add(self.chk_compare_data, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        btn_sizer.AddStretchSpacer(1)
        self.btn_compare = wx.Button(panel, label="开始全面分析", size=(200, 40))
        self.btn_compare.Bind(wx.EVT_BUTTON, self.on_compare)
        btn_sizer.Add(self.btn_compare, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        btn_sizer.AddStretchSpacer(1)
        main_sizer.Add(btn_sizer, 0, wx.EXPAND)

        self.notebook = wx.Notebook(panel)
        self.list_ctrl = wx.ListCtrl(self.notebook, style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES)

        self.list_ctrl.InsertColumn(0, "状态", width=60)
        self.list_ctrl.InsertColumn(1, "表名", width=200)
        self.list_ctrl.InsertColumn(2, "源行数", width=80, format=wx.LIST_FORMAT_RIGHT)
        self.list_ctrl.InsertColumn(3, "目标行数", width=80, format=wx.LIST_FORMAT_RIGHT)
        self.list_ctrl.InsertColumn(4, "详情/结构差异", width=500)

        self.list_ctrl.Bind(wx.EVT_SIZE, self.on_list_resize)
        self.notebook.AddPage(self.list_ctrl, "详细对比清单")

        self.txt_sql = wx.TextCtrl(self.notebook, style=wx.TE_MULTILINE | wx.HSCROLL)
        self.txt_sql.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.notebook.AddPage(self.txt_sql, "结构同步 SQL")

        # 数据差异详情列表
        self.list_data_diff = wx.ListCtrl(self.notebook, style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES)
        self.list_data_diff.InsertColumn(0, "表名", width=200)
        self.list_data_diff.InsertColumn(1, "需插入", width=80, format=wx.LIST_FORMAT_RIGHT)
        self.list_data_diff.InsertColumn(2, "需更新", width=80, format=wx.LIST_FORMAT_RIGHT)
        self.list_data_diff.InsertColumn(3, "需删除", width=80, format=wx.LIST_FORMAT_RIGHT)
        self.list_data_diff.InsertColumn(4, "差异详情", width=500)
        self.notebook.AddPage(self.list_data_diff, "数据差异详情")

        # 数据同步SQL
        self.txt_data_sql = wx.TextCtrl(self.notebook, style=wx.TE_MULTILINE | wx.HSCROLL)
        self.txt_data_sql.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.notebook.AddPage(self.txt_data_sql, "数据同步 SQL")

        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        self.txt_log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
        main_sizer.Add(self.txt_log, 0, wx.EXPAND | wx.ALL, 5)

        exec_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_exec = wx.Button(panel, label="执行结构同步 SQL", size=(150, 40))
        self.btn_exec.Disable()
        self.btn_exec.Bind(wx.EVT_BUTTON, self.on_execute)
        self.btn_exec.SetForegroundColour(wx.RED)
        
        self.btn_exec_data = wx.Button(panel, label="执行数据同步 SQL", size=(150, 40))
        self.btn_exec_data.Disable()
        self.btn_exec_data.Bind(wx.EVT_BUTTON, self.on_execute_data)
        self.btn_exec_data.SetForegroundColour(wx.Colour(200, 0, 0))
        
        exec_sizer.AddStretchSpacer(1)
        exec_sizer.Add(self.btn_exec, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        exec_sizer.Add(self.btn_exec_data, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        exec_sizer.AddStretchSpacer(1)
        main_sizer.Add(exec_sizer, 0, wx.EXPAND)

        panel.SetSizer(main_sizer)
        self.Centre()
        self.log("程序已启动。")

    def on_list_resize(self, event):
        w = self.list_ctrl.GetClientSize().width
        col0_w, col2_w, col3_w = 60, 80, 80
        self.list_ctrl.SetColumnWidth(0, col0_w)
        self.list_ctrl.SetColumnWidth(2, col2_w)
        self.list_ctrl.SetColumnWidth(3, col3_w)

        remain = w - col0_w - col2_w - col3_w
        if remain > 0:
            self.list_ctrl.SetColumnWidth(1, int(remain * 0.3))
            self.list_ctrl.SetColumnWidth(4, int(remain * 0.7))
        event.Skip()

    def log(self, msg):
        wx.CallAfter(self.txt_log.AppendText, f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def on_compare(self, event):
        src = self.src_panel.get_config()
        tgt = self.tgt_panel.get_config()
        if not src['db'] or not tgt['db']:
            wx.MessageBox("请输入数据库名！", "错误", wx.OK | wx.ICON_ERROR)
            return
        self.list_ctrl.DeleteAllItems()
        self.list_data_diff.DeleteAllItems()
        self.txt_sql.Clear()
        self.txt_data_sql.Clear()
        self.btn_compare.Disable()
        self.btn_exec.Disable()
        self.btn_exec_data.Disable()
        compare_data = self.chk_compare_data.GetValue()
        threading.Thread(target=self._run_compare, args=(src, tgt, compare_data), daemon=True).start()

    def _run_compare(self, src, tgt, compare_data):
        try:
            self.log("任务开始...")
            if compare_data:
                self.log("已启用数据逐条对比，这将需要较长时间...")
            report, sqls = self.core.analyze(src, tgt, compare_data=compare_data, log_callback=self.log)
            self.current_sqls = sqls
            self.current_data_sqls = self.core.data_sqls
            wx.CallAfter(self._update_ui_results, report, sqls, compare_data)
        except Exception as e:
            # 此处捕获到了 DBSyncCore.analyze 中抛出的带有【源数据库】或【目标数据库】的明确错误信息
            wx.CallAfter(wx.MessageBox, f"出错: {e}", "错误", wx.OK | wx.ICON_ERROR)
            self.log(f"异常: {e}")
        finally:
            wx.CallAfter(self.btn_compare.Enable)

    def _update_ui_results(self, report, sqls, compare_data=False):
        for status, table, s_rows, t_rows, detail in report:
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), status)
            self.list_ctrl.SetItem(idx, 1, table)
            self.list_ctrl.SetItem(idx, 2, str(s_rows))
            self.list_ctrl.SetItem(idx, 3, str(t_rows))
            self.list_ctrl.SetItem(idx, 4, detail)

            if status == 'NEW':
                self.list_ctrl.SetItemTextColour(idx, wx.Colour(0, 150, 0))
            elif status == 'DEL':
                self.list_ctrl.SetItemTextColour(idx, wx.Colour(255, 0, 0))
            elif status == 'STR':
                self.list_ctrl.SetItemTextColour(idx, wx.Colour(255, 140, 0))
            elif status == 'DAT':
                self.list_ctrl.SetItemTextColour(idx, wx.Colour(204, 204, 0))
            else:
                self.list_ctrl.SetItemTextColour(idx, wx.Colour(120, 120, 120))

        # 显示数据差异
        if compare_data and self.core.data_diff_report:
            for diff_info in self.core.data_diff_report:
                idx = self.list_data_diff.InsertItem(self.list_data_diff.GetItemCount(), diff_info['table'])
                self.list_data_diff.SetItem(idx, 1, str(diff_info['insert_count']))
                self.list_data_diff.SetItem(idx, 2, str(diff_info['update_count']))
                self.list_data_diff.SetItem(idx, 3, str(diff_info['delete_count']))
                details_text = "; ".join(diff_info['details'][:3])  # 只显示前3条详情
                if len(diff_info['details']) > 3:
                    details_text += f" ... (共{len(diff_info['details'])}条)"
                self.list_data_diff.SetItem(idx, 4, details_text)
                
                # 根据差异类型设置颜色
                total_diff = diff_info['insert_count'] + diff_info['update_count'] + diff_info['delete_count']
                if total_diff > 0:
                    self.list_data_diff.SetItemTextColour(idx, wx.Colour(255, 100, 0))
            
            if self.current_data_sqls:
                self.txt_data_sql.SetValue("\n".join(self.current_data_sqls))
                self.btn_exec_data.Enable()
                self.log(f"数据对比完成。发现 {len(self.core.data_diff_report)} 个表有数据差异，共 {len(self.current_data_sqls)} 条SQL。")

        if sqls:
            self.txt_sql.SetValue("\n".join(sqls))
            self.btn_exec.Enable()
            self.log(f"对比完成。结构差异语句: {len(sqls)} 条。")
            msg = f"发现差异！结构差异语句: {len(sqls)} 条。"
            if compare_data and self.core.data_diff_report:
                msg += f"\n数据差异: {len(self.core.data_diff_report)} 个表，{len(self.current_data_sqls)} 条SQL。"
            wx.MessageBox(msg, "完成", wx.OK | wx.ICON_WARNING)
        else:
            has_data_diff = any(r[0] == 'DAT' for r in report)
            if has_data_diff:
                self.txt_sql.SetValue("-- 结构一致，但数据行数不同 (见列表 DAT 项)")
                self.log("对比完成。结构一致，数据有差异。")
                msg = "结构一致，但发现数据量差异 (DAT)！"
                if compare_data and self.core.data_diff_report:
                    msg += f"\n数据逐条对比: {len(self.core.data_diff_report)} 个表有差异。"
                wx.MessageBox(msg, "提醒", wx.OK | wx.ICON_INFORMATION)
            else:
                self.txt_sql.SetValue("-- 完美一致 (结构 & 行数)")
                msg = "完美！结构与行数均一致。"
                if compare_data:
                    if self.core.data_diff_report:
                        msg += f"\n但数据逐条对比发现 {len(self.core.data_diff_report)} 个表有差异。"
                    else:
                        msg += "\n数据逐条对比也完全一致！"
                self.log("对比完成。完全一致。")
                wx.MessageBox(msg, "完成", wx.OK | wx.ICON_INFORMATION)

    def on_execute(self, event):
        if not self.current_sqls: return
        dlg = wx.MessageDialog(self, "⚠️ 确定执行结构同步？\n此操作只会修复表结构、索引和注释，不涉及数据！", "确认",
                               wx.YES_NO | wx.ICON_WARNING)
        if dlg.ShowModal() == wx.ID_YES:
            self.btn_exec.Disable()
            tgt = self.tgt_panel.get_config()
            threading.Thread(target=self._run_execute, args=(tgt,), daemon=True).start()
        dlg.Destroy()

    def _run_execute(self, tgt):
        self.log("开始执行结构同步...")
        # 核心 SQL 执行方法现在会返回带有 "目标数据库" 前缀的错误信息
        success, msg = self.core.execute_sql(tgt, self.current_sqls, self.log)
        if success:
            wx.CallAfter(wx.MessageBox, "结构同步成功！", "成功", wx.OK | wx.ICON_INFORMATION)
            self.log("执行结束: 成功")
        else:
            wx.CallAfter(wx.MessageBox, f"执行失败: {msg}", "失败", wx.OK | wx.ICON_ERROR)
            self.log(f"执行结束: 失败 - {msg}")
        wx.CallAfter(self.btn_exec.Enable)

    def on_execute_data(self, event):
        if not self.current_data_sqls:
            wx.MessageBox("没有数据同步SQL可执行！", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        dlg = wx.MessageDialog(self, 
                              f"⚠️ 确定执行数据同步？\n此操作将执行 {len(self.current_data_sqls)} 条SQL语句！\n"
                              "包括 INSERT、UPDATE、DELETE 操作，将修改目标数据库的数据！\n\n"
                              "强烈建议先备份目标数据库！", 
                              "确认", wx.YES_NO | wx.ICON_WARNING)
        if dlg.ShowModal() == wx.ID_YES:
            self.btn_exec_data.Disable()
            tgt = self.tgt_panel.get_config()
            threading.Thread(target=self._run_execute_data, args=(tgt,), daemon=True).start()
        dlg.Destroy()

    def _run_execute_data(self, tgt):
        self.log("开始执行数据同步...")
        success, msg = self.core.execute_sql(tgt, self.current_data_sqls, self.log)
        if success:
            wx.CallAfter(wx.MessageBox, f"数据同步成功！共执行 {len(self.current_data_sqls)} 条SQL。", 
                        "成功", wx.OK | wx.ICON_INFORMATION)
            self.log("执行结束: 成功")
        else:
            wx.CallAfter(wx.MessageBox, f"执行失败: {msg}", "失败", wx.OK | wx.ICON_ERROR)
            self.log(f"执行结束: 失败 - {msg}")
        wx.CallAfter(self.btn_exec_data.Enable)


if __name__ == "__main__":
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()