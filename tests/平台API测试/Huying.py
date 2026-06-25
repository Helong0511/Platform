import hashlib
import time
import requests
import json

# 配置信息
BASE_URL = 'https://client.btfrx.online/api/v1'
CLIENT_ID = 1028
SECRET_KEY = '65006a7c-1083-41b4-a255-3e9904eea930'


def generate_signature(client_id, req_time, secret_key, data_type=None, dimension=None, start_date=None, end_date=None):
    """生成签名

    Args:
        client_id: 客户ID
        req_time: 请求时间戳
        secret_key: 密钥
        data_type: 数据类型（对于 /client_data 接口是必填的，'all' 或 'day'）
        dimension: 统计维度（可选，country / ad_unit / country_ad_unit）
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
    if dimension:
        params['dimension'] = str(dimension)
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


def get_ad_data(data_type, start_date=None, end_date=None, dimension=None):
    """获取广告数据
    Args:
        data_type: 必填，'all' 明细 或 'day' 日汇总
        start_date: 可选，起始日期（格式：YYYY-MM-DD）
        end_date: 可选，终止日期（格式：YYYY-MM-DD）
        dimension: 可选，country / ad_unit / country_ad_unit（与后台报表一致；建议双 API 客户必传）
    """
    req_time = int(time.time())
    sign = generate_signature(CLIENT_ID, req_time, SECRET_KEY, data_type, dimension, start_date, end_date)

    params = {
        'client_id': CLIENT_ID,
        'req_time': req_time,
        'data_type': data_type,  # 必填参数
        'sign': sign
    }

    # 添加可选参数
    if dimension:
        params['dimension'] = dimension
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


# 使用示例（日期为当天 2026-06-24）
if __name__ == '__main__':
    today = '2026-06-23'

    # # 获取产品列表
    # products_result = get_products()
    # print("产品列表:", json.dumps(products_result, indent=2, ensure_ascii=False))

    # 获取详细广告数据（按国家维度，推荐）  country / ad_unit / country_ad_unit
    ad_data_result = get_ad_data(data_type='all', dimension='ad_unit', start_date=today, end_date=today)
    # print(json.dumps(ad_data_result, indent=2, ensure_ascii=False))

    product_name = []

    data = ad_data_result.get('data',[])
    if data:
        for item in data:
            # print(item.get('date',''),item.get('product_name',''),item.get('country_code',''),item.get('country_name_zh',''),item.get('request_count',''),item.get('match_count',''),item.get('coverage_rate',''),item.get('display_count',''),item.get('display_rate',''),item.get('click_count',''),item.get('click_rate',''),item.get('viewability_rate',''),item.get('cpc',''),item.get('pageviews',''),item.get('ecpm',''),item.get('revenue',''))

            if item.get('product_name','') not in product_name:
                print(item.get('product_name',''))
                product_name.append(item.get('product_name',''))

    print(len(product_name))

    product = sorted(product_name)
    print(product)

    # # 获取每日汇总（按国家维度）
    # daily_summary_result = get_ad_data(data_type='day', dimension='country', start_date=today, end_date=today)
    # print("按国家-每日汇总:", json.dumps(daily_summary_result, indent=2, ensure_ascii=False))