import wx
import wx.grid
import pymysql
import threading
import time

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
    'host': '159.138.133',
    'port': '3307',  # 建议使用不同端口以区分实例
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

    def analyze(self, source_conf, target_conf, log_callback=None):
        """核心对比逻辑：包含明确的异常源标记"""
        self.sqls = []
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
        super().__init__(None, title="Python 终极数据库对比工具 (结构/注释/行数)", size=(1100, 700))
        self.core = DBSyncCore()
        self.current_sqls = []

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        config_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.src_panel = DBConfigPanel(panel, "源数据库 (标准)", defaults=SOURCE_DEFAULTS)
        self.tgt_panel = DBConfigPanel(panel, "目标数据库 (待同步)", defaults=TARGET_DEFAULTS)

        config_sizer.Add(self.src_panel, 1, wx.EXPAND | wx.ALL, 5)
        config_sizer.Add(self.tgt_panel, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(config_sizer, 0, wx.EXPAND)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_compare = wx.Button(panel, label="开始全面分析 (结构+行数)", size=(200, 40))
        self.btn_compare.Bind(wx.EVT_BUTTON, self.on_compare)
        btn_sizer.AddStretchSpacer(1)
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

        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        self.txt_log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
        main_sizer.Add(self.txt_log, 0, wx.EXPAND | wx.ALL, 5)

        exec_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_exec = wx.Button(panel, label="执行同步 SQL", size=(150, 40))
        self.btn_exec.Disable()
        self.btn_exec.Bind(wx.EVT_BUTTON, self.on_execute)
        self.btn_exec.SetForegroundColour(wx.RED)
        exec_sizer.AddStretchSpacer(1)
        exec_sizer.Add(self.btn_exec, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
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
        self.txt_sql.Clear()
        self.btn_compare.Disable()
        self.btn_exec.Disable()
        threading.Thread(target=self._run_compare, args=(src, tgt), daemon=True).start()

    def _run_compare(self, src, tgt):
        try:
            self.log("任务开始...")
            report, sqls = self.core.analyze(src, tgt, log_callback=self.log)
            self.current_sqls = sqls
            wx.CallAfter(self._update_ui_results, report, sqls)
        except Exception as e:
            # 此处捕获到了 DBSyncCore.analyze 中抛出的带有【源数据库】或【目标数据库】的明确错误信息
            wx.CallAfter(wx.MessageBox, f"出错: {e}", "错误", wx.OK | wx.ICON_ERROR)
            self.log(f"异常: {e}")
        finally:
            wx.CallAfter(self.btn_compare.Enable)

    def _update_ui_results(self, report, sqls):
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

        if sqls:
            self.txt_sql.SetValue("\n".join(sqls))
            self.btn_exec.Enable()
            self.log(f"对比完成。结构差异语句: {len(sqls)} 条。")
            wx.MessageBox(f"发现差异！结构差异语句: {len(sqls)} 条。", "完成", wx.OK | wx.ICON_WARNING)
        else:
            has_data_diff = any(r[0] == 'DAT' for r in report)
            if has_data_diff:
                self.txt_sql.SetValue("-- 结构一致，但数据行数不同 (见列表 DAT 项)")
                self.log("对比完成。结构一致，数据有差异。")
                wx.MessageBox("结构一致，但发现数据量差异 (DAT)！", "提醒", wx.OK | wx.ICON_INFORMATION)
            else:
                self.txt_sql.SetValue("-- 完美一致 (结构 & 行数)")
                self.log("对比完成。完全一致。")
                wx.MessageBox("完美！结构与行数均一致。", "完成", wx.OK | wx.ICON_INFORMATION)

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
        self.log("开始执行同步...")
        # 核心 SQL 执行方法现在会返回带有 "目标数据库" 前缀的错误信息
        success, msg = self.core.execute_sql(tgt, self.current_sqls, self.log)
        if success:
            wx.CallAfter(wx.MessageBox, "结构同步成功！", "成功", wx.OK | wx.ICON_INFORMATION)
            self.log("执行结束: 成功")
        else:
            wx.CallAfter(wx.MessageBox, f"执行失败: {msg}", "失败", wx.OK | wx.ICON_ERROR)
            self.log(f"执行结束: 失败 - {msg}")
        wx.CallAfter(self.btn_exec.Enable)


if __name__ == "__main__":
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()