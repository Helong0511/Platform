import requests

# 测试 lp6
pixel_id = "878030098624377"
token = "EAAXW0mecENUBRH0Gy6RgpASivlDaQzk44YXK2lb2LigiE7ZAUmNo7m3ogsAsZCn8LL1xCKnFJ1uulvKAduXKv8YO9K0C5tg6cUiCXXEIpVqwLnsD66GObgzrZClgYSbwB1ewJXqyQzSuJxvktAHjZBKA4a2VCsoqigTA3tLFtHau1Nk8Htuiro6FRCkKqPAZAMQZDZD" # 建议尝试从 lp6 后台重新生成一个新 Token 试试

url = f"https://graph.facebook.com/v19.0/{pixel_id}"
response = requests.get(url, params={"access_token": token})

print(f"查询结果: {response.json()}")