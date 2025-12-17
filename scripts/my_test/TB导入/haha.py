from datetime import timedelta

import mysql.connector  # pip3 install mysql-connector-python
import pandas as pd

config = {
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',
    'host': '159.138.133.34',
    'database': 'platform',
    'raise_on_warnings': True
}
client_id = 1

ecpm_deduct_ratio = 0.20
revenue_deduct_ratio = 0.20

conn = mysql.connector.connect(**config)
cursor = conn.cursor()


def get_product_id(product_name):
    """
    根据产品名称（SUBID）获取产品ID
    
    Args:
        product_name: 产品名称，可以是字符串或整数
    
    Returns:
        int: 产品ID，如果不存在则返回None
    """
    global cursor

    # 使用参数化查询，避免SQL注入和类型错误
    sql = "SELECT `id` FROM `products` WHERE `name` = %s"

    # 将product_name转换为字符串，因为name字段是VARCHAR类型
    cursor.execute(sql, (str(product_name),))
    ret = cursor.fetchall()

    pro_id = None
    if ret:
        pro_id = ret[0][0]
    return pro_id


excel_file = r'E:\data\Platform\scripts\my_test\TB导入\TB搜索.xls'
print("=== 读取Excel文件 ===")
df = pd.read_excel(excel_file, sheet_name='sheet1', header=0)
print(f"成功读取文件，数据形状: {df.shape}")
print(f"列名: {df.columns.tolist()}")
subid_list = df['SUBID'].astype(int).unique().tolist()
sorted_subids = sorted(subid_list)
print(sorted_subids)

print(f"\n=== 查询产品ID ===")
found_count = 0
not_found_count = 0

in_set = []
not_in_set = []

for subid in sorted_subids:
    product_id = get_product_id(subid)
    if product_id:
        found_count += 1
        if subid not in in_set:
            in_set.append(subid)
    else:
        not_found_count += 1

        if subid not in not_in_set:
            not_in_set.append(subid)

        str_in = f"INSERT INTO `platform`.`products` (`client_id`, `name`, `ecpm_deduct_ratio`, `revenue_deduct_ratio`, `is_active`) VALUES ( {client_id}, '{subid}', {ecpm_deduct_ratio}, {revenue_deduct_ratio}, 1);"
        # cursor.execute(str_in)
        # conn.commit()

print(f"\n=== 统计结果 ===")
print(f"总共查询: {len(sorted_subids)} 个SUBID")

print(f"找到: {in_set}")
print(f"找到: {found_count} 个")

print(f"未找到: {not_in_set}")
print(f"未找到: {not_found_count} 个")

print(f"\n=== 从Excel中查询每个SUBID的最早日期 ===")
# 确保DATE列存在
if 'DATE' not in df.columns:
    # 尝试不区分大小写查找
    date_col = None
    for col in df.columns:
        if str(col).upper().strip() == 'DATE':
            date_col = col
            break
    if date_col:
        df['DATE'] = df[date_col]
    else:
        print("错误：Excel文件中未找到DATE列")
        print(f"可用列名: {df.columns.tolist()}")
        date_col = None
else:
    date_col = 'DATE'

