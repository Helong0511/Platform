import mysql.connector  # pip3 install mysql-connector-python
import pandas as pd
import os
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from collections import Counter

config = {
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',
    'host': '43.156.101.243',
    'database': 'platform',
    'raise_on_warnings': True
}

# Excel 文件路径
excel_file = Path(__file__).parent / '10528渠道ip+click id.xlsx'

def check_click_ids():
    """检查 Excel 文件中的 click_id 是否存在于数据库中"""
    
    # 1. 读取 Excel 文件
    print(f"正在读取 Excel 文件: {excel_file}")
    try:
        df = pd.read_excel(excel_file)
        print(f"成功读取 Excel 文件，共 {len(df)} 行数据")
        print(f"列名: {df.columns.tolist()}")
        print()
    except Exception as e:
        print(f"❌ 读取 Excel 文件失败: {e}")
        return
    
    # 2. 查找 click_id 列（支持多种可能的列名）
    click_id_column = None
    possible_names = ['affiliateClickId', 'affiliateclickid', 'affiliate_click_id', 
                      'click_id', 'click id', 'Click ID', 'Click_ID', 'clickid', 'ClickId']
    
    for col in df.columns:
        if col.strip() in possible_names or col.strip().lower() in [name.lower() for name in possible_names]:
            click_id_column = col
            break
    
    if click_id_column is None:
        print("❌ 未找到 click_id 列")
        print(f"可用的列名: {df.columns.tolist()}")
        return
    
    print(f"✅ 找到 click_id 列: {click_id_column} (对应数据库 clicks.click_id)")
    
    # 3. 提取 click_id 列表（去除空值和占位符）
    # 处理 click_id 列，转换为字符串并去除空格
    df[click_id_column] = df[click_id_column].astype(str).str.strip()
    
    # 过滤掉占位符格式的值（如 {AFF_CLICK_ID}）
    placeholder_mask = df[click_id_column].str.contains(r'[{}]', na=False)
    valid_mask = ~placeholder_mask & (df[click_id_column] != '') & (df[click_id_column] != 'nan') & (df[click_id_column].notna())
    
    placeholder_df = df[placeholder_mask]
    valid_df = df[valid_mask]
    
    click_ids = valid_df[click_id_column].tolist()
    placeholder_ids = placeholder_df[click_id_column].tolist()
    
    print(f"原始数据: {len(df)} 行")
    if len(placeholder_ids) > 0:
        print(f"过滤占位符: {len(placeholder_ids)} 个 (如 {{AFF_CLICK_ID}} 格式)")
        # 显示被过滤的占位符（如果数量不多）
        if len(placeholder_ids) <= 10:
            print("  被过滤的占位符:")
            for pid in placeholder_ids:
                print(f"    - {pid}")
    print(f"有效 click_id: {len(click_ids)} 个")
    print()
    
    # 3.5. 检查重复的 click_id
    click_id_counter = Counter(click_ids)
    duplicate_click_ids = {cid: count for cid, count in click_id_counter.items() if count > 1}
    
    if duplicate_click_ids:
        print(f"⚠️ 发现 {len(duplicate_click_ids)} 个重复的 click_id:")
        print("-" * 80)
        for cid, count in sorted(duplicate_click_ids.items()):
            print(f"  {cid}: 出现 {count} 次")
        
        # 找出重复值所在的行号（Excel 行号，从 1 开始，第 1 行是表头）
        duplicate_rows = {}
        for idx, row in df.iterrows():
            cid = str(row[click_id_column]).strip()
            # 检查是否是有效的重复值（不是占位符）
            if cid in duplicate_click_ids and '{' not in cid and '}' not in cid and cid not in ['', 'nan', 'None']:
                excel_row = idx + 2  # DataFrame 索引从 0 开始，Excel 行号从 2 开始（第 1 行是表头）
                if cid not in duplicate_rows:
                    duplicate_rows[cid] = []
                duplicate_rows[cid].append(excel_row)
        
        print("\n重复 click_id 所在的行号:")
        for cid, rows in sorted(duplicate_rows.items()):
            print(f"  {cid}: 行 {', '.join(map(str, rows))}")
        print()
    else:
        print("✅ 没有发现重复的 click_id")
        print()
    
    if not click_ids:
        print("❌ Excel 文件中没有有效的 click_id（所有值都是占位符或为空）")
        return
    
    # 4. 连接数据库
    print("正在连接数据库...")
    try:
        con = mysql.connector.connect(**config)
        cur = con.cursor()
        print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return
    
    # 5. 批量查询 click_id 是否存在
    print(f"\n开始检查 {len(click_ids)} 个 click_id...")
    print("-" * 80)
    
    # 使用 IN 查询提高效率
    placeholders = ','.join(['%s'] * len(click_ids))
    query = f"SELECT click_id FROM `clicks` WHERE click_id IN ({placeholders})"
    
    try:
        cur.execute(query, click_ids)
        existing_click_ids = {row[0] for row in cur.fetchall()}
        
        # 6. 统计结果
        missing_click_ids = [cid for cid in click_ids if cid not in existing_click_ids]
        
        print(f"\n📊 检查结果统计:")
        print(f"  总数量: {len(click_ids)}")
        print(f"  ✅ 存在: {len(existing_click_ids)}")
        print(f"  ❌ 不存在: {len(missing_click_ids)}")
        print()
        
        # 7. 显示不存在的 click_id
        if missing_click_ids:
            print(f"❌ 以下 {len(missing_click_ids)} 个 click_id 在数据库中不存在:")
            print("-" * 80)
            for i, cid in enumerate(missing_click_ids, 1):
                print(f"  {i}. {cid}")
        else:
            print("✅ 所有 click_id 都存在于数据库中！")
        
        # 8. 可选：显示存在的 click_id（如果数量不多）
        if len(existing_click_ids) <= 20:
            print(f"\n✅ 存在的 click_id ({len(existing_click_ids)} 个):")
            print("-" * 80)
            for i, cid in enumerate(sorted(existing_click_ids), 1):
                print(f"  {i}. {cid}")
        
        # 9. 在 Excel 中标记不存在的行和重复的行
        if missing_click_ids or duplicate_click_ids:
            print(f"\n正在标记 Excel 文件...")
            try:
                # 使用 openpyxl 打开 Excel 文件
                wb = load_workbook(excel_file)
                ws = wb.active
                
                # 定义填充颜色
                red_fill = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")  # 红色：不存在
                yellow_fill = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")  # 黄色：重复
                
                # 找到 click_id 列的索引（Excel 列号从 1 开始）
                header_row = 1
                click_id_col_idx = None
                for col_idx, cell in enumerate(ws[header_row], 1):
                    if cell.value == click_id_column:
                        click_id_col_idx = col_idx
                        break
                
                if click_id_col_idx is None:
                    print(f"⚠️ 警告: 在 Excel 中未找到列 '{click_id_column}'，无法标记行")
                else:
                    missing_click_ids_set = set(missing_click_ids)  # 使用集合提高查找效率
                    duplicate_click_ids_set = set(duplicate_click_ids.keys())  # 重复的 click_id
                    
                    missing_marked_count = 0
                    duplicate_marked_count = 0
                    
                    for row_idx in range(2, ws.max_row + 1):  # 从第 2 行开始（跳过表头）
                        cell_value = ws.cell(row=row_idx, column=click_id_col_idx).value
                        if cell_value is not None:
                            # 转换为字符串并去除空格
                            cell_str = str(cell_value).strip()
                            # 检查是否有效值（且不是占位符）
                            if cell_str and cell_str not in ['', 'nan', 'None'] and '{' not in cell_str and '}' not in cell_str:
                                # 优先标记不存在的（红色），然后是重复的（黄色）
                                if cell_str in missing_click_ids_set:
                                    # 标记整行为红色（不存在）
                                    for col in range(1, ws.max_column + 1):
                                        ws.cell(row=row_idx, column=col).fill = red_fill
                                    missing_marked_count += 1
                                elif cell_str in duplicate_click_ids_set:
                                    # 标记整行为黄色（重复）
                                    for col in range(1, ws.max_column + 1):
                                        ws.cell(row=row_idx, column=col).fill = yellow_fill
                                    duplicate_marked_count += 1
                    
                    # 保存文件
                    output_file = excel_file.parent / f"{excel_file.stem}_标记.xlsx"
                    wb.save(output_file)
                    
                    print(f"✅ 标记完成，保存到: {output_file}")
                    if missing_marked_count > 0:
                        print(f"   🔴 红色标记（不存在）: {missing_marked_count} 行")
                    if duplicate_marked_count > 0:
                        print(f"   🟡 黄色标记（重复）: {duplicate_marked_count} 行")
                    
            except Exception as e:
                print(f"⚠️ 标记 Excel 文件时出错: {e}")
                print("   请确保已安装 openpyxl: pip install openpyxl")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
    finally:
        cur.close()
        con.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    check_click_ids()
