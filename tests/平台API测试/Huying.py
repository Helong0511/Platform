import hashlib
import time

import requests

# 配置信息
# BASE_URL = 'https://client.btfrx.online/api/v1'  # 线上
BASE_URL = 'http://127.0.0.1:8960/api/v1'  # 本地
CLIENT_ID = 1028
SECRET_KEY = '65006a7c-1083-41b4-a255-3e9904eea930'


def generate_signature(
        client_id,
        req_time,
        secret_key,
        data_type=None,
        dimension=None,
        start_date=None,
        end_date=None,
        page=None,
        page_size=None,
):
    """生成签名

    Args:
        client_id: 客户ID
        req_time: 请求时间戳
        secret_key: 密钥
        data_type: 数据类型（对于 /client_data 接口是必填的，'all' 或 'day'）
        dimension: 统计维度（可选，country / ad_unit / country_ad_unit）
        start_date: 起始日期（可选）
        end_date: 终止日期（可选）
        page: 页码（可选，显式传入时参与签名）
        page_size: 每页条数（可选，显式传入时参与签名）
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
    if page is not None:
        params['page'] = str(page)
    if page_size is not None:
        params['page_size'] = str(page_size)

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


def get_ad_data(
        data_type,
        start_date=None,
        end_date=None,
        dimension=None,
        page=None,
        page_size=None,
):
    """获取广告数据（单页）
    Args:
        data_type: 必填，'all' 明细 或 'day' 日汇总
        start_date: 可选，起始日期（格式：YYYY-MM-DD）
        end_date: 可选，终止日期（格式：YYYY-MM-DD）
        dimension: 可选，country / ad_unit / country_ad_unit（与后台报表一致；建议双 API 客户必传）
        page: 可选，页码（从 1 开始）；不传默认第 1 页
        page_size: 可选，每页条数；不传默认 1000，最大 5000
    """
    req_time = int(time.time())
    sign = generate_signature(
        CLIENT_ID,
        req_time,
        SECRET_KEY,
        data_type,
        dimension,
        start_date,
        end_date,
        page,
        page_size,
    )

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
    if page is not None:
        params['page'] = page
    if page_size is not None:
        params['page_size'] = page_size

    headers = {'Content-Type': 'application/json'}
    response = requests.post(
        f'{BASE_URL}/client_data',
        headers=headers,
        json=params,
        timeout=10
    )

    return response.json()


def get_all_ad_data(data_type, start_date=None, end_date=None, dimension=None, page_size=5000):
    """自动分页拉取全部广告数据（默认每页 5000 条，减少请求次数）"""
    all_rows = []
    page = 1
    total = None

    while True:
        result = get_ad_data(
            data_type=data_type,
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
            page=page,
            page_size=page_size,
        )
        if result.get('code') != 200:
            return result

        rows = result.get('data') or []
        all_rows.extend(rows)
        total = result.get('total', len(all_rows))
        current_page = result.get('page', page)
        total_pages = result.get('total_pages') or (
            (total + page_size - 1) // page_size if total else 1
        )

        print(
            f"已拉取第 {current_page}/{total_pages} 页，"
            f"本页 {len(rows)} 条，累计 {len(all_rows)}/{total} 条"
        )

        if len(all_rows) >= total or not rows or current_page >= total_pages:
            break
        page += 1

    return {
        'code': 200,
        'message': f'成功获取 {len(all_rows)} 条广告数据（共 {total} 条）',
        'data': all_rows,
        'total': total,
        'page': 1,
        'page_size': len(all_rows),
    }


# 使用示例（日期为当天 2026-06-24）
if __name__ == '__main__':
    start_date = '2026-07-01'
    end_date = '2026-07-06'

    # # 获取产品列表
    # products_result = get_products()
    # print("产品列表:", json.dumps(products_result, indent=2, ensure_ascii=False))

    # 获取详细广告数据（按国家维度，推荐）  country / ad_unit / ad_unit_country
    ad_data_result = get_all_ad_data(data_type='day', dimension='country', start_date=start_date, end_date=end_date)
    # ad_data_result = get_all_ad_data(data_type='all', start_date=start_date, end_date=end_date)
    print(f"共获取 {len(ad_data_result.get('data', []))}/{ad_data_result.get('total', '?')} 条")
    # print(json.dumps(ad_data_result, indent=2, ensure_ascii=False))

    need = [
        "food.fanquer.com",
        "design.fanquer.com"
    ]

    data = ad_data_result.get('data', [])
    if data:
        for item in data:
            if item.get('product_name', '') in need:
                print('含有数据：', item)

    # # 获取每日汇总（按国家维度）
    # daily_summary_result = get_ad_data(data_type='day', dimension='country', start_date=today, end_date=today)
    # print("按国家-每日汇总:", json.dumps(daily_summary_result, indent=2, ensure_ascii=False))
