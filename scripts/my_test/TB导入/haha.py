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

product_id = 78

for tj in not_in_set:
    product_assignments_app_sql = f"INSERT INTO `platform`.`product_assignments` (`product_id`, `client_id`, `start_date`, `end_date`) VALUES ({product_id}, 1000, '2025-12-15', NULL);"

    product_id = product_id + 1

    print(product_assignments_app_sql)
    cursor.execute(product_assignments_app_sql)
    conn.commit()

cursor.close()
conn.close()
