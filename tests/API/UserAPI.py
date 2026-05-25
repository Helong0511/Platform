import requests

url = 'https://data.tongbaishijia.com/api/thirdservice'

Headers = {'Content-Type': 'application/json;charset=utf-8'}

username = 'BOFIT1'
password = 'f8034e342a8e6070aadaee559c3c95eb'

token_post = {
    "username": username,
    "password": password
}

response = requests.post(url + '/token', data=token_post)
json_data = response.json()
access_token = json_data.get('access_token', '')

Headers['Authorization'] = f'Bearer {access_token}'

tbsj_params = {
    "page": 1,
    "limit": 1000,
    "start": '2025-11-24 00:00:00',
    "end": '2025-11-24 23:59:59'
}

response = requests.post(url + '/adunit',headers=Headers, json=tbsj_params)
print(response.json())

response = requests.post(url + '/unit_data',headers=Headers, json=tbsj_params)
print(response.json())

response = requests.post(url + '/country',headers=Headers, json=tbsj_params)
print(response.json())