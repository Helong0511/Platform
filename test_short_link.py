import requests
import json

# 测试短链接创建API
def test_create_short_link():
    url = 'http://localhost:8000/api/v1/short-links/'
    headers = {'Content-Type': 'application/json'}
    data = {
        'original_url': 'https://example.com',
        'title': '测试短链接'
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print('Status code:', response.status_code)
        print('Response:', response.text)
    except Exception as e:
        print('Error:', str(e))

if __name__ == '__main__':
    test_create_short_link()