if 'DATE' in df.columns:
    # 将DATE列转换为日期类型
    df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')

    print(f"{'SUBID':<15} {'产品ID':<10} {'Excel最早日期':<20} {'分配历史':<50} {'日期逻辑检查':<30}")
    print("-" * 125)

    for subid in sorted_subids:
        product_id = get_product_id(subid)

        # 从Excel中查找该SUBID的最早日期
        subid_df = df[df['SUBID'].astype(str) == str(subid)]
        if len(subid_df) == 0:
            print(f"{subid:<15} {'未找到':<10} {'Excel中无数据':<20} {'-':<50} {'-':<30}")
            continue

        # 获取最早日期
        earliest_date_excel = subid_df['DATE'].min()

        if pd.isna(earliest_date_excel):
            earliest_str = "日期无效"
        else:
            # 如果是Timestamp类型，转换为date
            if isinstance(earliest_date_excel, pd.Timestamp):
                earliest_date_excel = earliest_date_excel.date()
            earliest_str = str(earliest_date_excel)

        # 查询 product_assignments 表中的分配历史
        assignment_str = ""
        date_logic_check = ""
        if product_id:
            sql_assignments = """
                              SELECT `start_date`, `end_date`, `client_id`
                              FROM `product_assignments`
                              WHERE `product_id` = %s
                              ORDER BY `start_date` ASC \
                              """
            cursor.execute(sql_assignments, (product_id,))
            assignments = cursor.fetchall()

            # 格式化分配历史
            if assignments:
                assignment_list = []
                for start_date, end_date, client_id in assignments:
                    start_str = start_date.strftime('%Y-%m-%d') if start_date else 'NULL'
                    end_str = end_date.strftime('%Y-%m-%d') if end_date else 'NULL(当前有效)'
                    assignment_list.append(f"{start_str}~{end_str}(client:{client_id})")
                assignment_str = "; ".join(assignment_list)

                # 检查Excel最早日期是否在分配历史范围内
                if not pd.isna(earliest_date_excel):
                    earliest_date_obj = earliest_date_excel
                    if isinstance(earliest_date_obj, pd.Timestamp):
                        earliest_date_obj = earliest_date_obj.date()

                    # 检查最早日期是否在任何分配记录的时间范围内
                    in_range = False
                    for start_date, end_date, client_id in assignments:
                        if end_date is None:
                            # end_date为NULL表示当前有效，检查是否>=start_date
                            if earliest_date_obj >= start_date:
                                in_range = True
                                break
                        else:
                            # 检查是否在范围内（end_date + 1天，因为end_date是包含的）
                            if start_date <= earliest_date_obj <= end_date:
                                in_range = True
                                break

                    if in_range:
                        date_logic_check = "✓ 日期在分配范围内"
                    else:
                        date_logic_check = "⚠ 日期不在分配范围内"
            else:
                assignment_str = "无分配记录"
                if not pd.isna(earliest_date_excel):
                    date_logic_check = "⚠ 无分配记录但Excel有数据"
        else:
            assignment_str = "产品未找到"
            date_logic_check = "-"

        product_id_str = str(product_id) if product_id else "未找到"
        print(f"{subid:<15} {product_id_str:<10} {earliest_str:<20} {assignment_str:<50} {date_logic_check:<30}")

print(f"\n=== 检查日期逻辑 ===")
if 'DATE' not in df.columns:
    print("警告：Excel文件中未找到DATE列，跳过日期逻辑检查")
