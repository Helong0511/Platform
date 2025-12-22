import requests
import json
from datetime import datetime

URL = 'https://client.btfrx.online/api/v1/macan/postback'

post_data = {
    "clk_id":1,
    "devad_id":1,
    "event_name":1,
    "event_value":1,
    "clkcarrier_id":1,
    "os":1,
    "payout":1,
    "ip":"127.0.0.1"
}




try:
    response = requests.get(URL, params=post_data, timeout=10)
except Exception as e:
    print(e)


