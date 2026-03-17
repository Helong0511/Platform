import requests

# 直接测试转化总览API（使用正确的路径）
summary_url = "http://localhost:8960/api/v1/conversion-summary/"

# 禁用SSL验证（仅用于测试）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 由于认证问题，我们先尝试不带认证的请求
try:
    # 明确使用HTTP，禁用SSL验证
    response = requests.get(summary_url, verify=False, allow_redirects=False)
    print("转化总览API响应:")
    print(response.status_code)
    print(response.json())
except Exception as e:
    print(f"请求失败: {e}")
