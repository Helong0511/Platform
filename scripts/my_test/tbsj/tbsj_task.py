import requests
import json
import mysql.connector  # pip3 install mysql-connector-python
from typing import Optional

Headers = {'Content-Type': 'application/json;charset=utf-8'}

base_url = 'https://data.tongbaishijia.com/api/thirdservice'

username = 'BOFIT'

password = '5e2296fa9fd1434bf8a60c03cf745ce9'

config = {
    'user': 'remote',
    'password': 'kb7$rL3d8!tQ',
    'host': '159.138.133.34',
    'database': 'platform',
    'raise_on_warnings': True
}
# 连接到 MySQL 数据库
conn = mysql.connector.connect(**config)


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
        "end": "2025-11-26"
    }
    response = requests.post(
        url=base_url + '/adunit',
        headers=Headers,
        json=ad_pr,
        timeout=20
    )

    if response.status_code == 200:
        data = response.json()
        ad_data = data['data']['items']
        pro = []
        country = []
        err_co = []
        for item in ad_data:
            if item.get('country_code', '') == 'XX' or item.get('country_code', '') == 'XK':
                print(item)

            if len(item.get('country_code', '')) > 2:
                if item.get('country_code', '') not in err_co:
                    err_co.append(item.get('country_code', ''))
            else:
                if item.get('country_code', '') not in country:
                    country.append(item.get('country_code', ''))
            if item.get('product') not in pro:
                pro.append(item.get('product'))

        co_in = []
        for code in country:
            q_c = f"SELECT `country_name_zh` FROM `countries` WHERE `alpha_2_code` = '{code}'"
            cur = conn.cursor()
            cur.execute(q_c)
            ret = cur.fetchall()
            if ret:
                country_info = {
                    'country_code': code,
                    'country_name_zh': ret[0][0]
                }
                if country_info not in co_in:
                    co_in.append(country_info)
            else:
                if code not in err_co:
                    err_co.append(code)
            cur.close()

        print(pro)
        print(err_co)
        print(len(co_in), co_in)

    else:
        error_data = response.json()
        print(error_data)
except requests.exceptions.RequestException as e:
    print(f"❌ 请求失败: {str(e)}")

conn.close()
