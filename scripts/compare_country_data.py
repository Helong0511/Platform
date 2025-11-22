#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比两个国家代码SQL文件的差异
"""

import re
from collections import defaultdict

def parse_sql_file(file_path):
    """解析SQL文件，提取表结构和数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取表名
    table_match = re.search(r'CREATE TABLE.*?`(\w+)`', content, re.IGNORECASE)
    table_name = table_match.group(1) if table_match else None
    
    # 提取字段信息
    fields = []
    field_matches = re.findall(r'`(\w+)`\s+[^,]+(?:COMMENT\s+[\'"]?([^\'"]+)[\'"]?)?', content)
    for match in field_matches:
        fields.append(match[0])
    
    # 提取INSERT语句中的数据
    insert_match = re.search(r'INSERT INTO.*?VALUES\s+(.*?);', content, re.DOTALL | re.IGNORECASE)
    if not insert_match:
        return None, None, None
    
    data_section = insert_match.group(1)
    
    # 解析数据行
    records = []
    # 匹配单行数据：(值1, 值2, ...)
    pattern = r'\(([^)]+)\)'
    matches = re.findall(pattern, data_section)
    
    for match in matches:
        # 解析值，处理引号和转义
        values = []
        current_value = ""
        in_quotes = False
        quote_char = None
        i = 0
        while i < len(match):
            char = match[i]
            if not in_quotes and char in ["'", '"']:
                in_quotes = True
                quote_char = char
                current_value += char
            elif in_quotes and char == quote_char:
                # 检查是否是转义的引号
                if i + 1 < len(match) and match[i + 1] == quote_char:
                    current_value += char + char
                    i += 1
                elif i + 1 < len(match) and match[i + 1] == '\\':
                    current_value += char
                    i += 1
                else:
                    in_quotes = False
                    quote_char = None
                    current_value += char
            elif not in_quotes and char == ',':
                values.append(current_value.strip().strip("'\" "))
                current_value = ""
            else:
                current_value += char
            i += 1
        if current_value:
            values.append(current_value.strip().strip("'\" "))
        records.append(values)
    
    return table_name, fields, records

