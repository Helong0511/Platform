import requests
import urllib3

# 禁用SSL验证（仅用于测试）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 登录信息
login_url = "http://localhost:8960/api/v1/auth/login"
username = "admin"
password = "yinghexinxi123"

# 转化总览API
conversion_url = "http://localhost:8960/api/v1/conversion-summary/"

# 会话对象，用于保持认证状态
session = requests.Session()
session.verify = False

try:
    # 登录
    print("正在登录...")
    login_data = {
        "username": username,
        "password": password,
        "grant_type": "password"
    }
    login_response = session.post(login_url, data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    print(f"登录响应状态码: {login_response.status_code}")
    print(f"登录响应: {login_response.json()}")
    
    # 检查登录是否成功
    if login_response.status_code == 200:
        # 访问转化总览API
        print("\n访问转化总览API...")
        conversion_response = session.get(conversion_url)
        print(f"转化总览API响应状态码: {conversion_response.status_code}")
        print(f"转化总览API响应: {conversion_response.json()}")
    else:
        print("登录失败，无法访问转化总览API")
        
except Exception as e:
    print(f"请求失败: {e}")