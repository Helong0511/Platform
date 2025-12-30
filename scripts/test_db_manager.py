#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据库管理工具的SQL解析功能
"""

import os
import sys
from db_manager_gui import SQLParser

def test_sql_parser():
    """测试SQL解析器"""
    # 获取SQL文件路径
    sql_file = os.path.join(os.path.dirname(__file__), "data", "platform20251230.sql")
    
    if not os.path.exists(sql_file):
        print(f"错误: SQL文件不存在: {sql_file}")
        return False
    
    try:
        # 创建解析器
        parser = SQLParser(sql_file)
        
        # 解析SQL文件
        tables = parser.parse()
        
        print(f"成功解析 {len(tables)} 个表\n")
        
        # 统计CPL表和其他表
        cpl_tables = [name for name, info in tables.items() if info['is_cpl']]
        other_tables = [name for name, info in tables.items() if not info['is_cpl']]
        
        print(f"CPL表系列 ({len(cpl_tables)} 个):")
        for table in sorted(cpl_tables):
            print(f"  - {table}")
        
        print(f"\n其他表 ({len(other_tables)} 个):")
        for table in sorted(other_tables):
            print(f"  - {table}")
        
        # 显示一个示例表的结构
        if tables:
            example_table = list(tables.keys())[0]
            table_info = tables[example_table]
            print(f"\n示例表 '{example_table}' 的结构:")
            print(f"  字段数: {len(table_info['columns'])}")
            print(f"  索引数: {len(table_info['indexes'])}")
            print(f"  外键数: {len(table_info['foreign_keys'])}")
            print(f"  注释: {table_info['comment']}")
            
            if table_info['columns']:
                print(f"\n  前3个字段:")
                for col in table_info['columns'][:3]:
                    print(f"    - {col['name']} ({col['type']})")
        
        return True
        
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_sql_parser()
    sys.exit(0 if success else 1)

