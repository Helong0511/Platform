import platform
import uuid
import requests

URL = 'https://client.btfrx.online/api/v1/bft/postback'

# 生成一个唯一的 click_id（需要转换为字符串）
click_id = str(uuid.uuid4())

# ============================================================================
# BFT postback 接口支持的参数说明
# ============================================================================
# 注意：虽然 channel_id, offer_id, publisher_id, advertiser_id, click_time 等是 CPL 系统内部字段
# 通常应该通过 click_id 在系统中查找，但接口也支持直接传递这些参数
# ============================================================================

post_data = {
    # ========== 必填参数 ==========
    # 以下参数名都可以使用（按优先级）：click_id, clk_id, cid, clickid, clickId, ClickId, conversion_id, conversionId
    "click_id": click_id,  # 【必填】转化ID（必须是系统中存在的 click_id）
    # 或者使用其他别名：
    # "clk_id": click_id,  # 【必填】BFT click ID（与 click_id 等效）
    # "cid": click_id,  # 【必填】Click ID 简写（与 click_id 等效）
    
    # ========== 可选参数 ==========
    # 事件相关
    "event_name": "purchase",  # 【可选】事件名称（也支持 event_id, eventId, event, eventName, EventName）
    "event_value": 99.99,  # 【可选】事件价值（浮点数）
    "payout": 10.00,  # 【可选】支付金额（浮点数）
    
    # 设备信息
    "os": platform.system(),  # 【可选】操作系统（如：Windows, Linux, Darwin）
    "devad_id": "12345678-1234-1234-1234-123456789012",  # 【可选】设备广告ID（字符串）
    "carrier": "China Mobile",  # 【可选】运营商（字符串）
    
    # 网络信息
    "ip": "127.0.0.1",  # 【可选】IP地址（如果不提供会自动获取）
    
    # 业务信息
    "offer_id": 4,  # 【可选】Offer ID（整数或字符串）
    "channel_id": 3,  # 【可选】渠道ID（字符串，也支持 publisher_id）
    "gid": 3,  # 【可选】渠道ID（字符串）
    "product_id": 1,  # 【可选】产品ID（整数）
    "client_id": 1,  # 【可选】客户ID（整数）
}

print(f"发送请求到: {URL}")
print(f"参数: {post_data}")
print("-" * 50)

try:
    # 使用 GET 请求
    response = requests.get(URL, params=post_data, timeout=10)
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.text}")
        
except requests.exceptions.RequestException as e:
    print(f"请求错误: {e}")
except Exception as e:
    print(f"其他错误: {e}")
    import traceback
    traceback.print_exc()

