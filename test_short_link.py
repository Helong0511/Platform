import requests
import json
import traceback

# 固定的User-Agent，确保会话ID一致
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 获取CSRF令牌
def get_csrf_token(cookies, token):
    url = 'https://client.btfrx.online/api/v1/dashboard/stats'
    headers = {
        'Authorization': f'Bearer {token}',
        'User-Agent': USER_AGENT
    }
    try:
        response = requests.get(url, headers=headers, cookies=cookies)
        print('CSRF token status code:', response.status_code)
        print('CSRF token headers:', dict(response.headers))
        # 从响应头或响应体中提取CSRF令牌
        # 通常CSRF令牌会在响应头的X-CSRF-Token字段中
        csrf_token = response.headers.get('X-CSRF-Token')
        return csrf_token
    except Exception as e:
        print('Get CSRF token error:', str(e))
        return None

# 测试短链接创建API
def test_create_short_link(token, cookies, csrf_token):
    url = 'https://client.btfrx.online/api/v1/short-links/'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'User-Agent': USER_AGENT
    }
    # 添加CSRF令牌到请求头
    if csrf_token:
        headers['X-CSRF-Token'] = csrf_token
    data = {
        'original_url': 'https://example.com',
        'title': '测试短链接'
    }
    
    try:
        print('\n=== POST Request Headers ===')
        for key, value in headers.items():
            print(f'{key}: {value}')
        print('=== POST Request Data ===')
        print(json.dumps(data, indent=2))
        
        response = requests.post(url, headers=headers, cookies=cookies, json=data)
        print('\n=== POST Response ===')
        print('Status code:', response.status_code)
        print('Response:', response.text)
        print('Headers:', dict(response.headers))
        print('Cookies sent:', dict(cookies))
        print('Cookies received:', dict(response.cookies))
        
        # 尝试解析响应为JSON，获取更详细的错误信息
        try:
            response_json = response.json()
            if 'detail' in response_json:
                print('Error detail:', response_json['detail'])
            if 'message' in response_json:
                print('Error message:', response_json['message'])
        except json.JSONDecodeError:
            pass
    except Exception as e:
        print('Error:', str(e))
        import traceback
        traceback.print_exc()

# 测试登录API
def test_login():
    url = 'https://client.btfrx.online/api/v1/auth/login'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': USER_AGENT
    }
    data = {
        'username': 'admin',
        'password': 'yinghexinxi123'
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        print('Login status code:', response.status_code)
        print('Login response:', response.text)
        print('Login headers:', dict(response.headers))
        # 提取 access_token
        response_data = response.json()
        token = response_data.get('access_token')
        return token, response.cookies
    except Exception as e:
        print('Login error:', str(e))
        return None, None

if __name__ == '__main__':
    print('Testing login...')
    token, cookies = test_login()
    if token:
        print('Getting CSRF token...')
        csrf_token = get_csrf_token(cookies, token)
        print('Testing create short link...')
        test_create_short_link(token, cookies, csrf_token)
    else:
        print('Login failed, cannot test create short link')


