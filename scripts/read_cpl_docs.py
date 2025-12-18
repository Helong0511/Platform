#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 CPL 资料文档
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def read_docx():
    """读取 .docx 文件"""
    try:
        from docx import Document
        doc_path = 'scripts/CPL资料/说明书.docx'
        if not os.path.exists(doc_path):
            print(f"文件不存在: {doc_path}")
            return
        
        doc = Document(doc_path)
        print("=" * 80)
        print("说明书.docx 内容")
        print("=" * 80)
        
        # 读取段落
        print("\n【段落内容】")
        for i, para in enumerate(doc.paragraphs, 1):
            text = para.text.strip()
            if text:
                print(f"{i}. {text}")
        
        # 读取表格
        if doc.tables:
            print("\n【表格内容】")
            for table_idx, table in enumerate(doc.tables, 1):
                print(f"\n--- 表格 {table_idx} ---")
                for row_idx, row in enumerate(table.rows, 1):
                    row_data = [cell.text.strip() for cell in row.cells]
                    if any(row_data):  # 只打印非空行
                        print(f"行 {row_idx}: {' | '.join(row_data)}")
    except ImportError:
        print("需要安装 python-docx: pip install python-docx")
    except Exception as e:
        print(f"读取 .docx 失败: {e}")
        import traceback
        traceback.print_exc()

def read_xlsx():
    """读取 .xlsx 文件"""
    try:
        import pandas as pd
        xls_path = 'scripts/CPL资料/CPL系统界面.xlsx'
        if not os.path.exists(xls_path):
            print(f"文件不存在: {xls_path}")
            return
        
        xls = pd.ExcelFile(xls_path)
        print("\n" + "=" * 80)
        print("CPL系统界面.xlsx 内容")
        print("=" * 80)
        
        print(f"\n工作表列表: {xls.sheet_names}")
        
        for sheet_name in xls.sheet_names:
            print(f"\n{'=' * 80}")
            print(f"工作表: {sheet_name}")
            print('=' * 80)
            df = pd.read_excel(xls, sheet_name=sheet_name)
            # 打印所有数据
            print(df.to_string(index=False))
            print()
    except ImportError as e:
        print(f"需要安装库: pip install pandas openpyxl")
    except Exception as e:
        print(f"读取 .xlsx 失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    read_docx()
    read_xlsx()

