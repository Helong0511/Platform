import hashlib
import time
import requests
import json

# 配置信息
BASE_URL = 'https://client.btfrx.online/api/v1'
CLIENT_ID = 1025
SECRET_KEY = 'fdedbcee-08b8-451d-9878-128a9c168bdd'


def generate_signature(client_id, req_time, secret_key, data_type=None, start_date=None, end_date=None):
    """生成签名

    Args:
        client_id: 客户ID
        req_time: 请求时间戳
        secret_key: 密钥
        data_type: 数据类型（对于 /client_data 接口是必填的，'all' 或 'day'）
        start_date: 起始日期（可选）
        end_date: 终止日期（可选）
    """
    params = {
        'client_id': str(client_id),
        'req_time': str(req_time)
    }

    # 添加参数（对于 /client_data 接口，data_type 是必填的）
    if data_type:
        params['data_type'] = str(data_type)
    if start_date:
        params['start_date'] = str(start_date)
    if end_date:
        params['end_date'] = str(end_date)

    sorted_keys = sorted(params.keys())
    temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
    temp_str = temp_str + f'&key={secret_key}'

    sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest().lower()
    return sign


def get_products():
    """获取产品列表"""
    req_time = int(time.time())
    sign = generate_signature(CLIENT_ID, req_time, SECRET_KEY)

    params = {
        'client_id': CLIENT_ID,
        'req_time': req_time,
        'sign': sign
    }

    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_products',
        headers=headers,
        json=params,
        timeout=10
    )

    return response.json()


def get_ad_data(data_type, start_date=None, end_date=None):
    """获取广告数据
    Args:
        data_type: 必填，数据类型，'all' 表示详细数据（按国家+广告单元），'day' 表示每日汇总（按产品+日期+广告单元）
        start_date: 可选，起始日期（格式：YYYY-MM-DD），不提供则使用当前月第一天
        end_date: 可选，终止日期（格式：YYYY-MM-DD），不提供则使用当前月最后一天
    """
    req_time = int(time.time())
    sign = generate_signature(CLIENT_ID, req_time, SECRET_KEY, data_type, start_date, end_date)

    params = {
        'client_id': CLIENT_ID,
        'req_time': req_time,
        'data_type': data_type,  # 必填参数
        'sign': sign
    }

    # 添加可选参数
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date

    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_data',
        headers=headers,
        json=params,
        timeout=10
    )

    return response.json()


# 使用示例
if __name__ == '__main__':
    # 获取产品列表
    products_result = get_products()
    print("产品列表:", json.dumps(products_result, indent=2, ensure_ascii=False))

    # 获取详细广告数据（按国家+广告单元）
    ad_data_result = get_ad_data(data_type='all', start_date='2026-05-27', end_date='2026-05-27')
    print("详细广告数据:", json.dumps(ad_data_result, indent=2, ensure_ascii=False))

    # 获取每日汇总数据（按产品+日期+广告单元汇总）
    daily_summary_result = get_ad_data(data_type='day', start_date='2026-05-27', end_date='2026-05-27')
    print("每日汇总数据:", json.dumps(daily_summary_result, indent=2, ensure_ascii=False))

    test = None

    if test:
        print('值为真')
    else:
        print('值为假')