import uuid
import platform
import requests
import json
from datetime import datetime

URL = 'https://client.btfrx.online/api/v1/macan/postback'

uuid.uuid4()

post_data = {
    "clk_id":uuid.uuid4(),
    "os":platform.system(),
    "payout":10.00,
    "ip":"127.0.0.1"
}

try:
    response = requests.get(URL, params=post_data, timeout=10)
except Exception as e:
    print(e)


