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

BASE = "https://api.dhan.co/v2"

# Try different fund endpoints
endpoints = [
    "/fund-limit",
    "/fundlimits",
    "/fund",
    "/margin",
    "/limits",
    "/user/fund-limit",
    "/portfolio/fund-limit",
]

for ep in endpoints:
    print(f"\n🔄 Trying: {BASE}{ep}")
    r = requests.get(f"{BASE}{ep}", headers=headers, timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:200]}")
