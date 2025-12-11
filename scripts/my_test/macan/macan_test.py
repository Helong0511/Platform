"""
Macan S2S PostBack 接口测试脚本
用于测试 Macan PostBack 回调接口是否正常工作
"""
import requests
import json
from datetime import datetime

# 配置
BASE_URL = "https://client.btfrx.online"  # 修改为您的服务器地址
API_ENDPOINT = f"{BASE_URL}/api/v1/macan/postback"

def test_get_postback():
    """测试 GET 请求"""
    print("=" * 50)
    print("测试 GET 请求")
    print("=" * 50)
    
    params = {
        "clk_id": "test_clk_12345",
        "event_name": "purchase",
        "devad_id": "test_devad_id_abc123",
        "event_value": 99.99,
        "payout": 10.5,
        "carrier": "China Mobile",
        "os": "IOS",
        "ip": "192.168.1.1",
        "gid": "test_channel_001",
        "product_id": 1,  # 可选
        "client_id": 1,  # 可选
    }
    
    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("✅ GET 请求测试成功")
        else:
            print(f"❌ GET 请求测试失败，状态码: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {str(e)}")
    
    print()


def test_post_postback():
    """测试 POST 请求"""
    print("=" * 50)
    print("测试 POST 请求")
    print("=" * 50)

    data = {
        "clk_id": "test_clk_67890",
        "event_name": "install",
        "devad_id": "test_devad_id_xyz789",
        "event_value": 49.99,
        "payout": 5.0,
        "carrier": "China Unicom",
        "os": "Android",
        "ip": "192.168.1.2",
        "gid": "test_channel_002",
        "product_id": 1,  # 可选
        "client_id": 1,  # 可选
    }

    try:
        response = requests.post(
            API_ENDPOINT,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("✅ POST 请求测试成功")
        else:
            print(f"❌ POST 请求测试失败，状态码: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {str(e)}")

    print()


def test_minimal_params():
    """测试最小参数（仅必填参数）"""
    print("=" * 50)
    print("测试最小参数（仅必填参数）")
    print("=" * 50)

    params = {
        "clk_id": "minimal_test_123",
        "event_name": "test_event",
    }

    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

        if response.status_code == 200:
            print("✅ 最小参数测试成功")
        else:
            print(f"❌ 最小参数测试失败，状态码: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {str(e)}")

    print()


def test_missing_required_params():
    """测试缺少必填参数"""
    print("=" * 50)
    print("测试缺少必填参数（应该返回错误）")
    print("=" * 50)

    # 缺少 event_name
    params = {
        "clk_id": "test_clk_12345",
    }
    
    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code != 200:
            print("✅ 正确返回错误（缺少必填参数）")
        else:
            print("❌ 应该返回错误但没有返回")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {str(e)}")
    
    print()


if __name__ == "__main__":
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试接口: {API_ENDPOINT}")
    print()
    
    # 运行所有测试
    test_get_postback()
    test_post_postback()
    test_minimal_params()
    test_missing_required_params()
    
    print("=" * 50)
    print("所有测试完成")
    print("=" * 50)

