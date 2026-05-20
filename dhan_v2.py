import requests

CLIENT_ID = "1106299230"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzc5MjY4OTE0LCJpYXQiOjE3NzkxODI1MTQsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA2Mjk5MjMwIn0.u5bnLLsNs-Y__4wo00Hyx5NnMnUlRkLRxU2qMux5xWhrODH9qnpZWfMSf1e2bHyJ27jFNbL_XzM0jv7KG2FIAQ"

headers = {
    'access-token': ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

BASE_URL = "https://api.dhan.co/v2"

print("="*60)
print("DHAN API v2")
print("="*60)

# Funds
print("\n💰 FUNDS")
r = requests.get(f'{BASE_URL}/fundlimit', headers=headers)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    try:
        print(r.json())
    except:
        print(r.text[:500])

print("\n✅ DONE")

