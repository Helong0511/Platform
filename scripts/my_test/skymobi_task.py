from datetime import datetime

import requests
import json

api_id = '10177'

api_key = '67b7c7fac2154bb8f59546d9b23058c9'

try:
    today_str = datetime.today().strftime('%Y-%m-%d')
    ext_path = f'https://crm.skymobi.online/api/adxh5?apikey={api_key}&date={today_str}&uid={api_id}&page=1&limit=500'
    print(ext_path)
    # 发送POST请求
    response = requests.get(url=ext_path, timeout=10)

    status_code = response.status_code

    print(f'响应状态码: {status_code}')
    print(f'响应头 Content-Type: {response.headers.get("Content-Type", "N/A")}')

    try:
        response_data = response.json()
        print(response_data)

        if status_code == 200:
            if response_data.get("ret") == 0 or response_data.get("msg") == 'ok':
                data = response_data.get("list", [])
                print(f'产品数量: {len(data)}')
                if data:
                    for item in data:
                        print(item.get('country',''))

                else:
                    print('  暂无产品数据')


        else:
            error_msg = response_data.get("detail") or response_data.get("message", "未知错误")
            print(f'错误信息: {error_msg}')

    except json.JSONDecodeError:
        print(f'原始响应: {response.text[:500]}')


except requests.exceptions.RequestException as e:
    print(f'\n❌ 请求失败: {str(e)}')
