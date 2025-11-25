"""
对外开放API测试代码
根据API文档编写，支持Token认证和多种API接口的测试

API文档规范：
- 基础URL: https://data.tongbaishijia.com/api/thirdservice
- 认证方式: API Token (Bearer Token)
- 数据格式: JSON
- 字符编码: UTF-8
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


class APITester:
    """API测试类"""

    def __init__(self, base_url: str, username: str = None, password: str = None):
        """
        初始化API测试器
        
        Args:
            base_url: API基础URL
            username: 用户名（用于获取Token）
            password: 密码（用于获取Token）
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.access_token = None
        self.headers = {
            'Content-Type': 'application/json;charset=utf-8'
        }

    def get_token(self, username: str = None, password: str = None) -> Optional[str]:
        """
        获取API访问Token
        
        Args:
            username: 用户名（如果不提供则使用初始化时的用户名）
            password: 密码（如果不提供则使用初始化时的密码）
        
        Returns:
            Access Token字符串，失败返回None
        """
        username = username or self.username
        password = password or self.password

        if not username or not password:
            print("❌ 错误: 需要提供用户名和密码来获取Token")
            return None

        url = f"{self.base_url}/token"
        payload = {
            "username": username,
            "password": password
        }

        print(f"\n{'=' * 60}")
        print("获取Token")
        print(f"URL: {url}")
        print(f"请求体: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        print(f"{'=' * 60}")

        try:
            response = requests.post(
                url=url,
                headers=self.headers,
                json=payload,
                timeout=20
            )

            print(f"状态码: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    self.access_token = data.get('access_token')

                    if self.access_token:
                        # 更新headers，添加Authorization
                        self.headers['Authorization'] = f'Bearer {self.access_token}'
                        print(f"✅ Token获取成功: {self.access_token}")
                        return self.access_token
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

    def send_request(
            self,
            endpoint: str,
            params: Dict[str, Any] = None,
            method: str = 'POST',
            timeout: int = 20,
            require_auth: bool = True
    ) -> requests.Response:
        """
        发送API请求
        
        Args:
            endpoint: API端点路径（如 /data, /adunit）
            params: 请求参数
            method: 请求方法（GET/POST）
            timeout: 超时时间（秒）
            require_auth: 是否需要认证（默认True）
        
        Returns:
            Response对象
        """
        if params is None:
            params = {}

        url = f"{self.base_url}{endpoint}"

        # 检查是否需要认证
        if require_auth and not self.access_token:
            print("⚠️  警告: 未设置Token，尝试自动获取...")
            if not self.get_token():
                raise Exception("无法获取Token，请求终止")

        try:
            if method.upper() == 'GET':
                response = requests.get(
                    url=url,
                    headers=self.headers,
                    params=params,
                    timeout=timeout
                )
            else:
                response = requests.post(
                    url=url,
                    headers=self.headers,
                    json=params,
                    timeout=timeout
                )

            return response

        except requests.exceptions.RequestException as e:
            print(f'❌ 请求失败: {str(e)}')
            raise

    def parse_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        解析API响应
        
        Args:
            response: Response对象
        
        Returns:
            解析后的数据字典
        """
        result = {
            'status_code': response.status_code,
            'success': False,
            'code': None,
            'data': None,
            'error': None,
            'message': '',
            'raw_response': None
        }

        try:
            json_data = response.json()
            result['raw_response'] = json_data

            # 检查错误响应格式
            if 'error' in json_data:
                error_info = json_data['error']
                result['error'] = error_info
                result['message'] = error_info.get('message', '请求失败')
                result['code'] = error_info.get('code', 'UNKNOWN_ERROR')
                return result

            # 检查成功响应格式
            if 'code' in json_data:
                result['code'] = json_data.get('code')
                # code为20000表示成功
                if result['code'] == 20000:
                    result['success'] = True
                    result['data'] = json_data.get('data')
                    result['message'] = '请求成功'
                else:
                    result['message'] = f"请求失败，错误码: {result['code']}"

            # 兼容其他响应格式
            elif response.status_code in [200, 201, 204]:
                result['success'] = True
                result['data'] = json_data.get('data', json_data)
                result['message'] = '请求成功'
            else:
                result['message'] = json_data.get('message', '请求失败')

        except json.JSONDecodeError:
            result['message'] = '响应不是有效的JSON格式'
            result['raw_response'] = response.text[:500]

        return result

    def test_api(
            self,
            endpoint: str,
            params: Dict[str, Any] = None,
            method: str = 'POST',
            print_result: bool = True,
            require_auth: bool = True
    ) -> Dict[str, Any]:
        """
        测试API接口
        
        Args:
            endpoint: API端点
            params: 请求参数
            method: 请求方法
            print_result: 是否打印结果
            require_auth: 是否需要认证
        
        Returns:
            测试结果字典
        """
        if params is None:
            params = {}

        print(f"\n{'=' * 60}")
        print(f"测试接口: {endpoint}")
        print(f"请求方法: {method}")
        print(f"请求参数: {json.dumps(params, indent=2, ensure_ascii=False)}")
        print(f"{'=' * 60}")

        try:
            response = self.send_request(endpoint, params, method, require_auth=require_auth)
            result = self.parse_response(response)

            if print_result:
                print(f"状态码: {result['status_code']}")
                print(f"响应码: {result.get('code', 'N/A')}")
                print(f"成功: {result['success']}")
                print(f"消息: {result['message']}")

                if result.get('error'):
                    print(f"\n错误信息:")
                    print(json.dumps(result['error'], indent=2, ensure_ascii=False))

                if result['success'] and result['data']:
                    print(f"\n响应数据:")
                    print(json.dumps(result['data'], indent=2, ensure_ascii=False))
                elif result['raw_response']:
                    print(f"\n原始响应:")
                    if isinstance(result['raw_response'], dict):
                        print(json.dumps(result['raw_response'], indent=2, ensure_ascii=False))
                    else:
                        print(result['raw_response'])

            return result

        except Exception as e:
            print(f"❌ 测试失败: {str(e)}")
            return {'success': False, 'error': str(e)}


def main():
    """主测试函数 - 根据API文档填写具体测试用例"""

    # ========== 配置信息（根据实际情况填写）==========
    BASE_URL = 'https://data.tongbaishijia.com/api/thirdservice'
    USERNAME = 'BOFIT'  # 替换为实际用户名
    PASSWORD = '5e2296fa9fd1434bf8a60c03cf745ce9'  # 替换为实际密码

    # 初始化测试器
    tester = APITester(BASE_URL, USERNAME, PASSWORD)

    # ========== 测试用例1: 获取Token ==========
    print("\n" + "=" * 60)
    print("【测试用例1: 获取Token】")
    print("=" * 60)

    token = tester.get_token()
    if not token:
        print("❌ Token获取失败，后续测试无法进行")
        return

    # ========== 测试用例2: 获取链接数据报表 ==========
    print("\n" + "=" * 60)
    print("【测试用例2: 获取链接数据报表 (POST /data)】")
    print("=" * 60)

    # 计算日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3)

    params_data = {
        "product": "url",  # 产品URL
        "page": 1,
        "limit": 500,
        "start": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d")
    }

    result_data = tester.test_api('/data', params_data, method='POST')

    # 处理返回数据
    if result_data.get('success') and result_data.get('data'):
        data = result_data['data']
        total = data.get('total', 0)
        items = data.get('items', [])

        print(f"\n✅ 查询成功，共 {total} 条数据")

        if items:
            print(f"\n前5条数据详情:")
            for i, item in enumerate(items[:5], 1):
                print(f"\n数据 {i}:")
                print(f"  日期: {item.get('date', 'N/A')}")
                print(f"  产品: {item.get('product', 'N/A')}")
                print(f"  广告请求数: {item.get('ad_requests', 0)}")
                print(f"  广告匹配数: {item.get('ad_matches', 0)}")
                print(f"  覆盖率: {item.get('ad_coverage', 0)}%")
                print(f"  广告展示数: {item.get('ad_impressions', 0)}")
                print(f"  展示率: {item.get('ad_impression_rate', 0)}%")
                print(f"  广告点击数: {item.get('ad_clicks', 0)}")
                print(f"  点击率(CTR): {item.get('ctr', 0)}%")
                print(f"  eCPM: {item.get('ecpm', 0)}")
                print(f"  收益: {item.get('earnings', 0)}")

    # ========== 测试用例3: 获取国家以及单元位置数据报表 ==========
    print("\n" + "=" * 60)
    print("【测试用例3: 获取国家以及单元位置数据报表 (GET /adunit)】")
    print("=" * 60)

    params_adunit = {
        "product": "url",  # 产品URL
        "countryCode": "",  # 国家代码（可选）
        "adunit": "",  # 广告单元位置（可选，空字符串表示全部）
        "page": 1,
        "limit": 500,
        "start": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d")
    }

    result_adunit = tester.test_api('/adunit', params_adunit, method='GET')

    # 处理返回数据
    if result_adunit.get('success') and result_adunit.get('data'):
        data = result_adunit['data']
        total = data.get('total', 0)
        items = data.get('items', [])

        print(f"\n✅ 查询成功，共 {total} 条数据")

        if items:
            print(f"\n前5条数据详情:")
            for i, item in enumerate(items[:5], 1):
                print(f"\n数据 {i}:")
                print(f"  日期: {item.get('date', 'N/A')}")
                print(f"  产品: {item.get('product', 'N/A')}")
                print(f"  国家代码: {item.get('country_code', 'N/A')}")
                print(f"  广告单元: {item.get('ad_unit', 'N/A')}")
                print(f"  广告请求数: {item.get('ad_requests', 0)}")
                print(f"  广告匹配数: {item.get('ad_matches', 0)}")
                print(f"  覆盖率: {item.get('ad_coverage', 0)}%")
                print(f"  广告展示数: {item.get('ad_impressions', 0)}")
                print(f"  展示率: {item.get('ad_impression_rate', 0)}%")
                print(f"  广告点击数: {item.get('ad_clicks', 0)}")
                print(f"  点击率(CTR): {item.get('ctr', 0)}%")
                print(f"  eCPM: {item.get('ecpm', 0)}")
                print(f"  收益: {item.get('earnings', 0)}")

    # ========== 测试用例4: 错误处理测试 ==========
    print("\n" + "=" * 60)
    print("【测试用例4: 错误参数测试】")
    print("=" * 60)

    error_params = {
        "product": "url",
        "page": 1,
        "limit": 50,
        "start": "invalid-date",  # 无效日期
        "end": end_date.strftime("%Y-%m-%d")
    }

    result_error = tester.test_api('/data', error_params, method='POST')

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
