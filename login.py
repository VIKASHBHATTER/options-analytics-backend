import os
import pyotp
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv('DHAN_CLIENT_ID')
totp_secret = os.getenv('DHAN_TOTP')

print(f"Client ID: {client_id}")

totp = pyotp.TOTP(totp_secret)
current_otp = totp.now()
print(f"Current TOTP: {current_otp}")

PIN = "210519"

# Try different endpoints
endpoints = [
    "https://api.dhan.co/v2/login",
    "https://api.dhan.co/login",
    "https://api.dhan.co/v1/login",
]

for url in endpoints:
    print(f"\n🔄 Trying: {url}")
    try:
        response = requests.post(url, json={
            "client_id": client_id,
            "pin": PIN,
            "totp": current_otp
        }, headers={"Content-Type": "application/json"}, timeout=10)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        if response.status_code == 200:
            print("✅ This endpoint works!")
            break
            
    except Exception as e:
        print(f"❌ Failed: {e}")
