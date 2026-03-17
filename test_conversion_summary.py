import requests

# 直接测试转化总览API（使用正确的路径）
summary_url = "http://localhost:8000/api/v1/conversion-summary/"

# 由于认证问题，我们先尝试不带认证的请求
try:
    response = requests.get(summary_url)
    print("转化总览API响应:")
    print(response.status_code)
    print(response.json())
except Exception as e:
    print(f"请求失败: {e}")
