import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv('DHAN_CLIENT_ID')
access_token = os.getenv('DHAN_ACCESS_TOKEN')

headers = {
    'access-token': access_token,
    'client-id': client_id,
    'Content-type': 'application/json',
    'Accept': 'application/json'
}

# Try different base URLs
bases = [
    "https://api.dhan.co/v2",
    "https://api.dhan.co",
    "https://dhan.co/api/v2",
    "https://dhan.co/api",
]

endpoints = ["/fund-limit", "/funds", "/market-quote/ltp", "/marketquote/ltp", "/ltp"]

for base in bases:
    print(f"\n{'='*50}")
    print(f"BASE URL: {base}")
    print('='*50)
    
    for ep in endpoints:
        url = f"{base}{ep}"
        print(f"\n🔄 GET {url}")
        try:
            r = requests.get(url, headers=headers, timeout=5)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")
        
        # POST bhi try karo
        print(f"\n🔄 POST {url}")
        try:
            r = requests.post(url, json={"NSE": ["SENSEX"]}, headers=headers, timeout=5)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")