else:
    print("检查 product_assignments 表中的日期逻辑问题（基于Excel最早日期）...")
    print(f"{'产品ID':<10} {'SUBID':<15} {'Excel最早日期':<20} {'问题类型':<20} {'详细信息':<60}")
    print("-" * 125)

    issues_found = 0
    for subid in sorted_subids:
        product_id = get_product_id(subid)
        if not product_id:
            continue

        # 从Excel中获取最早日期
        subid_df = df[df['SUBID'].astype(str) == str(subid)]
        earliest_date_excel = None
        if len(subid_df) > 0 and 'DATE' in subid_df.columns:
            earliest_date_excel = subid_df['DATE'].min()
            if not pd.isna(earliest_date_excel):
                if isinstance(earliest_date_excel, pd.Timestamp):
                    earliest_date_excel = earliest_date_excel.date()

        # 查询所有分配记录
        sql_assignments = """
                          SELECT `id`, `start_date`, `end_date`, `client_id`
                          FROM `product_assignments`
                          WHERE `product_id` = %s
                          ORDER BY `start_date` ASC \
                          """
        cursor.execute(sql_assignments, (product_id,))
        assignments = cursor.fetchall()

        if len(assignments) == 0:
            # 如果有Excel数据但没有分配记录，这是一个问题
            if earliest_date_excel:
                issues_found += 1
                earliest_str = str(earliest_date_excel)
                print(f"{product_id:<10} {subid:<15} {earliest_str:<20} {'缺少分配记录':<20} "
                      f"Excel中有数据(最早{earliest_str})但数据库无分配记录")
            continue

        # 检查1: 是否有重叠的日期范围
        for i in range(len(assignments)):
            id1, start1, end1, client1 = assignments[i]
            for j in range(i + 1, len(assignments)):
                id2, start2, end2, client2 = assignments[j]

                # 检查重叠：如果 end1 为 NULL，视为无穷大（使用一个很大的日期）
                # 如果 end2 为 NULL，也视为无穷大
                end1_val = end1 if end1 else start2 + timedelta(days=365 * 10)  # 假设NULL表示未来10年
                end2_val = end2 if end2 else start1 + timedelta(days=365 * 10)

                # 检查是否有重叠：两个区间重叠的条件是：not (end1 < start2 or start1 > end2)
                if not (end1_val < start2 or start1 > end2_val):
                    issues_found += 1
                    earliest_str = str(earliest_date_excel) if earliest_date_excel else "N/A"
                    start1_str = start1.strftime('%Y-%m-%d') if start1 else 'NULL'
                    start2_str = start2.strftime('%Y-%m-%d') if start2 else 'NULL'
                    end1_str = end1.strftime('%Y-%m-%d') if end1 else 'NULL'
                    end2_str = end2.strftime('%Y-%m-%d') if end2 else 'NULL'
                    print(f"{product_id:<10} {subid:<15} {earliest_str:<20} {'日期重叠':<20} "
                          f"记录{id1}({start1_str}~{end1_str})与记录{id2}({start2_str}~{end2_str})重叠")

        # 检查2: 是否有间隙（不连续）
        for i in range(len(assignments) - 1):
            id1, start1, end1, client1 = assignments[i]
            id2, start2, end2, client2 = assignments[i + 1]

            if end1 is None:
                # 如果第一条记录的end_date为NULL，不应该有下一条记录
                issues_found += 1
                earliest_str = str(earliest_date_excel) if earliest_date_excel else "N/A"
                print(f"{product_id:<10} {subid:<15} {earliest_str:<20} {'逻辑错误':<20} "
                      f"记录{id1}的end_date为NULL，但存在后续记录{id2}")
            elif end1 + timedelta(days=1) != start2:
                # 检查是否有间隙（end_date + 1天应该等于下一条的start_date）
                issues_found += 1
                gap_days = (start2 - end1).days - 1
                earliest_str = str(earliest_date_excel) if earliest_date_excel else "N/A"
                end1_str = end1.strftime('%Y-%m-%d') if end1 else 'NULL'
                start2_str = start2.strftime('%Y-%m-%d') if start2 else 'NULL'
                print(f"{product_id:<10} {subid:<15} {earliest_str:<20} {'日期间隙':<20} "
                      f"记录{id1}(结束于{end1_str})与记录{id2}(开始于{start2_str})之间有{gap_days}天间隙")

        # 检查3: start_date 应该 <= end_date（如果end_date不为NULL）
        for id_val, start_date, end_date, client_id in assignments:
            if end_date and start_date > end_date:
                issues_found += 1
                earliest_str = str(earliest_date_excel) if earliest_date_excel else "N/A"
                start_str = start_date.strftime('%Y-%m-%d') if start_date else 'NULL'
                end_str = end_date.strftime('%Y-%m-%d') if end_date else 'NULL'
                print(f"{product_id:<10} {subid:<15} {earliest_str:<20} {'日期错误':<20} "
                      f"记录{id_val}: start_date({start_str}) > end_date({end_str})")

        # 检查4: Excel最早日期是否早于第一条分配记录的start_date
        if earliest_date_excel and len(assignments) > 0:
            first_assignment = assignments[0]
            first_start_date = first_assignment[1]  # start_date
            if earliest_date_excel < first_start_date:
                issues_found += 1
                earliest_str = str(earliest_date_excel)
                start_str = first_start_date.strftime('%Y-%m-%d') if first_start_date else 'NULL'
                print(f"{product_id:<10} {subid:<15} {earliest_str:<20} {'日期不匹配':<20} "
                      f"Excel最早日期({earliest_str})早于第一条分配记录开始日期({start_str})")

    if issues_found == 0:
        print("✓ 未发现日期逻辑问题")
    else:
        print(f"\n共发现 {issues_found} 个日期逻辑问题")

cursor.close()
conn.close()
