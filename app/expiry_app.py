"""
Expiry List Application Module
Handles all expiry list related operations
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')
DHAN_BASE_URL = "https://api.dhan.co"

HEADERS = {
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

INDEX_SECURITY_IDS = {
    'NIFTY': '13',
    'BANKNIFTY': '25',
    'FINNIFTY': '27',
    'MIDCPNIFTY': '442',
    'SENSEX': '51',
    'BANKEX': '69'
}

def dhan_post(endpoint, payload):
    """Make POST request to Dhan API"""
    url = f"{DHAN_BASE_URL}{endpoint}"
    try:
        if isinstance(payload, dict):
            payload["dhanClientId"] = DHAN_CLIENT_ID
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        return resp
    except Exception as e:
        return type('obj', (object,), {
            'status_code': 500, 
            'text': str(e), 
            'json': lambda: {"error": str(e)}
        })()

def get_expiry_list(symbol):
    """Fetch expiry list for given symbol"""
    sec_id = INDEX_SECURITY_IDS.get(symbol.upper())
    if not sec_id:
        return {"error": f"Unknown symbol: {symbol}"}, 400
    
    payload = {
        "UnderlyingScrip": int(sec_id),
        "UnderlyingSeg": "IDX_I"
    }
    
    resp = dhan_post("/v2/optionchain/expirylist", payload)
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get('status') == 'success' and 'data' in data:
            return {
                "status": "success",
                "symbol": symbol.upper(),
                "expiries": data['data']
            }, 200
        else:
            return {
                "status": "error",
                "message": "Invalid response",
                "raw_response": data
            }, 500
    else:
        return {"error": resp.text}, resp.status_code
