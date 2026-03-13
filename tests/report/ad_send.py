import time
import uuid
import httpx
import json
from typing import Dict, Any


# ============================================
# 问题分析总结
# ============================================
# 原 ad_send.py 的问题：
# 1. 设置了 token 请求头，但 API 不需要（unique_channel.py 成功是因为没带 token）
# 2. 响应是纯文本 "OK"，不是 JSON，但代码尝试用 .json() 解析
# 3. post_data 包含嵌套字典 userData，直接作为 form-data 发送需要特殊处理
# 4. 没有正确处理数据格式转换

# API 基础 URL
url = "https://linkes.com/UniqueChannelServer/UniqueChannelSync"

# Facebook 相关配置（暂时未使用）
API_VERSION = "v25.0"
PIXEL_ID = "2105276563598069"
TOKEN = "EAAUIMcFRZAnsBQ3UZAS7ZBLrcf0EsRhrpluOZBEVZA52TweqrD8ZA6fNMUByWCfMwyR86w6tq5uZBGE2K6C72GPCZCCP7Cx4oPZAaFo3NMZBcqTj9iGatWfNQjZBRClwoiJrX5Kv6ZBKSPCrmkNY1bGuUY6A5SlxLUWBq6mHNxCCCoLbLecNDZCj2YBmpr829jSKxuon5fwZDZD"


def send_ad_event():
    """
    发送广告事件到 UniqueChannelSync API（修复版本）
    参考 unique_channel.py 的成功实现
    """
    # 构建广告发送的测试数据
    post_data = {
        "adsid": uuid.uuid4().hex,
        "event": "viewWebpage",
        "pixid": "2105276563598069",
        "testServe": "true",
        "type": "Facebook",
        "unixtime": int(time.time()),
        "userData": {
            "email": "123456789@gmail.com",
            "ip": "0.0.0.0",
            "phone": 123456789,
            "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/22G100 Instagram 395.1.0.30.151 (iPhone11,8; iOS 18_6_2; pt_BR; pt; scale=2.00; 828x1792; IABMV/1; 784107667)"
        }
    }
    
    # 将复杂的嵌套字典转换为 form-data 兼容格式
    # 注意：form-data 不支持嵌套字典，需要序列化为 JSON 字符串
    form_data = {}
    for key, value in post_data.items():
        if isinstance(value, dict):
            # 嵌套字典需要序列化为 JSON 字符串
            form_data[key] = json.dumps(value, ensure_ascii=False)
        else:
            form_data[key] = str(value)
    
    print("=" * 60)
    print("发送广告事件请求")
    print("=" * 60)
    print(f"请求 URL: {url}")
    print(f"请求数据:")
    for key, value in form_data.items():
        print(f"  {key}: {value}")
    
    # 创建 HTTP 客户端
    client = httpx.Client(timeout=30.0)
    
    try:
        # 发送 form-data 格式的 POST 请求（不设置 token 头，参考 unique_channel.py）
        response = client.post(url, data=form_data)
        
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200 and response.text.strip() == "OK":
            print("\n✓ 请求成功！")
            return True
        else:
            print("\n✗ 请求失败！")
            return False
            
    except Exception as e:
        print(f"\n✗ 请求异常: {str(e)}")
        return False
    finally:
        client.close()


def main():
    """主函数"""
    print("=" * 60)
    print("广告事件发送测试程序（修复版本）")
    print("=" * 60)
    
    success = send_ad_event()
    
    print("\n" + "=" * 60)
    if success:
        print("测试完成 - 成功")
    else:
        print("测试完成 - 失败")
    print("=" * 60)


if __name__ == "__main__":
    main()