def compare_files():
    """对比两个文件"""
    file1 = 'scripts/国家代码.sql'
    file2 = 'scripts/ISO3166-1.sql'
    
    print("=" * 80)
    print("国家代码SQL文件对比分析")
    print("=" * 80)
    
    # 解析文件1
    table1, fields1, records1 = parse_sql_file(file1)
    print(f"\n【文件1】{file1}")
    print(f"  表名: {table1}")
    print(f"  字段数: {len(fields1)}")
    print(f"  字段: {', '.join(fields1)}")
    print(f"  记录数: {len(records1)}")
    
    # 解析文件2
    table2, fields2, records2 = parse_sql_file(file2)
    print(f"\n【文件2】{file2}")
    print(f"  表名: {table2}")
    print(f"  字段数: {len(fields2)}")
    print(f"  字段: {', '.join(fields2)}")
    print(f"  记录数: {len(records2)}")
    
    # 字段对比
    print("\n" + "=" * 80)
    print("【表结构差异】")
    print("=" * 80)
    
    # 字段映射关系
    field_mapping = {
        'iso_code_2': 'alpha_2_code',
        'iso_code_3': 'alpha_3_code',
        'iso_code_numeric': 'numeric_code',
        'name_en': 'country_name_en',
        'name_zh': 'country_name_zh'
    }
    
    print(f"\n文件1独有字段: {set(fields1) - set(field_mapping.keys())}")
    print(f"文件2独有字段: {set(fields2) - set(field_mapping.values())}")
    print(f"  文件2额外字段: official_name_zh, official_name_en, independent_status, continent, subregion")
    
    # 数据对比 - 基于ISO代码
    print("\n" + "=" * 80)
    print("【数据差异】")
    print("=" * 80)
    
    # 构建索引：ISO代码 -> 记录
    data1_dict = {}
    data2_dict = {}
    
    # 文件1：iso_code_2 在索引1
    for record in records1:
        if len(record) >= 1:
            code = record[0].strip("'\" ")
            data1_dict[code] = record
    
    # 文件2：alpha_2_code 在索引1
    for record in records2:
        if len(record) >= 1:
            code = record[1].strip("'\" ")  # 跳过id字段
            data2_dict[code] = record
    
    # 找出只在文件1中的记录
    only_in_file1 = set(data1_dict.keys()) - set(data2_dict.keys())
    # 找出只在文件2中的记录
    only_in_file2 = set(data2_dict.keys()) - set(data1_dict.keys())
    # 共同记录
    common_codes = set(data1_dict.keys()) & set(data2_dict.keys())
    
    print(f"\n文件1总记录数: {len(data1_dict)}")
    print(f"文件2总记录数: {len(data2_dict)}")
    print(f"共同记录数: {len(common_codes)}")
    print(f"仅在文件1中的记录数: {len(only_in_file1)}")
    print(f"仅在文件2中的记录数: {len(only_in_file2)}")
    
    if only_in_file1:
        print(f"\n【仅在文件1中的国家代码】({len(only_in_file1)}个):")
        for code in sorted(only_in_file1):
            record = data1_dict[code]
            name_zh = record[4] if len(record) > 4 else "N/A"
            name_en = record[3] if len(record) > 3 else "N/A"
            print(f"  {code}: {name_zh} ({name_en})")
    
    if only_in_file2:
        print(f"\n【仅在文件2中的国家代码】({len(only_in_file2)}个):")
        for code in sorted(only_in_file2):
            record = data2_dict[code]
            name_zh = record[3] if len(record) > 3 else "N/A"  # 跳过id
            name_en = record[4] if len(record) > 4 else "N/A"
            print(f"  {code}: {name_zh} ({name_en})")
    
    # 对比共同记录的名称差异
    print("\n" + "=" * 80)
    print("【共同记录的名称差异】")
    print("=" * 80)
    
    name_differences = []
    for code in sorted(common_codes):
        rec1 = data1_dict[code]
        rec2 = data2_dict[code]
        
        # 文件1: iso_code_2, iso_code_3, iso_code_numeric, name_en, name_zh
        # 文件2: id, alpha_2_code, alpha_3_code, numeric_code, country_name_zh, country_name_en, ...
        
        name_zh_1 = rec1[4] if len(rec1) > 4 else ""
        name_en_1 = rec1[3] if len(rec1) > 3 else ""
        name_zh_2 = rec2[3] if len(rec2) > 3 else ""  # 跳过id
        name_en_2 = rec2[4] if len(rec2) > 4 else ""
        
        if name_zh_1 != name_zh_2 or name_en_1 != name_en_2:
            name_differences.append({
                'code': code,
                'zh_1': name_zh_1,
                'zh_2': name_zh_2,
                'en_1': name_en_1,
                'en_2': name_en_2
            })
    
    if name_differences:
        print(f"\n发现 {len(name_differences)} 个名称差异:")
        for diff in name_differences[:20]:  # 只显示前20个
            print(f"\n  代码: {diff['code']}")
            if diff['zh_1'] != diff['zh_2']:
                print(f"    中文名 - 文件1: {diff['zh_1']}")
                print(f"    中文名 - 文件2: {diff['zh_2']}")
            if diff['en_1'] != diff['en_2']:
                print(f"    英文名 - 文件1: {diff['en_1']}")
                print(f"    英文名 - 文件2: {diff['en_2']}")
        if len(name_differences) > 20:
            print(f"\n  ... 还有 {len(name_differences) - 20} 个差异未显示")
    else:
        print("\n所有共同记录的名称完全一致")
    
    print("\n" + "=" * 80)
    print("对比完成")
    print("=" * 80)

if __name__ == '__main__':
    compare_files()

