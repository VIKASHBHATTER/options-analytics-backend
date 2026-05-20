import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv('DHAN_CLIENT_ID')
access_token = os.getenv('DHAN_ACCESS_TOKEN')

print(f"Client ID: {client_id}")
print(f"Token: {access_token[:50]}...")

# ✅ CORRECT HEADERS (DhanHQ-py source code se)
headers = {
    'access-token': access_token,
    'client-id': client_id,              # 👈 'X-Dhan-Client-Id' nahi!
    'Content-type': 'application/json',  # 👈 lowercase 't'
    'Accept': 'application/json'
}

BASE = "https://api.dhan.co/v2"

print("\n💰 Funds...")
r = requests.get(f"{BASE}/fund-limit", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n📈 Holdings...")
r = requests.get(f"{BASE}/holdings", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n📋 Orders...")
r = requests.get(f"{BASE}/orders", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n🎯 Positions...")
r = requests.get(f"{BASE}/positions", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n📊 LTP (SENSEX)...")
payload = {"NSE": ["SENSEX"]}
r = requests.post(f"{BASE}/market-quote/ltp", json=payload, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n📈 OHLC (SENSEX)...")
payload2 = {"NSE": ["SENSEX"]}
r = requests.post(f"{BASE}/market-quote/ohlc", json=payload2, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")
