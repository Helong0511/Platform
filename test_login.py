import requests

# 登录请求（使用application/x-www-form-urlencoded格式）
url = "http://localhost:8000/api/v1/auth/login"
data = {
    "username": "admin",
    "password": "My@SecurePssw0rd2025!"
}

response = requests.post(url, data=data)
print("登录响应:")
print(response.status_code)
print(response.json())

# 如果登录成功，获取访问令牌
if response.status_code == 200:
    access_token = response.json().get("access_token")
    if access_token:
        print(f"\n获取到访问令牌: {access_token}")
        
        # 使用令牌测试转化总览API
        summary_url = "http://localhost:8000/api/v1/conversion-summary/"
        summary_headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        summary_response = requests.get(summary_url, headers=summary_headers)
        print("\n转化总览API响应:")
        print(summary_response.status_code)
        print(summary_response.json())
