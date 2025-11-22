"""
客户API测试程序
用于测试客户API查询产品和广告数据的功能

API端点：
- /api/v1/client_products - 查询所有产品名称
- /api/v1/client_data - 查询广告数据

认证方式：
- client_id: 客户ID
- req_time: 请求时间戳（10位秒级）
- sign: MD5签名

签名算法：
1. 按字母排序参数：client_id, req_time, secret_key
2. 拼接：client_id=1000&req_time=1745656222&secret_key=f21b6638-b732-4f69-9d6a-049e3207c5b3
3. MD5加密
"""
import requests
import json
import hashlib
import time
from datetime import datetime


class ClientAPITester:
    """客户API测试类"""

    def __init__(self, base_url: str, client_id: int, secret_key: str):
        """
        初始化测试器

        Args:
            base_url: API服务器基础URL，例如 https://admin.king-sms.com
            client_id: 客户ID
            secret_key: 客户的密钥（从数据库Client表的key字段获取）
        """
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.secret_key = secret_key
        self.products_url = f"{self.base_url}/api/v1/client_products"
        self.data_url = f"{self.base_url}/api/v1/client_data"

    def generate_signature(self, client_id: int, req_time: int, secret_key: str) -> str:
        """
        生成MD5签名

        Args:
            client_id: 客户ID
            req_time: 请求时间戳
            secret_key: 密钥

        Returns:
            MD5签名字符串（小写）
        """
        # 按字母排序参数
        params = {
            'client_id': str(client_id),
            'req_time': str(req_time)
        }

        # 按key排序并拼接
        sorted_keys = sorted(params.keys())
        temp_str = '&'.join([f"{key}={params[key]}" for key in sorted_keys])
        temp_str = temp_str + '&key='+ secret_key

        # MD5加密
        sign = hashlib.md5(temp_str.encode('utf-8')).hexdigest()

        return sign.lower()

    def create_request_data(self) -> dict:
        """
        创建请求数据（包含签名）

        Returns:
            包含 client_id, req_time, sign 的字典
        """
        # 获取当前时间戳（10位秒级）
        req_time = int(time.time())

        # 生成签名
        sign = self.generate_signature(self.client_id, req_time, self.secret_key)

        return {
            "client_id": self.client_id,
            "req_time": req_time,
            "sign": sign
        }

    def test_get_products(self) -> dict:
        """
        测试查询产品列表

        Returns:
            测试结果字典
        """
        print('=' * 60)
        print('测试查询产品列表')
        print('=' * 60)

        # 创建请求数据
        request_data = self.create_request_data()

        print(f'请求URL: {self.products_url}')
        print(f'请求数据: {json.dumps(request_data, indent=2, ensure_ascii=False)}')
        print('-' * 60)

        try:
            # 发送POST请求
            response = requests.post(
                self.products_url,
                json=request_data,  # 使用JSON格式发送
                timeout=10
            )

            status_code = response.status_code
            print(f'响应状态码: {status_code}')
            print(f'响应头 Content-Type: {response.headers.get("Content-Type", "N/A")}')

            try:
                response_data = response.json()
                print(f'响应内容: {json.dumps(response_data, indent=2, ensure_ascii=False)}')

                if status_code == 200:
                    if response_data.get("code") == 200 or response_data.get("success"):
                        data = response_data.get("data", [])
                        print(f'\n✅ 查询成功！')
                        print(f'产品数量: {len(data)}')
                        if data:
                            print('\n产品列表:')
                            for i, product in enumerate(data, 1):
                                print(f'  {i}. ID: {product.get("id")}, 名称: {product.get("name")}')
                        else:
                            print('  暂无产品数据')
                        return {
                            "success": True,
                            "status_code": status_code,
                            "data": data,
                            "count": len(data)
                        }
                    else:
                        print(f'\n❌ 查询失败: {response_data.get("message", "未知错误")}')
                        return {
                            "success": False,
                            "status_code": status_code,
                            "error": response_data.get("message", "未知错误")
                        }
                else:
                    print(f'\n❌ 请求失败，状态码: {status_code}')
                    error_msg = response_data.get("detail") or response_data.get("message", "未知错误")
                    print(f'错误信息: {error_msg}')
                    return {
                        "success": False,
                        "status_code": status_code,
                        "error": error_msg
                    }
            except json.JSONDecodeError:
                print(f'\n❌ 响应不是有效的JSON格式')
                print(f'原始响应: {response.text[:500]}')
                return {
                    "success": False,
                    "status_code": status_code,
                    "error": "响应不是有效的JSON格式",
                    "raw_response": response.text
                }

        except requests.exceptions.RequestException as e:
            print(f'\n❌ 请求失败: {str(e)}')
            return {
                "success": False,
                "error": str(e)
            }

    def test_get_ad_data(self) -> dict:
        """
        测试查询广告数据

        Returns:
            测试结果字典
        """
        print('\n' + '=' * 60)
        print('测试查询广告数据')
        print('=' * 60)

        # 创建请求数据
        request_data = self.create_request_data()

        print(f'请求URL: {self.data_url}')
        print(f'请求数据: {json.dumps(request_data, indent=2, ensure_ascii=False)}')
        print('-' * 60)

        try:
            # 发送POST请求
            response = requests.post(
                self.data_url,
                json=request_data,  # 使用JSON格式发送
                timeout=10
            )

            status_code = response.status_code
            print(f'响应状态码: {status_code}')
            print(f'响应头 Content-Type: {response.headers.get("Content-Type", "N/A")}')

            try:
                response_data = response.json()
                print(response_data)
                # 如果数据太多，只显示前几条
                if isinstance(response_data.get("data"), list) and len(response_data.get("data", [])) > 5:
                    preview_data = response_data.copy()
                    preview_data["data"] = preview_data["data"][:3]
                    preview_data["_preview"] = True
                    preview_data["_total_count"] = len(response_data["data"])
                    print(f'响应内容（预览前3条）: {json.dumps(preview_data, indent=2, ensure_ascii=False)}')
                    print(f'\n... 共 {len(response_data["data"])} 条数据，仅显示前3条')
                else:
                    print(f'响应内容: {json.dumps(response_data, indent=2, ensure_ascii=False)}')

                if status_code == 200:
                    if response_data.get("code") == 200 or response_data.get("success"):
                        data = response_data.get("data", [])
                        print(f'\n✅ 查询成功！')
                        print(f'广告数据条数: {len(data)}')
                        if data:
                            print('\n广告数据示例（前5条）:')
                            for i, item in enumerate(data[:5], 1):
                                print(f'\n  {i}. 日期: {item.get("date")}')
                                print(f'     产品: {item.get("product_name")}')
                                print(f'     请求数: {item.get("request_count")}')
                                print(f'     匹配数: {item.get("match_count")}')
                                print(f'     覆盖率: {item.get("coverage_rate")}%')
                                print(f'     展示数: {item.get("display_count")}')
                                print(f'     展示率: {item.get("display_rate")}%')
                                print(f'     点击数: {item.get("click_count")}')
                                print(f'     点击率: {item.get("click_rate")}%')
                                print(f'     eCPM: {item.get("ecpm_after_deduct")}')
                                print(f'     收益: {item.get("revenue_after_deduct")}')
                        else:
                            print('  暂无广告数据')
                        return {
                            "success": True,
                            "status_code": status_code,
                            "data": data,
                            "count": len(data)
                        }
                    else:
                        print(f'\n❌ 查询失败: {response_data.get("message", "未知错误")}')
                        return {
                            "success": False,
                            "status_code": status_code,
                            "error": response_data.get("message", "未知错误")
                        }
                else:
                    print(f'\n❌ 请求失败，状态码: {status_code}')
                    error_msg = response_data.get("detail") or response_data.get("message", "未知错误")
                    print(f'错误信息: {error_msg}')
                    return {
                        "success": False,
                        "status_code": status_code,
                        "error": error_msg
                    }
            except json.JSONDecodeError:
                print(f'\n❌ 响应不是有效的JSON格式')
                print(f'原始响应: {response.text[:500]}')
                return {
                    "success": False,
                    "status_code": status_code,
                    "error": "响应不是有效的JSON格式",
                    "raw_response": response.text
                }

        except requests.exceptions.RequestException as e:
            print(f'\n❌ 请求失败: {str(e)}')
            return {
                "success": False,
                "error": str(e)
            }

    def test_all(self):
        """运行所有测试"""
        print('=' * 60)
        print('客户API测试程序')
        print('=' * 60)
        print(f'服务器地址: {self.base_url}')
        print(f'客户ID: {self.client_id}')
        print(f'密钥: {self.secret_key[:20]}...{self.secret_key[-10:]}')
        print('=' * 60)

        # 测试查询产品
        products_result = self.test_get_products()

        # 测试查询广告数据
        ad_data_result = self.test_get_ad_data()

        # 总结
        print('\n' + '=' * 60)
        print('测试总结')
        print('=' * 60)
        print(f'查询产品: {"✅ 成功" if products_result.get("success") else "❌ 失败"}')
        if products_result.get("success"):
            print(f'  - 产品数量: {products_result.get("count", 0)}')
        else:
            print(f'  - 错误: {products_result.get("error", "未知错误")}')

        print(f'查询广告数据: {"✅ 成功" if ad_data_result.get("success") else "❌ 失败"}')
        if ad_data_result.get("success"):
            print(f'  - 数据条数: {ad_data_result.get("count", 0)}')
        else:
            print(f'  - 错误: {ad_data_result.get("error", "未知错误")}')

        return {
            "products": products_result,
            "ad_data": ad_data_result
        }


def main():
    base_url = 'https://client.king-sms.com'

    client_id = 1001

    secret_key = '7a2480f0-fa9e-487b-b21a-83cbb9bd6a5b'

    # 创建测试器并运行测试
    tester = ClientAPITester(base_url, client_id, secret_key)
    tester.test_all()


if __name__ == "__main__":
    main()

