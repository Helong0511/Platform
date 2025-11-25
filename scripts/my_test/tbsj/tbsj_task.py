import hashlib
import pytz
import requests
import json
from datetime import datetime, timedelta  # 日期时间处理
from typing import Dict, Any, Optional

Headers = {'Content-Type': 'application/json;charset=utf-8'}

base_url = 'https://data.tongbaishijia.com/api/thirdservice'

username = 'BOFIT'

password = '5e2296fa9fd1434bf8a60c03cf745ce9'


def get_token() -> Optional[str]:
    pa = {
        "username": username,
        "password": password
    }

    try:
        response = requests.post(
            url=base_url + '/token',
            headers=Headers,
            json=pa,
            timeout=20
        )

        if response.status_code == 200:
            try:
                data = response.json()
                access_token = data.get('access_token', '')
                if access_token:
                    Headers['Authorization'] = f'Bearer {access_token}'
                    return access_token
                else:
                    print(f"❌ Token获取失败: 响应中未找到access_token")
                    print(f"响应内容: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return None
            except json.JSONDecodeError:
                print(f"❌ 响应不是有效的JSON格式")
                print(f"原始响应: {response.text[:500]}")
                return None

        else:
            print(f"❌ Token获取失败，状态码: {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误信息: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"原始响应: {response.text[:500]}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {str(e)}")
        return None


Headers['Authorization'] = f'Bearer {get_token()}'

print(Headers)

try:
    ad_pr = {
        "page": 1,
        "limit": 5000,
        "start": "2025-11-01",
        "end": "2025-11-25"
    }
    response = requests.post(
        url=base_url + '/adunit',
        headers=Headers,
        json=ad_pr,
        timeout=20
    )

    if response.status_code == 200:
        data = response.json()
        print(data)
        ad_data = data['data']['items']
        pro = []
        for item in ad_data:
            print(item)
            if len(item.get('country_code'))>2:
                print(item.get('country_code'))

            if item.get('product')  not in pro:
                pro.append(item.get('product'))

        print(pro)

    else:
        error_data = response.json()
        print(error_data)
except requests.exceptions.RequestException as e:
    print(f"❌ 请求失败: {str(e)}")
