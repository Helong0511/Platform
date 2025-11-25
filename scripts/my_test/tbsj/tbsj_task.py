import hashlib

import pytz
import requests
import json
from datetime import datetime, timedelta  # 日期时间处理

Headers = {'Content-Type': 'application/json;;charset=utf-8'}

url = 'https://data.tongbaishijia.com/api/thirdservice'

appKey = '07ycrvnf'

apiSecret = 'cglnhl8pbg8zl4b9a44c4qofdrb6rwn4'


def generate_sign(params: dict, api_secret: str = apiSecret) -> str:
    """
    根据参数和 apiSecret 生成签名
    规则：
    1. 按参数名 ASCII 升序排序（排除 sign）
    2. 拼接成 key + value 的字符串
    3. 在首尾拼接 apiSecret
    4. 全部转为小写
    5. 进行 MD5，结果转小写
    """
    # 1. 排序并拼接参数
    sorted_items = sorted((k, v) for k, v in params.items() if k != "sign")
    query_str = "".join(f"{k}{v}" for k, v in sorted_items)

    # 2. 拼接 apiSecret
    full_str = f"{api_secret}{query_str}{api_secret}".lower()

    # 3. 进行 md5
    md5_hash = hashlib.md5(full_str.encode("utf-8")).hexdigest().lower()
    return md5_hash


try:
    APP_TIMEZONE = pytz.timezone("Asia/Shanghai")
    app_now = datetime.now(APP_TIMEZONE)
    app_yesterday = app_now - timedelta(days=1)
    yesterday_str = app_yesterday.strftime("%Y-%m-%d")
    today_str = app_now.strftime("%Y-%m-%d")

    tqt_params = {
        "appKey": appKey,
        "startDate": today_str,
        "endDate": today_str,
        "page": 1,
        "pageSize": 500,
        "type": "country"
    }
    tqt_params['sign'] = generate_sign(tqt_params)
    print(tqt_params)

    response = requests.post(
        url=url,
        headers=Headers,
        json=tqt_params,
        timeout=20
    )

    status_code = response.status_code

    try:
        json_data = response.json()
        print(json_data)
        data = None
        if 'data' in json_data and isinstance(json_data['data'], dict):
            data = json_data['data'].get('list', [])
        else:
            data = json_data.get('list', [])
        print(len(data))
        cp = []
        if data:
            for item in data:
                item_date = item.get('date', '')

                if item.get('url', '') not in cp:
                    cp.append(item.get('url', ''))

                # print('\n⽇期', item.get('date', ''))
                # print('产品', item.get('url', ''))

                # print('国家代码', item.get('country_code', ''))
                # print('国家名称', item.get('country_name', ''))

                # print('请求数', item.get('requests', 0))
                # print('匹配数', item.get('matche_que', 0))
                # print('覆盖率', item.get('coverage', ''))
                # print('展示数', item.get('adimpressions', 0))
                # print('展示率', item.get('display_rate', ''))
                # print('点击数', item.get('clicks', 0))
                # print('点击率', item.get('ctr', ''))

                # print('eCPM', item.get('ecpm', ''))

                # print('收益', item.get('estirevenue', ''))
                # print('网页展示', item.get('page_views', ''))
            print(len(cp), cp)

        else:
            print('  暂无产品数据')
    except json.JSONDecodeError:
        print(f'原始响应: {response.text}')

except requests.exceptions.RequestException as e:
    print(f'\n❌ 请求失败: {str(e)}')
