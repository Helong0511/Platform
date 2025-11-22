import requests
import json

url = 'https://admin.king-sms.com/api/v1/auth/login'

credentials = {
    'username': 'admin',
    'password': 'admin123'
}

# ✅ 正确：使用 data 参数，不要设置 Content-Type
# requests 会自动设置为 application/x-www-form-urlencoded
response = requests.post(url, data=credentials)

print(f'登录响应状态码: {response.status_code}')
print(f'登录响应内容: {response.text}')

if response.status_code == 200:
    response_data = response.json()
    if 'access_token' in response_data:
        print('✅ 登录成功！')
        access_token = response_data['access_token']
        print(f'获取到的访问令牌: {access_token}')
    else:
        print('❌ 登录响应中未找到访问令牌')
else:
    print(f'❌ 登录失败，状态码: {response.status_code}')


































