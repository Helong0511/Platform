import hashlib
import time
import requests
import json

# domain = 'king-sms.com'
domain = 'btfrx.online'

product_url = f'https://client.{domain}/api/v1/client_products'
data_url = f'https://client.{domain}/api/v1/client_data'

if domain == 'king-sms.com':
    APP_ID = 1010
    SECRET_KEY = 'a481444f-3a12-471a-8c89-2d2576b7fa14'
else:
    APP_ID = 1007
    SECRET_KEY = 'ec5875f0-d100-4e1f-8304-4903121f5560'

Headers = {'Content-Type': 'application/json'}

product_params = {
    'client_id': str(APP_ID),
    'req_time': str(int(time.time()))
}

sorted_keys = sorted(product_params.keys())
temp_str = '&'.join([f"{key}={product_params[key]}" for key in sorted_keys])
temp_str += f'&key={SECRET_KEY}'
sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest()
product_params['sign'] = sign.lower()

ad_data_params = {
    'client_id': str(APP_ID),
    'req_time': str(int(time.time())),
    'data_type': 'day',  # all:表示全部国家的详细数据；day:表示产品按天统计的数据
    'start_date': '2025-11-20',
    'end_date': '2025-11-26'
}

sorted_keys = sorted(ad_data_params.keys())
temp_str = '&'.join([f"{key}={ad_data_params[key]}" for key in sorted_keys])
temp_str += f'&key={SECRET_KEY}'
sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest()
ad_data_params['sign'] = sign.lower()

try:
    # 发送POST请求
    response = requests.post(
        url=product_url,
        headers=Headers,
        json=product_params,  # 使用JSON格式发送
        timeout=10
    )

    status_code = response.status_code

    print(f'响应状态码: {status_code}')
    print(f'响应头 Content-Type: {response.headers.get("Content-Type", "N/A")}')

    try:
        response_data = response.json()
        print(response_data)
        print(f'响应内容: {json.dumps(response_data, indent=2, ensure_ascii=False)}')

        if status_code == 200:
            if response_data.get("code") == 200 or response_data.get("success"):
                data = response_data.get("data", [])
                print(f'产品数量: {len(data)}')
                if data:
                    print('\n产品列表:')
                    for i, product in enumerate(data, 1):
                        print(f'  {i}. ID: {product.get("id")}, 名称: {product.get("name")}')
                else:
                    print('  暂无产品数据')


        else:
            error_msg = response_data.get("detail") or response_data.get("message", "未知错误")
            print(f'错误信息: {error_msg}')

    except json.JSONDecodeError:
        print(f'原始响应: {response.text[:500]}')


except requests.exceptions.RequestException as e:
    print(f'\n❌ 请求失败: {str(e)}')

try:
    # 发送POST请求
    response = requests.post(
        url=data_url,
        headers=Headers,
        json=ad_data_params,  # 使用JSON格式发送
        timeout=10
    )

    status_code = response.status_code
    print(f'响应状态码: {status_code}')
    print(f'响应头 Content-Type: {response.headers.get("Content-Type", "N/A")}')

    try:
        response_data = response.json()
        print(response_data)
        if status_code == 200:
            if response_data.get("code") == 200 or response_data.get("success"):
                data = response_data.get("data", [])
                print(f'\n✅ 查询成功！')
                print(f'广告数据条数: {len(data)}')
                if data:
                    for item in data:
                        print(f'\n日期: {item.get("date")}')
                        print(f'产品: {item.get("product_name")}')
                        print(f'国家代码: {item.get("country_code")}')
                        print(f'国家名称: {item.get("country_name_zh")}')
                        print(f'请求数: {item.get("request_count")}')
                        print(f'匹配数: {item.get("match_count")}')
                        print(f'覆盖率: {item.get("coverage_rate")}%')
                        print(f'展示数: {item.get("display_count")}')
                        print(f'展示率: {item.get("display_rate")}%')
                        print(f'点击数: {item.get("click_count")}')
                        print(f'点击率: {item.get("click_rate")}%')
                        print(f'eCPM: {item.get("ecpm")}')
                        print(f'收益: {item.get("revenue")}')
                else:
                    print('  暂无广告数据')
            else:
                print(f'\n❌ 查询失败: {response_data.get("message", "未知错误")}')

        else:
            print(f'\n❌ 请求失败，状态码: {status_code}')
            error_msg = response_data.get("detail") or response_data.get("message", "未知错误")
            print(f'错误信息: {error_msg}')

    except json.JSONDecodeError:
        print(f'\n❌ 响应不是有效的JSON格式')
        print(f'原始响应: {response.text[:500]}')


except requests.exceptions.RequestException as e:
    print(f'\n❌ 请求失败: {str(e)}')
