import requests

need = [
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br7pyFwHYA4ga9w7acyeCdmyDzXbfe9mGMkwGNXEwz&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br7NyKYdz74g49w7zcHzC9Grd3prznHCexza3rwdb3&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br9XBKmepg9kjWD9PNbFergzndJxzznHCJwwpCkfX&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=br9XJdnwPB9kjWDb9DnGaJCK7dh3Rat3994wYBcWH&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=branwyDnF39zeaYRtztTJywyJyWeDKdkFApNeTNYmt&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbdEkaDHDwwaj4eB7MMtpPNXwWkXYxKdyp9xFYY&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbjGA9JgkwwajhNPtTWeFj4DRR39bPtyMjmbYkr&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkdKYEFxwnajhcK77hfyGNwnR4FW4wAxTRPXwJ&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbktYyXFnwnajhDDWTrWxz9dWKGrBcngeK79ryk&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkwmkEHdwnajhFd7bn4ytKttH3wmxDt3MDG4rN&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkAHKfg3wwajtpzzzwPMCraPYaJj7gR94z7w3z&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbkPTEH4dwtajdMzCNTTX9Y4B9HKBCEFnGa9GEz&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbm9yBENtwwajzpGyNCMgfA3BBC7NyWweWt3Et3&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbmbfwBGXwwajzRYhjXwGme3dyCeKaYw7WfdKJb&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbmngMFGXwnajkmEBkJTj3Ftc3fPaEmamwftazJ&payout=3.00",
    "https://client.btfrx.online/api/v1/bft/postback?click_id=brbmwpeppKwnajkDddkrEdkWGEmpHDAmFHngbtz3&payout=3.00",
]

for get_url in need:
    response = requests.get(get_url)
    print(response.json())
