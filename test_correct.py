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

print("="*60)
print("💰 FUNDS (/fundlimit)")
r = requests.get(f"{BASE}/fundlimit", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n" + "="*60)
print("📈 HOLDINGS (/holdings)")
r = requests.get(f"{BASE}/holdings", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n" + "="*60)
print("🎯 POSITIONS (/positions)")
r = requests.get(f"{BASE}/positions", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n" + "="*60)
print("📋 ORDERS (/orders)")
r = requests.get(f"{BASE}/orders", headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n" + "="*60)
print("📊 INTRADAY CHART (/charts/intraday)")
payload = {
    "securityId": "1",
    "exchangeSegment": "IDX_I",
    "instrument": "INDEX",
    "interval": 1,
    "fromDate": "2026-05-19",
    "toDate": "2026-05-20"
}
r = requests.post(f"{BASE}/charts/intraday", json=payload, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")

print("\n" + "="*60)
print("📊 HISTORICAL CHART (/charts/historical)")
payload2 = {
    "securityId": "1",
    "exchangeSegment": "IDX_I", 
    "instrument": "INDEX",
    "fromDate": "2026-05-01",
    "toDate": "2026-05-20"
}
r = requests.post(f"{BASE}/charts/historical", json=payload2, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")
