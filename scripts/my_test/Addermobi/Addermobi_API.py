import requests
import json
import mysql.connector  # pip3 install mysql-connector-python
from typing import Optional
from datetime import datetime, timedelta  # 日期时间处理

Headers = {}

username = 'Leadwin'

password = 'lw145667'

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
        "userName": username,
        "password": password
    }

    try:
        response = requests.post(
            url='https://api.addermobi.com/api/User/loginApi',
            headers=Headers,
            json=pa,
            timeout=20
        )

        if response.status_code == 200:
            try:
                token_data = response.json()

                data = None
                if 'data' in token_data and isinstance(token_data['data'], dict):
                    data = token_data['data'].get('token', [])
                else:
                    data = token_data.get('token', [])
                if data:
                    return data
                else:
                    print(f"❌ Token获取失败: 响应中未找到token")
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
Headers['Content-Type'] = 'application/json'

today_str = datetime.now().strftime("%Y-%m-%d")

try:
    p1 = [
        {"name": "Revenue_time",
         "value": today_str,
         "displayType": "thanorequal"
         },
        {"name": "Revenue_time",
         "value": today_str,
         "displayType": "lessorequal"
         }
    ]
    ad_pr = {
        "page": 1,
        "rows": 500,
        "sort": "Revenue_time,Product_id",
        "order": "desc",
        "wheres": json.dumps(p1)
    }
    response = requests.post(
        url='https://api.addermobi.com/api/Revenue_DetailReports/GetData',
        headers=Headers,
        json=ad_pr,
        timeout=20
    )

    if response.status_code == 200:
        return_data = response.json()
        print(return_data)
        ad_data = None
        if 'rows' in return_data and isinstance(return_data['rows'], dict):
            ad_data = return_data.get('rows', [])
        else:
            ad_data = return_data.get('rows', [])

        if ad_data:
            pro = []
            country = []
            err_co = []

            cpc = 0
            for item in ad_data:
                if len(item.get('Country_Code', '')) > 2:
                    if item.get('Country_Code', '') not in err_co:
                        err_co.append(item.get('Country_Code', ''))
                else:
                    if item.get('Country_Code', '') not in country:
                        country.append(item.get('Country_Code', ''))
                if item.get('link') not in pro:
                    pro.append(item.get('link'))

                # print(f"\n产品id：{item.get('Product_id', '')}")
                # print(f"用户id：{item.get('User_Id', '')}")
                # print(f"智能链接：{item.get('shortUrl', '')}")
                # print(f"AdsLinkId：{item.get('AdsLinkId', '')}")
                # print(f"收入时间：{item.get('Revenue_time', '')}")
                # print(f"广告链接：{item.get('link', '')}")
                # print(f"广告单元：{item.get('Ad_Unit', '')}")
                # print(f"国家代码：{item.get('Country_Code', '')}")
                # print(f"用户名：{item.get('UserName', '')}")
                # print(f"广告请求：{item.get('AdRequests', 0)}")
                # print(f"匹配数：{item.get('MatchedAdRequests', 0)}")
                # print(f"覆盖率：{item.get('AdRequestsCoverage', 0)}")
                # print(f"广告展示：{item.get('Impressions', 0)}")
                # print(f"广告点击：{item.get('Clicks', 0)}")
                # print(f"预估收益：{item.get('EstimatedEarnings', 0)}")
                # print(f"可见度：{item.get('ActiveViewViewability', '')}")
                # print(f"可见时长(毫秒)：{item.get('ActiveViewTime', '')}")
                # print(f"CTR：{item.get('CTR', 0)}")
                # print(f"ecpm：{item.get('eCPM', 0)}")
                print(f"cpc：{item.get('CPC', 0)}")
                # print(f"产品名称：{item.get('ProductName', '')}")
                print(f"覆盖率：{item.get('AdRequestsCoverage', 0)}")
                cpc = cpc + item.get('CPC', 0)

            co_in = []
            for code in country:
                q_c = f"SELECT `country_name_zh` FROM `countries` WHERE `alpha_2_code` = '{code}'"
                cur = conn.cursor()
                cur.execute(q_c)
                ret = cur.fetchall()
                if ret:
                    country_info = {
                        'Country_Code': code,
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
            print(cpc, cpc/4)
    else:
        error_data = response.json()
        print(error_data)
except requests.exceptions.RequestException as e:
    print(f"❌ 请求失败: {str(e)}")

conn.close()
