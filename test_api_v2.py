import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv('DHAN_CLIENT_ID')
access_token = os.getenv('DHAN_ACCESS_TOKEN')

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Dhan-Client-Id": client_id,
    "access-token": access_token
}

BASE = "https://api.dhan.co/v2"

print("💰 Funds (GET /v2/fund-limit)...")
r = requests.get(f"{BASE}/fund-limit", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n📊 LTP (POST /v2/market-quote/ltp)...")
# Correct payload format
payload = {
    "NSE": ["SENSEX"]  # Ya security_id use karo
}
r = requests.post(f"{BASE}/market-quote/ltp", json=payload, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n📈 OHLC (POST /v2/market-quote/ohlc)...")
payload2 = {
    "NSE": ["SENSEX"]
}
r = requests.post(f"{BASE}/market-quote/ohlc", json=payload2, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n🔍 Full Quote (POST /v2/market-quote/full)...")
payload3 = {
    "NSE": ["SENSEX"]
}
r = requests.post(f"{BASE}/market-quote/full", json=payload3, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")
